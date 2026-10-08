"""SQLAlchemy engine, session dependency and model initialization."""

from collections.abc import Generator

from fastapi import Request
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    """Base for SQLAlchemy models."""


def create_database(database_url: str) -> tuple[Engine, sessionmaker[Session]]:
    """Create an engine and session factory for the configured database."""
    connect_args = (
        {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    )
    engine = create_engine(database_url, connect_args=connect_args)

    if database_url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def enable_sqlite_foreign_keys(dbapi_connection: object, _: object) -> None:
            cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    return engine, factory


def get_db(request: Request) -> Generator[Session, None, None]:
    """Yield a request-scoped database session."""
    factory: sessionmaker[Session] = request.app.state.session_factory
    session = factory()
    session.info["settings"] = request.app.state.settings
    try:
        yield session
    finally:
        session.close()
