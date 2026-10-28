"""Business rules of the support desk, as pure functions.

Nothing here touches the database or HTTP. Each function either returns normally
or raises a DomainError. Services call these before writing; main.py maps each
error class to an HTTP status code. Keeping the rules here means they read like
the spec and can be unit-tested without a server.

Order services check in:
  1. ensure_can_view           -> 404  (don't reveal that someone else's ticket exists)
  2. ensure_can_change_status  -> 403  (role / assignee permission)
  3. ensure_version_matches    -> 409  (client acted on stale data; reload first)
  4. validate_transition       -> 400  (the move itself is not allowed)
"""

from app.models import Role, Status, Ticket, User


# --- Domain errors ---------------------------------------------------------


class DomainError(Exception):
    """Base for every business-rule failure. `code` is machine-readable for the frontend."""

    code = "domain_error"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotFound(DomainError):
    code = "not_found"


class PermissionDenied(DomainError):
    code = "permission_denied"


class RuleViolation(DomainError):
    """The request is well-formed but breaks a business rule (e.g. open -> resolved)."""

    code = "rule_violation"


class VersionConflict(DomainError):
    """Someone else updated the ticket since the client last loaded it."""

    code = "version_conflict"


# --- Status transitions ----------------------------------------------------

# The only legal moves. Anything not listed (open -> resolved, resolved -> open,
# same -> same) is rejected.
ALLOWED_TRANSITIONS: dict[Status, set[Status]] = {
    Status.OPEN: {Status.IN_PROGRESS},
    Status.IN_PROGRESS: {Status.RESOLVED},
    Status.RESOLVED: {Status.IN_PROGRESS},  # "reopen": needs a reason
}

REASON_REQUIRED: set[tuple[Status, Status]] = {(Status.RESOLVED, Status.IN_PROGRESS)}


def validate_transition(current: Status, target: Status, reason: str | None) -> None:
    if target not in ALLOWED_TRANSITIONS[current]:
        raise RuleViolation(f"Cannot change status from '{current.value}' to '{target.value}'")
    if (current, target) in REASON_REQUIRED and not (reason and reason.strip()):
        raise RuleViolation("A reason is required to reopen a resolved ticket")


# --- Permissions -----------------------------------------------------------


def can_view_ticket(user: User, ticket: Ticket) -> bool:
    """Agents see every ticket; users only the ones they created."""
    return user.is_agent or ticket.creator_id == user.id


def ensure_can_view(user: User, ticket: Ticket | None) -> Ticket:
    # 404 rather than 403, so users can't probe which ticket ids exist.
    if ticket is None or not can_view_ticket(user, ticket):
        raise NotFound("Ticket not found")
    return ticket


def ensure_can_create_ticket(user: User) -> None:
    # Assumption: tickets are raised by users; agents work them.
    if user.is_agent:
        raise PermissionDenied("Only users can create tickets")


def ensure_can_comment(user: User, ticket: Ticket) -> None:
    # Anyone who can see the ticket can discuss it.
    ensure_can_view(user, ticket)


def ensure_can_change_status(user: User, ticket: Ticket, target: Status) -> None:
    if not user.is_agent:
        raise PermissionDenied("Only agents can change ticket status")
    if target == Status.RESOLVED and ticket.assignee_id != user.id:
        raise PermissionDenied("Only the assigned agent can resolve this ticket")


def ensure_can_assign(user: User, assignee: User | None) -> None:
    """`assignee=None` means un-assign."""
    if not user.is_agent:
        raise PermissionDenied("Only agents can assign tickets")
    if assignee is not None and assignee.role != Role.AGENT:
        raise RuleViolation("Tickets can only be assigned to agents")


# --- Concurrency -----------------------------------------------------------


def ensure_version_matches(ticket: Ticket, client_version: int) -> None:
    """First line of the optimistic lock: reject edits based on a stale copy.

    The second line is SQLAlchemy's version_id_col (see models.Ticket), which
    catches a concurrent write landing between our read and our UPDATE.
    """
    if ticket.version != client_version:
        raise VersionConflict(
            f"Ticket was modified by someone else (your version {client_version}, "
            f"current version {ticket.version}). Reload and try again."
        )
