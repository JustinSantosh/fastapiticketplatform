"""Ticket endpoints. Thin: validate input, call a service, return a schema."""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app import services as service
from app.auth import get_current_user
from app.db import get_db
from app.models import Priority, Status, User
from app.schemas import (
    AssignRequest,
    CommentCreate,
    CommentOut,
    ErrorResponse,
    StatusChangeRequest,
    TicketCreate,
    TicketDetail,
    TicketOut,
    TicketPage,
)

router = APIRouter(prefix="/api/tickets", tags=["tickets"])

ERRORS = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
}
EDIT_ERRORS = {**ERRORS, 400: {"model": ErrorResponse}, 409: {"model": ErrorResponse}}


@router.get("", response_model=TicketPage, responses={401: {"model": ErrorResponse}})
def list_tickets(
    status_: Status | None = Query(None, alias="status"),
    priority: Priority | None = None,
    assignee: str | None = Query(None, pattern=r"^(me|unassigned|\d+)$"),
    q: str | None = Query(None, max_length=100),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TicketPage:
    filters = service.TicketFilters(
        status=status_, priority=priority, assignee=assignee, q=(q or "").strip() or None
    )
    items, total, pages = service.list_tickets(db, user, filters, page, page_size)
    return TicketPage(
        items=[TicketOut.model_validate(t) for t in items],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.post("", response_model=TicketDetail, status_code=status.HTTP_201_CREATED, responses=ERRORS)
def create_ticket(
    body: TicketCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    return service.create_ticket(db, user, body)


@router.get("/{ticket_id}", response_model=TicketDetail, responses=ERRORS)
def get_ticket(ticket_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return service.get_ticket(db, user, ticket_id)


@router.post("/{ticket_id}/status", response_model=TicketDetail, responses=EDIT_ERRORS)
def change_status(
    ticket_id: int,
    body: StatusChangeRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return service.change_status(db, user, ticket_id, body)


@router.post("/{ticket_id}/assign", response_model=TicketDetail, responses=EDIT_ERRORS)
def assign_ticket(
    ticket_id: int,
    body: AssignRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return service.assign_ticket(db, user, ticket_id, body)


@router.get("/{ticket_id}/comments", response_model=list[CommentOut], responses=ERRORS)
def list_comments(ticket_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return service.list_comments(db, user, ticket_id)


@router.post(
    "/{ticket_id}/comments",
    response_model=CommentOut,
    status_code=status.HTTP_201_CREATED,
    responses=ERRORS,
)
def add_comment(
    ticket_id: int,
    body: CommentCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return service.add_comment(db, user, ticket_id, body.body)
