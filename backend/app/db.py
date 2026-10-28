"""Database engine, session factory and the declarative Base for all models."""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    """Parent class for every SQLAlchemy model (defined in app/models.py)."""


engine = create_engine(get_settings().database_url, pool_pre_ping=True)

# expire_on_commit=False lets routers return ORM objects after commit without a reload query.
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request, always closed afterwards."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
