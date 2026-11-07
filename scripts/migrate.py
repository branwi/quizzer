"""Upgrade tracked schemas; back up and adopt an unchanged pre-Alembic SQLite database."""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import inspect

from alembic import command
from app import models  # noqa: F401
from app.config import get_settings
from app.database import Base, make_engine


def migrate() -> None:
    engine = make_engine(get_settings().database_url)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    try:
        tables = set(inspect(engine).get_table_names())
        if tables and "alembic_version" not in tables:
            with engine.connect() as connection:
                differences = compare_metadata(
                    MigrationContext.configure(connection), Base.metadata
                )
            if differences:
                raise RuntimeError(
                    "Existing schema differs from the baseline. "
                    "Back up and review it before migration."
                )
            if engine.dialect.name == "sqlite" and engine.url.database not in (
                None,
                "",
                ":memory:",
            ):
                source = Path(engine.url.database).resolve()
                stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
                backup = source.with_name(source.name + f".pre-alembic-{stamp}.db")
                assert backup.parent == source.parent
                with sqlite3.connect(source) as original, sqlite3.connect(backup) as target:
                    original.backup(target)
                print(f"Saved baseline backup: {backup.name}")
            command.stamp(config, "0001")
        command.upgrade(config, "head")
        print("Database migrations are current.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    migrate()
