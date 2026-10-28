"""Status transitions through the API: allowed, disallowed, reopen reason, history."""

import pytest

from app.models import Status
from tests.conftest import auth, history


def change(client, agent, ticket_id, status, version, reason=None):
    body = {"status": status, "version": version}
    if reason is not None:
        body["reason"] = reason
    return client.post(f"/api/tickets/{ticket_id}/status", headers=auth(agent), json=body)


def test_full_lifecycle_open_to_resolved(client, db, alice, sam, make_ticket):
    t = make_ticket(alice, assignee=sam)

    r = change(client, sam, t.id, "in_progress", version=1)
    assert r.status_code == 200
    assert r.json()["status"] == "in_progress" and r.json()["version"] == 2

    r = change(client, sam, t.id, "resolved", version=2)
    assert r.status_code == 200
    assert r.json()["status"] == "resolved" and r.json()["version"] == 3

    moves = [(h.from_status, h.to_status, h.changed_by_id) for h in history(db, t.id)]
    assert moves == [
        (Status.OPEN, Status.IN_PROGRESS, sam.id),
        (Status.IN_PROGRESS, Status.RESOLVED, sam.id),
    ]


@pytest.mark.parametrize(
    "start,target",
    [
        (Status.OPEN, "resolved"),  # can't skip In Progress
        (Status.OPEN, "open"),  # no-op "transition"
        (Status.IN_PROGRESS, "open"),  # can't go backwards
        (Status.IN_PROGRESS, "in_progress"),
        (Status.RESOLVED, "open"),  # reopen goes to In Progress, not Open
        (Status.RESOLVED, "resolved"),
    ],
)
def test_disallowed_transitions_are_rejected_and_nothing_changes(client, db, alice, sam, make_ticket, start, target):
    t = make_ticket(alice, status=start, assignee=sam)
    r = change(client, sam, t.id, target, version=1, reason="some reason")
    assert r.status_code == 400
    assert r.json()["code"] == "rule_violation"

    db.expire_all()
    assert db.get(type(t), t.id).status == start
    assert db.get(type(t), t.id).version == 1  # rejected request did not write
    assert history(db, t.id) == []


@pytest.mark.parametrize("reason", [None, "", "    "])
def test_reopen_without_reason_is_rejected(client, alice, sam, make_ticket, reason):
    t = make_ticket(alice, status=Status.RESOLVED, assignee=sam)
    r = change(client, sam, t.id, "in_progress", version=1, reason=reason)
    assert r.status_code == 400
    assert "reason is required" in r.json()["detail"]


def test_reopen_with_reason_is_allowed_and_reason_is_recorded(client, db, alice, sam, priya, make_ticket):
    t = make_ticket(alice, status=Status.RESOLVED, assignee=sam)
    # Any agent may reopen (only resolving is restricted to the assignee)
    r = change(client, priya, t.id, "in_progress", version=1, reason="  Customer says it is still broken  ")
    assert r.status_code == 200
    assert r.json()["status"] == "in_progress"

    [entry] = history(db, t.id)
    assert (entry.from_status, entry.to_status) == (Status.RESOLVED, Status.IN_PROGRESS)
    assert entry.reason == "Customer says it is still broken"  # stripped
    assert entry.changed_by_id == priya.id


def test_detail_endpoint_exposes_history(client, alice, sam, make_ticket):
    t = make_ticket(alice, status=Status.RESOLVED, assignee=sam)
    change(client, sam, t.id, "in_progress", version=1, reason="Regression")
    detail = client.get(f"/api/tickets/{t.id}", headers=auth(alice)).json()
    assert [(h["from_status"], h["to_status"], h["reason"]) for h in detail["status_changes"]] == [
        ("resolved", "in_progress", "Regression")
    ]


def test_unknown_status_value_is_a_validation_error(client, alice, sam, make_ticket):
    t = make_ticket(alice)
    r = change(client, sam, t.id, "closed", version=1)
    assert r.status_code == 422
