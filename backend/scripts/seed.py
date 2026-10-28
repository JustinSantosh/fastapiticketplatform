"""Load demo accounts and a few tickets.  Run from backend/:

    python -m scripts.seed           # add demo data (does nothing if already present)
    python -m scripts.seed --reset   # wipe ALL rows in the app's tables, then re-seed

DEMO ONLY - these passwords are public in the README; never use them for real accounts.
"""

import sys

from sqlalchemy import select, text

from app.db import Base, SessionLocal
from app.models import Comment, Priority, Role, Status, Ticket, TicketStatusChange, User
from app.auth import hash_password

DEMO_PASSWORD = "Password123!"

DEMO_USERS = [
    ("alice@example.com", "Alice Johnson", Role.USER),
    ("bob@example.com", "Bob Smith", Role.USER),
    ("agent.sam@example.com", "Sam Rivera", Role.AGENT),
    ("agent.priya@example.com", "Priya Patel", Role.AGENT),
]


def reset() -> None:
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with SessionLocal() as db:
        db.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        db.commit()
    print("Removed all users, tickets, comments and history.")


def seed() -> None:
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email == DEMO_USERS[0][0])):
            print("Demo data already present - nothing to do.")
            return

        users = {
            email: User(email=email, full_name=name, role=role, hashed_password=hash_password(DEMO_PASSWORD))
            for email, name, role in DEMO_USERS
        }
        db.add_all(users.values())
        db.flush()  # assigns ids

        alice, bob = users["alice@example.com"], users["bob@example.com"]
        sam, priya = users["agent.sam@example.com"], users["agent.priya@example.com"]

        open_ticket = Ticket(
            title="Cannot reset my password",
            description="The reset email never arrives. I checked spam too.",
            priority=Priority.HIGH,
            creator=alice,
        )
        in_progress = Ticket(
            title="Invoice shows wrong billing address",
            description="My March invoice still has my old office address.",
            priority=Priority.MEDIUM,
            creator=alice,
            assignee=sam,
            status=Status.IN_PROGRESS,
            status_changes=[
                TicketStatusChange(from_status=Status.OPEN, to_status=Status.IN_PROGRESS, changed_by=sam)
            ],
            comments=[Comment(author=sam, body="Looking into this now - will update the address today.")],
        )
        resolved = Ticket(
            title="Feature request: dark mode",
            description="Would love a dark theme for the dashboard.",
            priority=Priority.LOW,
            creator=bob,
            assignee=priya,
            status=Status.RESOLVED,
            status_changes=[
                TicketStatusChange(from_status=Status.OPEN, to_status=Status.IN_PROGRESS, changed_by=priya),
                TicketStatusChange(from_status=Status.IN_PROGRESS, to_status=Status.RESOLVED, changed_by=priya),
            ],
        )
        db.add_all([open_ticket, in_progress, resolved])
        db.commit()

        print(f"Seeded {len(users)} users and 3 tickets. Demo password for all: {DEMO_PASSWORD}")


if __name__ == "__main__":
    if "--reset" in sys.argv:
        reset()
    seed()
