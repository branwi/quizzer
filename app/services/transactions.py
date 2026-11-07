from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.services.errors import StateConflict


@contextmanager
def write_transaction(db: Session) -> Iterator[None]:
    """Own a fresh unit of work, serializing SQLite checks and writes together.

    A request may already have a read transaction from authentication. End it
    first so a waiting writer sees current state, not an earlier read snapshot.
    Callers must commit their own pending work before entering this service.
    """
    if db.new or db.dirty or db.deleted:
        raise RuntimeError("Workflow services require a session without pending changes")
    db.rollback()
    try:
        if db.get_bind().dialect.name == "sqlite":
            db.execute(text("BEGIN IMMEDIATE"))
        else:
            db.begin()
        yield
        db.commit()
    except OperationalError as exc:
        db.rollback()
        if db.get_bind().dialect.name == "sqlite" and "locked" in str(exc.orig).lower():
            raise StateConflict("Database is busy; retry the request") from None
        raise
    except Exception:
        db.rollback()
        raise
