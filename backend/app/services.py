"""Ticket use-cases. Each function: load -> check rules -> write -> commit.

Services know about the DB and the rules, but not about HTTP; they raise
DomainErrors and main.py turns those into status codes.
"""

import math
from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.orm.exc import StaleDataError

from app import rules
from app.models import Comment, Priority, Role, Status, Ticket, TicketStatusChange, User
from app.schemas import AssignRequest, StatusChangeRequest, TicketCreate


@dataclass
class TicketFilters:
    status: Status | None = None
    priority: Priority | None = None
    assignee: str | None = None  # "me" | "unassigned" | "<agent id>"
    q: str | None = None


# --- Reads ---------------------------------------------------------------------


def _load_ticket(db: Session, ticket_id: int, *, detail: bool = False) -> Ticket | None:
    stmt = select(Ticket).where(Ticket.id == ticket_id).options(
        selectinload(Ticket.creator), selectinload(Ticket.assignee)
    )
    if detail:
        stmt = stmt.options(
            selectinload(Ticket.comments).selectinload(Comment.author),
            selectinload(Ticket.status_changes).selectinload(TicketStatusChange.changed_by),
        )
    # populate_existing: always take fresh column values (incl. version) from the DB
    return db.scalar(stmt.execution_options(populate_existing=True))


def get_ticket(db: Session, user: User, ticket_id: int) -> Ticket:
    return rules.ensure_can_view(user, _load_ticket(db, ticket_id, detail=True))


def list_tickets(
    db: Session, user: User, filters: TicketFilters, page: int, page_size: int
) -> tuple[list[Ticket], int, int]:
    """Returns (items, total, pages). Newest first."""
    stmt = select(Ticket)

    # Privacy rule applied in the query itself: a user's list can only ever
    # contain their own tickets, whatever filters they send.
    if not user.is_agent:
        stmt = stmt.where(Ticket.creator_id == user.id)

    if filters.status:
        stmt = stmt.where(Ticket.status == filters.status)
    if filters.priority:
        stmt = stmt.where(Ticket.priority == filters.priority)
    if filters.assignee == "me":
        stmt = stmt.where(Ticket.assignee_id == user.id)
    elif filters.assignee == "unassigned":
        stmt = stmt.where(Ticket.assignee_id.is_(None))
    elif filters.assignee:
        stmt = stmt.where(Ticket.assignee_id == int(filters.assignee))
    if filters.q:
        # autoescape: a search for "50%" matches the literal text, not a wildcard
        stmt = stmt.where(
            or_(
                Ticket.title.icontains(filters.q, autoescape=True),
                Ticket.description.icontains(filters.q, autoescape=True),
            )
        )

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = db.scalars(
        stmt.options(selectinload(Ticket.creator), selectinload(Ticket.assignee))
        .order_by(Ticket.created_at.desc(), Ticket.id.desc())  # id breaks ties: stable pages
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return list(items), total, max(1, math.ceil(total / page_size))


def list_comments(db: Session, user: User, ticket_id: int) -> list[Comment]:
    return get_ticket(db, user, ticket_id).comments


# --- Writes --------------------------------------------------------------------


def _commit_ticket_change(db: Session) -> None:
    """Commit, turning a lost optimistic-lock race into a VersionConflict.

    StaleDataError means our `UPDATE ... WHERE version = N` matched 0 rows:
    another request changed the ticket after we loaded it.
    """
    try:
        db.commit()
    except StaleDataError:
        db.rollback()
        raise rules.VersionConflict(
            "Ticket was modified by someone else at the same time. Reload and try again."
        )


def create_ticket(db: Session, user: User, data: TicketCreate) -> Ticket:
    rules.ensure_can_create_ticket(user)
    ticket = Ticket(
        title=data.title, description=data.description, priority=data.priority, creator=user
    )
    db.add(ticket)
    db.commit()
    return get_ticket(db, user, ticket.id)


def change_status(db: Session, user: User, ticket_id: int, req: StatusChangeRequest) -> Ticket:
    ticket = rules.ensure_can_view(user, _load_ticket(db, ticket_id))
    rules.ensure_can_change_status(user, ticket, req.status)
    rules.ensure_version_matches(ticket, req.version)
    rules.validate_transition(ticket.status, req.status, req.reason)

    db.add(
        TicketStatusChange(
            ticket=ticket,
            from_status=ticket.status,
            to_status=req.status,
            reason=req.reason or None,
            changed_by=user,
        )
    )
    ticket.status = req.status
    _commit_ticket_change(db)
    return get_ticket(db, user, ticket_id)


def assign_ticket(db: Session, user: User, ticket_id: int, req: AssignRequest) -> Ticket:
    ticket = rules.ensure_can_view(user, _load_ticket(db, ticket_id))
    assignee = db.get(User, req.assignee_id) if req.assignee_id is not None else None
    if req.assignee_id is not None and assignee is None:
        raise rules.RuleViolation(f"User {req.assignee_id} does not exist")
    rules.ensure_can_assign(user, assignee)
    rules.ensure_version_matches(ticket, req.version)

    ticket.assignee = assignee
    _commit_ticket_change(db)
    return get_ticket(db, user, ticket_id)


def add_comment(db: Session, user: User, ticket_id: int, body: str) -> Comment:
    # Comments are append-only rows, so two people commenting at once can't
    # overwrite each other - no version check (and no ticket version bump) needed.
    ticket = rules.ensure_can_view(user, _load_ticket(db, ticket_id))
    rules.ensure_can_comment(user, ticket)
    comment = Comment(ticket=ticket, author=user, body=body)
    db.add(comment)
    db.commit()
    return comment


def list_agents(db: Session, user: User) -> list[User]:
    if not user.is_agent:
        raise rules.PermissionDenied("Only agents can list agents")
    return list(db.scalars(select(User).where(User.role == Role.AGENT).order_by(User.full_name)))
