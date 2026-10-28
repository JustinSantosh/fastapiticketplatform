"""Unit tests for app/rules.py: pure functions, no database or HTTP."""

import itertools

import pytest

from app import rules
from app.models import Role, Status, Ticket, User

OPEN, IN_PROGRESS, RESOLVED = Status.OPEN, Status.IN_PROGRESS, Status.RESOLVED

ALLOWED = {(OPEN, IN_PROGRESS), (IN_PROGRESS, RESOLVED), (RESOLVED, IN_PROGRESS)}
ALL_PAIRS = list(itertools.product(Status, Status))


def user(id_: int, role: Role) -> User:
    return User(id=id_, email=f"u{id_}@t.io", full_name="T", role=role, hashed_password="x")


def ticket(creator_id: int = 1, assignee_id: int | None = None, version: int = 1) -> Ticket:
    return Ticket(id=99, creator_id=creator_id, assignee_id=assignee_id, version=version, status=OPEN)


# --- Transitions: every one of the 9 (from, to) pairs is checked ----------------


@pytest.mark.parametrize("current,target", [p for p in ALL_PAIRS if p in ALLOWED])
def test_allowed_transitions_pass(current, target):
    rules.validate_transition(current, target, reason="because")


@pytest.mark.parametrize("current,target", [p for p in ALL_PAIRS if p not in ALLOWED])
def test_disallowed_transitions_raise(current, target):
    with pytest.raises(rules.RuleViolation, match="Cannot change status"):
        rules.validate_transition(current, target, reason="because")


@pytest.mark.parametrize("reason", [None, "", "   "])
def test_reopen_requires_non_blank_reason(reason):
    with pytest.raises(rules.RuleViolation, match="reason is required"):
        rules.validate_transition(RESOLVED, IN_PROGRESS, reason)


def test_forward_moves_do_not_need_a_reason():
    rules.validate_transition(OPEN, IN_PROGRESS, None)
    rules.validate_transition(IN_PROGRESS, RESOLVED, None)


# --- Permissions ------------------------------------------------------------------


def test_user_sees_only_own_ticket_and_agent_sees_all():
    owner, other, agent = user(1, Role.USER), user(2, Role.USER), user(3, Role.AGENT)
    t = ticket(creator_id=1)
    assert rules.can_view_ticket(owner, t)
    assert rules.can_view_ticket(agent, t)
    assert not rules.can_view_ticket(other, t)
    with pytest.raises(rules.NotFound):
        rules.ensure_can_view(other, t)


def test_missing_ticket_is_not_found():
    with pytest.raises(rules.NotFound):
        rules.ensure_can_view(user(1, Role.AGENT), None)


def test_only_assigned_agent_may_resolve():
    assignee, other_agent = user(3, Role.AGENT), user(4, Role.AGENT)
    t = ticket(assignee_id=3)
    rules.ensure_can_change_status(assignee, t, RESOLVED)
    with pytest.raises(rules.PermissionDenied, match="assigned agent"):
        rules.ensure_can_change_status(other_agent, t, RESOLVED)
    with pytest.raises(rules.PermissionDenied, match="assigned agent"):
        rules.ensure_can_change_status(assignee, ticket(assignee_id=None), RESOLVED)


def test_any_agent_may_start_or_reopen_but_users_may_not():
    t = ticket(assignee_id=3)
    rules.ensure_can_change_status(user(4, Role.AGENT), t, IN_PROGRESS)
    with pytest.raises(rules.PermissionDenied, match="Only agents"):
        rules.ensure_can_change_status(user(1, Role.USER), t, IN_PROGRESS)


def test_assign_rules():
    agent, plain_user = user(3, Role.AGENT), user(1, Role.USER)
    rules.ensure_can_assign(agent, agent)
    rules.ensure_can_assign(agent, None)  # unassign
    with pytest.raises(rules.PermissionDenied):
        rules.ensure_can_assign(plain_user, agent)
    with pytest.raises(rules.RuleViolation, match="only be assigned to agents"):
        rules.ensure_can_assign(agent, plain_user)


def test_only_users_create_tickets():
    rules.ensure_can_create_ticket(user(1, Role.USER))
    with pytest.raises(rules.PermissionDenied):
        rules.ensure_can_create_ticket(user(3, Role.AGENT))


def test_version_must_match():
    rules.ensure_version_matches(ticket(version=4), 4)
    with pytest.raises(rules.VersionConflict, match="your version 3, current version 4"):
        rules.ensure_version_matches(ticket(version=4), 3)
