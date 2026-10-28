"""Shared test fixtures.

Tests run against real PostgreSQL (TEST_DATABASE_URL), not SQLite: the
optimistic-lock and race tests depend on Postgres row locking, and CHECK
constraints / ILIKE behave as in production.

Isolation: tables live in their own "test" schema (search_path in the URL) and
are TRUNCATEd after every test. We truncate rather than wrap each test in a
rolled-back transaction because the race tests need several real connections
that see each other's commits.
"""

from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.db import Base, get_db
from app.main import app
from app.models import Priority, Role, Status, Ticket, TicketStatusChange, User
from app.auth import create_access_token, hash_password

PASSWORD = "test-password"
# bcrypt is deliberately slow; hash once per run instead of once per user per test.
PASSWORD_HASH = hash_password(PASSWORD)


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    settings = get_settings()
    url = settings.test_database_url
    if not url or url == settings.database_url:
        pytest.exit("TEST_DATABASE_URL must be set and differ from DATABASE_URL", returncode=2)

    eng = create_engine(url)
    with eng.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS test"))
        schema = conn.execute(text("SELECT current_schema()")).scalar()
    if schema != "test":
        pytest.exit(f"Refusing to run: test connection uses schema {schema!r}, expected 'test'", returncode=2)

    Base.metadata.drop_all(eng)  # start clean even if a previous run crashed
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture
def session_factory(engine: Engine) -> Iterator[sessionmaker[Session]]:
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    yield factory
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
def db(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    """A session for arranging data and asserting on DB state directly."""
    with session_factory() as session:
        yield session


@pytest.fixture
def client(session_factory: sessionmaker[Session]) -> Iterator[TestClient]:
    """API client whose requests each get their own session on the test DB."""

    def override_get_db() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


# --- Users -------------------------------------------------------------------------


def _user(db: Session, email: str, role: Role) -> User:
    user = User(email=email, full_name=email.split("@")[0].title(), role=role, hashed_password=PASSWORD_HASH)
    db.add(user)
    db.commit()
    return user


@pytest.fixture
def alice(db: Session) -> User:
    return _user(db, "alice@test.io", Role.USER)


@pytest.fixture
def bob(db: Session) -> User:
    return _user(db, "bob@test.io", Role.USER)


@pytest.fixture
def sam(db: Session) -> User:
    return _user(db, "sam@test.io", Role.AGENT)


@pytest.fixture
def priya(db: Session) -> User:
    return _user(db, "priya@test.io", Role.AGENT)


def auth(user: User) -> dict[str, str]:
    """Authorization header for `user` (login itself is covered in test_auth_privacy)."""
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


# --- Tickets -----------------------------------------------------------------------


@pytest.fixture
def make_ticket(db: Session) -> Callable[..., Ticket]:
    """Insert a ticket directly in any state, e.g. make_ticket(alice, status=RESOLVED, assignee=sam).

    Arranging state in the DB (not through the API) keeps each test focused on
    the one action it is checking.
    """

    def _make(
        creator: User,
        *,
        title: str = "Printer is broken",
        description: str = "It prints blank pages",
        priority: Priority = Priority.MEDIUM,
        status: Status = Status.OPEN,
        assignee: User | None = None,
    ) -> Ticket:
        ticket = Ticket(
            title=title,
            description=description,
            priority=priority,
            status=status,
            creator=creator,
            assignee=assignee,
        )
        db.add(ticket)
        db.commit()
        return ticket

    return _make


def history(db: Session, ticket_id: int) -> list[TicketStatusChange]:
    db.expire_all()
    return list(db.get(Ticket, ticket_id).status_changes)
