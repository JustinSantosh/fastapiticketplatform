"""Conflicting concurrent updates must not silently overwrite each other.

Layer 1: client sends the version it saw; a stale one gets 409.
Layer 2: UPDATE ... WHERE version = N; losing a race at the DB also gets 409.
"""

import threading

import pytest

from app import rules
from app.models import Status, Ticket
from app.services import _commit_ticket_change
from tests.conftest import auth, history

# --- Layer 1: stale client ----------------------------------------------------------


def test_stale_version_is_rejected_with_409(client, db, alice, sam, priya, make_ticket):
    t = make_ticket(alice, assignee=sam)
    # Both agents loaded the ticket at version 1.
    first = client.post(f"/api/tickets/{t.id}/status", headers=auth(sam), json={"status": "in_progress", "version": 1})
    assert first.status_code == 200 and first.json()["version"] == 2

    second = client.post(f"/api/tickets/{t.id}/assign", headers=auth(priya), json={"assignee_id": priya.id, "version": 1})
    assert second.status_code == 409
    assert second.json()["code"] == "version_conflict"
    assert "your version 1, current version 2" in second.json()["detail"]

    # The first writer's change survived; the second changed nothing.
    db.expire_all()
    ticket = db.get(Ticket, t.id)
    assert ticket.assignee_id == sam.id and ticket.status == Status.IN_PROGRESS and ticket.version == 2


def test_conflict_is_reported_before_transition_errors(client, alice, sam, make_ticket):
    # Client thinks ticket is v1/open and asks for in_progress; it's actually v2.
    # It must be told "reload" (409), not given a misleading transition error.
    t = make_ticket(alice, assignee=sam)
    client.post(f"/api/tickets/{t.id}/status", headers=auth(sam), json={"status": "in_progress", "version": 1})
    r = client.post(f"/api/tickets/{t.id}/status", headers=auth(sam), json={"status": "in_progress", "version": 1})
    assert r.status_code == 409


def test_retry_with_fresh_version_succeeds(client, alice, sam, priya, make_ticket):
    t = make_ticket(alice, assignee=sam)
    client.post(f"/api/tickets/{t.id}/assign", headers=auth(sam), json={"assignee_id": priya.id, "version": 1})
    stale = client.post(f"/api/tickets/{t.id}/assign", headers=auth(sam), json={"assignee_id": None, "version": 1})
    assert stale.status_code == 409

    current = client.get(f"/api/tickets/{t.id}", headers=auth(sam)).json()["version"]
    retry = client.post(f"/api/tickets/{t.id}/assign", headers=auth(sam), json={"assignee_id": None, "version": current})
    assert retry.status_code == 200 and retry.json()["assignee"] is None


def test_comments_never_conflict_and_do_not_bump_version(client, db, alice, sam, make_ticket):
    t = make_ticket(alice)
    assert client.post(f"/api/tickets/{t.id}/comments", headers=auth(alice), json={"body": "one"}).status_code == 201
    assert client.post(f"/api/tickets/{t.id}/comments", headers=auth(sam), json={"body": "two"}).status_code == 201
    db.expire_all()
    assert db.get(Ticket, t.id).version == 1


# --- Layer 2: race between read and write --------------------------------------------


def test_db_level_lock_catches_write_between_read_and_commit(session_factory, alice, sam, priya, make_ticket):
    """Deterministic version of the race: both sessions read v1, one commits first."""
    t = make_ticket(alice)
    with session_factory() as a, session_factory() as b:
        ticket_a = a.get(Ticket, t.id)
        ticket_b = b.get(Ticket, t.id)
        assert ticket_a.version == ticket_b.version == 1  # both passed the layer-1 check

        ticket_a.assignee_id = sam.id
        _commit_ticket_change(a)  # UPDATE ... WHERE version = 1 -> matches, v2

        ticket_b.assignee_id = priya.id
        with pytest.raises(rules.VersionConflict):
            _commit_ticket_change(b)  # UPDATE ... WHERE version = 1 -> 0 rows

    with session_factory() as check:
        final = check.get(Ticket, t.id)
        assert final.assignee_id == sam.id and final.version == 2


@pytest.mark.parametrize("attempt", range(5))
def test_parallel_requests_with_same_version_exactly_one_wins(client, db, alice, sam, priya, make_ticket, attempt):
    """Two real HTTP requests fired at the same instant with the same version."""
    t = make_ticket(alice, status=Status.IN_PROGRESS, assignee=sam)
    barrier = threading.Barrier(2)
    results: dict[str, int] = {}

    def fire(name, agent, payload):
        barrier.wait()  # release both threads together
        results[name] = client.post(f"/api/tickets/{t.id}/{payload.pop('_path')}", headers=auth(agent), json=payload).status_code

    threads = [
        threading.Thread(target=fire, args=("resolve", sam, {"_path": "status", "status": "resolved", "version": 1})),
        threading.Thread(target=fire, args=("reassign", priya, {"_path": "assign", "assignee_id": priya.id, "version": 1})),
    ]
    for th in threads:
        th.start()
    for th in threads:
        th.join()

    assert sorted(results.values()) == [200, 409], results

    db.expire_all()
    final = db.get(Ticket, t.id)
    assert final.version == 2  # exactly one write landed
    if results["resolve"] == 200:
        assert final.status == Status.RESOLVED and final.assignee_id == sam.id
        assert len(history(db, t.id)) == 1
    else:
        assert final.status == Status.IN_PROGRESS and final.assignee_id == priya.id
        assert history(db, t.id) == []  # the losing request's history row was rolled back too
