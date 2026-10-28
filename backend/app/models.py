"""SQLAlchemy ORM models: the database schema of the support desk.

Four tables:
  users                  - people who log in (role: user or agent)
  tickets                - support requests; `version` powers optimistic locking
  comments               - discussion thread on a ticket
  ticket_status_changes  - audit trail of every status move (stores the reopen reason)
"""

import enum
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Role(str, enum.Enum):
    USER = "user"
    AGENT = "agent"


class Priority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Status(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"


def _enum(enum_cls: type[enum.Enum], name: str) -> Enum:
    """Store enums as VARCHAR + CHECK constraint (not a native PG enum type).

    Native PG enums need an ALTER TYPE migration to add a value; a CHECK constraint
    is just as strict but simpler to evolve. values_callable stores "in_progress",
    not the Python member name "IN_PROGRESS".
    """
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=20,
        values_callable=lambda e: [m.value for m in e],
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(_enum(Role, "user_role"), default=Role.USER)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    @property
    def is_agent(self) -> bool:
        return self.role == Role.AGENT

    def __repr__(self) -> str:
        return f"<User {self.id} {self.email} {self.role.value}>"


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    priority: Mapped[Priority] = mapped_column(
        _enum(Priority, "ticket_priority"), default=Priority.MEDIUM
    )
    status: Mapped[Status] = mapped_column(_enum(Status, "ticket_status"), default=Status.OPEN)

    # RESTRICT: a user who has tickets cannot be deleted out from under them.
    creator_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    # SET NULL: removing an agent un-assigns their tickets instead of deleting them.
    # "Assignee must be an agent" can't be a simple FK rule, so services enforce it.
    assignee_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Optimistic locking: SQLAlchemy adds "AND version = <old>" to every UPDATE and
    # bumps it by 1. If another transaction changed the row first, 0 rows match and
    # SQLAlchemy raises StaleDataError instead of silently overwriting.
    version: Mapped[int] = mapped_column(Integer, default=1)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    creator: Mapped[User] = relationship(foreign_keys=[creator_id])
    assignee: Mapped[User | None] = relationship(foreign_keys=[assignee_id])
    comments: Mapped[list["Comment"]] = relationship(
        back_populates="ticket", order_by="Comment.created_at", cascade="all, delete-orphan"
    )
    status_changes: Mapped[list["TicketStatusChange"]] = relationship(
        back_populates="ticket",
        order_by="TicketStatusChange.created_at",
        cascade="all, delete-orphan",
    )

    # eager_defaults: fetch server-generated values (updated_at) via RETURNING on
    # INSERT/UPDATE, so responses don't need an extra SELECT after commit.
    __mapper_args__ = {"version_id_col": version, "eager_defaults": True}

    __table_args__ = (
        CheckConstraint("length(btrim(title)) > 0", name="title_not_blank"),
        CheckConstraint("version >= 1", name="version_positive"),
        # Indexes match the dashboard's filters and default sort.
        Index("ix_tickets_creator_id", "creator_id"),
        Index("ix_tickets_assignee_id", "assignee_id"),
        Index("ix_tickets_status", "status"),
        Index("ix_tickets_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<Ticket {self.id} {self.status.value} v{self.version}>"


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(
        ForeignKey("tickets.id", ondelete="CASCADE"), index=True
    )
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    ticket: Mapped[Ticket] = relationship(back_populates="comments")
    author: Mapped[User] = relationship()

    __table_args__ = (CheckConstraint("length(btrim(body)) > 0", name="comment_not_blank"),)


class TicketStatusChange(Base):
    """One row per status move. Answers "who changed what, when, and why"."""

    __tablename__ = "ticket_status_changes"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(
        ForeignKey("tickets.id", ondelete="CASCADE"), index=True
    )
    from_status: Mapped[Status] = mapped_column(_enum(Status, "status_change_from"))
    to_status: Mapped[Status] = mapped_column(_enum(Status, "status_change_to"))
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    ticket: Mapped[Ticket] = relationship(back_populates="status_changes")
    changed_by: Mapped[User] = relationship()
