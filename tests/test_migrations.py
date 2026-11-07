import sqlite3
import subprocess
import sys

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.database import Base, create_tables, make_engine
from scripts.seed import seed, table_counts


def run_migration(path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + path.as_posix())
    return subprocess.run(
        [sys.executable, "-m", "scripts.migrate"], capture_output=True, text=True, timeout=30
    )


def test_fresh_migration_matches_models_and_is_repeatable(tmp_path, monkeypatch):
    path = tmp_path / "fresh.db"
    result = run_migration(path, monkeypatch)
    assert result.returncode == 0, result.stderr
    engine = make_engine("sqlite:///" + path.as_posix())
    try:
        assert set(inspect(engine).get_table_names()) == set(Base.metadata.tables) | {
            "alembic_version"
        }
        with engine.connect() as connection:
            assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
        assert run_migration(path, monkeypatch).returncode == 0
    finally:
        engine.dispose()


def test_existing_seed_is_backed_up_and_adopted_without_data_loss(tmp_path, monkeypatch):
    path = tmp_path / "existing.db"
    engine = make_engine("sqlite:///" + path.as_posix())
    try:
        create_tables(engine)
        with Session(engine) as db, db.begin():
            seed(db)
            before = table_counts(db)
        result = run_migration(path, monkeypatch)
        assert result.returncode == 0, result.stderr
        assert len(list(tmp_path.glob("existing.db.pre-alembic-*.db"))) == 1
        with Session(engine) as db:
            assert table_counts(db) == before
        assert run_migration(path, monkeypatch).returncode == 0
        assert len(list(tmp_path.glob("existing.db.pre-alembic-*.db"))) == 1
    finally:
        engine.dispose()


def test_unknown_schema_is_refused_without_stamping(tmp_path, monkeypatch):
    path = tmp_path / "unknown.db"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE unrelated (id INTEGER)")
    result = run_migration(path, monkeypatch)
    assert result.returncode != 0
    assert "differs from the baseline" in result.stderr
    with sqlite3.connect(path) as db:
        assert (
            db.execute("SELECT name FROM sqlite_master WHERE name='alembic_version'").fetchone()
            is None
        )
