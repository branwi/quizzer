from datetime import UTC, datetime

import pytest
from sqlalchemy import func, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.database import Base, create_tables, make_engine
from app.models import QuizAssignment, Role, User


def test_create_all_creates_seven_queryable_tables(engine, db):
    assert set(inspect(engine).get_table_names()) == set(Base.metadata.tables)
    assert len(Base.metadata.tables) == 7
    for table in Base.metadata.sorted_tables:
        assert db.scalar(select(func.count()).select_from(table)) == 0
    create_tables(engine)  # Calling it again leaves existing tables alone.


def test_only_positive_points_have_a_database_check(engine):
    checks = [
        (name, check)
        for name in Base.metadata.tables
        for check in inspect(engine).get_check_constraints(name)
    ]
    assert len(checks) == 1
    assert checks[0][0] == "quiz_questions"


def test_foreign_keys_still_reject_missing_references(db):
    db.add(QuizAssignment(quiz_id=999, student_id=999))
    with pytest.raises(IntegrityError):
        db.flush()


def test_utc_datetimes_survive_sqlite_round_trip(db):
    user = User(
        name="UTC",
        email="utc@example.test",
        password_hash="unused",
        role=Role.STUDENT,
        created_at=datetime(2026, 11, 7, 15, 30, tzinfo=UTC),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    assert user.created_at == datetime(2026, 11, 7, 15, 30, tzinfo=UTC)
    assert user.created_at.tzinfo == UTC


def test_data_persists_after_reopening_database(tmp_path):
    engine = make_engine("sqlite:///" + (tmp_path / "quiz.db").as_posix())
    try:
        create_tables(engine)
        with Session(engine) as db:
            db.add(
                User(
                    name="Saved",
                    email="saved@example.test",
                    role=Role.STUDENT,
                    password_hash="unused",
                )
            )
            db.commit()
        engine.dispose()
        with Session(engine) as db:
            assert db.scalar(select(User.name)) == "Saved"
    finally:
        engine.dispose()


def test_settings_read_environment(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///other.db")
    monkeypatch.setenv("ACCESS_TOKEN_MINUTES", "15")
    settings = Settings(_env_file=None)
    assert settings.database_url == "sqlite:///other.db"
    assert settings.access_token_minutes == 15
