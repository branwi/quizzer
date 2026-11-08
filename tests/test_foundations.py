import pytest
from sqlalchemy import func, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.database import create_tables, make_engine
from app.models import AssignedProblem, Role, User


def test_data_persists_when_database_is_reopened(tmp_path):
    engine = make_engine("sqlite:///" + (tmp_path / "problems.db").as_posix())
    try:
        create_tables(engine)
        with Session(engine) as db:
            db.add(User(first_name="Maya", grade="6", role=Role.STUDENT))
            db.commit()
        engine.dispose()
        create_tables(engine)
        with Session(engine) as db:
            assert db.scalar(select(func.count()).select_from(User)) == 1
            assert db.scalar(select(User.first_name)) == "Maya"
    finally:
        engine.dispose()


def test_foreign_keys_reject_missing_assignment_references(db):
    db.add(AssignedProblem(student_id=999, question_id=999))
    with pytest.raises(IntegrityError):
        db.flush()


def test_name_grade_pair_is_unique_across_roles(db):
    db.add(User(first_name="Same", grade="12", role=Role.STUDENT))
    db.commit()
    db.add(User(first_name="Same", grade="12", role=Role.TEACHER))
    with pytest.raises(IntegrityError):
        db.flush()


def test_no_attempt_or_answer_tables_are_created(engine):
    assert set(inspect(engine).get_table_names()) == {"profiles", "problems", "assigned_problems"}


def test_settings_read_environment(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///other.db")
    settings = Settings(_env_file=None)
    assert settings.database_url == "sqlite:///other.db"
