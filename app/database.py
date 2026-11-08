from collections.abc import Iterator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def make_engine(database_url: str) -> Engine:
    options = {"connect_args": {"check_same_thread": False}}
    if database_url in ("sqlite://", "sqlite:///:memory:"):
        options["poolclass"] = StaticPool
    engine = create_engine(database_url, **options)

    @event.listens_for(engine, "connect")
    def configure_sqlite(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")
        # SQLite's built-in lower() only handles ASCII; casefold also handles names like Émile.
        connection.create_function("casefold", 1, str.casefold, deterministic=True)

    return engine


engine = make_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def create_tables(bind: Engine = engine) -> None:
    from app import models  # noqa: F401

    Base.metadata.create_all(bind)


def get_db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session
