"""Pydantic models: the request/response contract of the API.

Request models validate and normalise input (whitespace is stripped before
length checks, so "   " is rejected as empty). Response models control exactly
which fields leave the server - e.g. hashed_password is never in UserOut.
"""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints

from app.models import Priority, Role, Status

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=200)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)]
CommentBody = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)  # build from SQLAlchemy objects


# --- Users / auth ------------------------------------------------------------


class UserBrief(ORMModel):
    id: int
    full_name: str
    role: Role


class UserOut(UserBrief):
    email: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# --- Tickets -----------------------------------------------------------------


class TicketCreate(BaseModel):
    title: Title
    description: Description
    priority: Priority = Priority.MEDIUM


class TicketOut(ORMModel):
    id: int
    title: str
    description: str
    priority: Priority
    status: Status
    creator: UserBrief
    assignee: UserBrief | None
    version: int  # send back on every edit, for conflict detection
    created_at: datetime
    updated_at: datetime


class TicketPage(BaseModel):
    items: list[TicketOut]
    total: int
    page: int
    page_size: int
    pages: int


class CommentCreate(BaseModel):
    body: CommentBody


class CommentOut(ORMModel):
    id: int
    body: str
    author: UserBrief
    created_at: datetime


class StatusChangeOut(ORMModel):
    id: int
    from_status: Status
    to_status: Status
    reason: str | None
    changed_by: UserBrief
    created_at: datetime


class TicketDetail(TicketOut):
    comments: list[CommentOut]
    status_changes: list[StatusChangeOut]


class StatusChangeRequest(BaseModel):
    status: Status
    reason: Reason | None = None  # required only for reopen; rules.py enforces that
    version: int = Field(ge=1)


class AssignRequest(BaseModel):
    assignee_id: int | None  # null = unassign
    version: int = Field(ge=1)


# --- Errors (documented in OpenAPI) -------------------------------------------


class ErrorResponse(BaseModel):
    detail: str
    code: str
