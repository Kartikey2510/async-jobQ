"""Database engine and session helpers."""

from collections.abc import Generator
import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


def _database_url() -> str:
    if url := os.getenv("DATABASE_URL"):
        return url
    if sqlite_path := os.getenv("SQLITE_PATH"):
        Path(sqlite_path).parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{sqlite_path}"
    return f"sqlite:///{Path(__file__).resolve().parent.parent / 'jobs.db'}"


DATABASE_URL = _database_url()
_IS_SQLITE = DATABASE_URL.startswith("sqlite")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if _IS_SQLITE else {},
)

if _IS_SQLITE:

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:
        # WAL allows concurrent readers (HTTP) while a writer (worker) commits.
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    # Import models so metadata is registered before create_all.
    from app.models import orm  # noqa: F401

    Base.metadata.create_all(bind=engine)
