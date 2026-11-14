from collections.abc import Iterator

from sqlalchemy import Engine, create_engine, event, inspect
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.config import get_settings


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
    from backend import models  # noqa: F401

    Base.metadata.create_all(bind)
    # Earlier databases stored several question formats. Existing short answers
    # keep their IDs, content, and assignment links when the unused columns go.
    with bind.begin() as connection:
        columns = {column["name"] for column in inspect(connection).get_columns("problems")}
        if not {"type", "choices"} & columns:
            return
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        if "type" in columns:
            unsupported = connection.exec_driver_sql(
                "SELECT count(*) FROM problems WHERE type IS NULL OR type != 'short_answer'"
            ).scalar_one()
            if unsupported:
                raise ValueError("Convert existing questions to short answers before upgrading")
        if "choices" in columns:
            with_choices = connection.exec_driver_sql(
                "SELECT count(*) FROM problems WHERE choices IS NOT NULL AND choices != 'null'"
            ).scalar_one()
            if with_choices:
                raise ValueError("Convert existing question choices before upgrading")
        for column in ("type", "choices"):
            if column in columns:
                connection.exec_driver_sql(f"ALTER TABLE problems DROP COLUMN {column}")


def get_db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session
