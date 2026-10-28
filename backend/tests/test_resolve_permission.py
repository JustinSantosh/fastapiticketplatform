"""Only the assigned agent can resolve a ticket."""

from app.models import Status
from tests.conftest import auth


def resolve(client, actor, ticket_id, version=1):
    return client.post(
        f"/api/tickets/{ticket_id}/status",
        headers=auth(actor),
        json={"status": "resolved", "version": version},
    )


def test_assigned_agent_can_resolve(client, alice, sam, make_ticket):
    t = make_ticket(alice, status=Status.IN_PROGRESS, assignee=sam)
    r = resolve(client, sam, t.id)
    assert r.status_code == 200
    assert r.json()["status"] == "resolved"


def test_other_agent_cannot_resolve(client, alice, sam, priya, make_ticket):
    t = make_ticket(alice, status=Status.IN_PROGRESS, assignee=sam)
    r = resolve(client, priya, t.id)
    assert r.status_code == 403
    assert r.json() == {"detail": "Only the assigned agent can resolve this ticket", "code": "permission_denied"}


def test_unassigned_ticket_cannot_be_resolved_by_any_agent(client, alice, sam, make_ticket):
    t = make_ticket(alice, status=Status.IN_PROGRESS, assignee=None)
    assert resolve(client, sam, t.id).status_code == 403


def test_ticket_creator_cannot_resolve(client, alice, sam, make_ticket):
    t = make_ticket(alice, status=Status.IN_PROGRESS, assignee=sam)
    assert resolve(client, alice, t.id).status_code == 403


def test_reassignment_moves_the_right_to_resolve(client, alice, sam, priya, make_ticket):
    t = make_ticket(alice, status=Status.IN_PROGRESS, assignee=sam)
    r = client.post(f"/api/tickets/{t.id}/assign", headers=auth(sam), json={"assignee_id": priya.id, "version": 1})
    assert r.status_code == 200 and r.json()["version"] == 2

    assert resolve(client, sam, t.id, version=2).status_code == 403  # no longer assignee
    assert resolve(client, priya, t.id, version=2).status_code == 200


def test_permission_is_checked_before_transition(client, alice, sam, priya, make_ticket):
    # Ticket is Open (open -> resolved is also illegal). A non-assignee must get
    # 403 for permission, not a 400 that reveals the transition rules.
    t = make_ticket(alice, status=Status.OPEN, assignee=sam)
    assert resolve(client, priya, t.id).status_code == 403
