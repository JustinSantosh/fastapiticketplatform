"""Authentication, role permissions and user ticket privacy (enforced server-side)."""

from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.config import get_settings
from tests.conftest import PASSWORD, auth

# --- Login -----------------------------------------------------------------------


def test_login_returns_token_that_works(client, alice):
    r = client.post("/api/auth/login", json={"email": "ALICE@test.io", "password": PASSWORD})
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["email"] == "alice@test.io"
    assert "hashed_password" not in body["user"]

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200 and me.json()["id"] == alice.id


@pytest.mark.parametrize(
    "email,password", [("alice@test.io", "wrong"), ("nobody@test.io", PASSWORD)]
)
def test_login_failure_gives_same_generic_401(client, alice, email, password):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 401
    assert r.json() == {"detail": "Invalid email or password", "code": "unauthorized"}


def _token(user_id: int, secret: str, minutes: int) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    return jwt.encode({"sub": str(user_id), "exp": exp}, secret, algorithm="HS256")


@pytest.mark.parametrize(
    "header",
    [
        None,  # no header at all
        "Bearer not-a-jwt",
        "Bearer {forged}",  # signed with the wrong secret
        "Bearer {expired}",
    ],
)
def test_protected_endpoints_reject_bad_tokens(client, alice, header):
    tokens = {
        "forged": _token(alice.id, "attacker-secret", 60),
        "expired": _token(alice.id, get_settings().jwt_secret, -1),
    }
    headers = {"Authorization": header.format(**tokens)} if header else {}
    r = client.get("/api/tickets", headers=headers)
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"


# --- Ticket privacy ---------------------------------------------------------------


def test_user_cannot_read_another_users_ticket(client, alice, bob, make_ticket):
    t = make_ticket(alice)
    assert client.get(f"/api/tickets/{t.id}", headers=auth(alice)).status_code == 200
    r = client.get(f"/api/tickets/{t.id}", headers=auth(bob))
    # 404, not 403: Bob can't even learn that ticket exists
    assert r.status_code == 404
    assert r.json()["code"] == "not_found"


def test_other_users_ticket_looks_identical_to_missing_ticket(client, alice, bob, make_ticket):
    t = make_ticket(alice)
    hidden = client.get(f"/api/tickets/{t.id}", headers=auth(bob))
    missing = client.get("/api/tickets/999999", headers=auth(bob))
    assert hidden.status_code == missing.status_code == 404
    assert hidden.json() == missing.json()


def test_user_cannot_read_or_add_comments_on_another_users_ticket(client, alice, bob, make_ticket):
    t = make_ticket(alice)
    assert client.get(f"/api/tickets/{t.id}/comments", headers=auth(bob)).status_code == 404
    r = client.post(f"/api/tickets/{t.id}/comments", headers=auth(bob), json={"body": "hi"})
    assert r.status_code == 404


def test_user_list_contains_only_own_tickets_even_with_filters(client, alice, bob, sam, make_ticket):
    mine = make_ticket(alice, title="Alice issue")
    make_ticket(bob, title="Bob issue", assignee=sam)
    for params in [{}, {"assignee": str(sam.id)}, {"q": "issue"}, {"page_size": 100}]:
        r = client.get("/api/tickets", headers=auth(alice), params=params)
        assert r.status_code == 200
        ids = [t["id"] for t in r.json()["items"]]
        assert set(ids) <= {mine.id}, params


def test_agent_sees_every_ticket(client, alice, bob, sam, make_ticket):
    a, b = make_ticket(alice), make_ticket(bob)
    r = client.get("/api/tickets", headers=auth(sam))
    assert {t["id"] for t in r.json()["items"]} == {a.id, b.id}
    assert client.get(f"/api/tickets/{a.id}", headers=auth(sam)).status_code == 200


# --- Role permissions ---------------------------------------------------------------


def test_user_can_create_and_comment_on_own_ticket(client, alice):
    r = client.post("/api/tickets", headers=auth(alice), json={"title": "VPN down", "description": "Since 9am"})
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "open" and body["version"] == 1 and body["creator"]["id"] == alice.id
    c = client.post(f"/api/tickets/{body['id']}/comments", headers=auth(alice), json={"body": "Still down"})
    assert c.status_code == 201


def test_agent_cannot_create_ticket(client, sam):
    r = client.post("/api/tickets", headers=auth(sam), json={"title": "VPN down", "description": "x"})
    assert r.status_code == 403


def test_user_cannot_assign_or_change_status_even_on_own_ticket(client, alice, sam, make_ticket):
    t = make_ticket(alice)
    r = client.post(f"/api/tickets/{t.id}/assign", headers=auth(alice), json={"assignee_id": sam.id, "version": 1})
    assert r.status_code == 403
    r = client.post(f"/api/tickets/{t.id}/status", headers=auth(alice), json={"status": "in_progress", "version": 1})
    assert r.status_code == 403


def test_agent_list_endpoint_is_agent_only(client, alice, sam):
    assert client.get("/api/users/agents", headers=auth(alice)).status_code == 403
    r = client.get("/api/users/agents", headers=auth(sam))
    assert r.status_code == 200 and [a["id"] for a in r.json()] == [sam.id]


def test_cannot_assign_ticket_to_a_non_agent(client, alice, bob, sam, make_ticket):
    t = make_ticket(alice)
    r = client.post(f"/api/tickets/{t.id}/assign", headers=auth(sam), json={"assignee_id": bob.id, "version": 1})
    assert r.status_code == 400 and r.json()["code"] == "rule_violation"


# --- Validation ---------------------------------------------------------------------


def test_create_ticket_validation_errors_are_per_field(client, alice):
    r = client.post("/api/tickets", headers=auth(alice), json={"title": "  a  ", "description": "   ", "priority": "urgent"})
    assert r.status_code == 422
    fields = {e["field"] for e in r.json()["errors"]}
    assert fields == {"title", "description", "priority"}
