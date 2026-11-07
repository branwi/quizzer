from copy import deepcopy
from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, inspect, select, text
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session

from app.config import Settings
from app.database import create_tables, make_engine
from app.models import (
    Answer,
    Attempt,
    Question,
    Quiz,
    QuizAssignment,
    QuizKind,
    QuizQuestion,
    Role,
    User,
)
from app.security import verify_password
from scripts.seed import DEMO_EMAILS, DEMO_PASSWORD, seed, table_counts


def test_all_tables_created_and_queryable(engine, db):
    expected = {
        "users",
        "questions",
        "quizzes",
        "quiz_questions",
        "quiz_assignments",
        "attempts",
        "answers",
    }
    assert set(inspect(engine).get_table_names()) == expected
    assert table_counts(db) == dict.fromkeys(expected, 0)
    create_tables(engine)  # Startup is safe on an existing schema.


def test_foreign_keys_enabled_on_every_connection(tmp_path):
    engine = make_engine(f"sqlite:///{(tmp_path / 'connections.db').as_posix()}")
    try:
        with engine.connect() as first, engine.connect() as second:
            assert first.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
            assert second.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
    finally:
        engine.dispose()


def test_seed_is_repeatable_and_hashes_passwords(seeded):
    assert table_counts(seeded) == {
        "users": 3,
        "questions": 3,
        "quizzes": 1,
        "quiz_questions": 3,
        "quiz_assignments": 2,
        "attempts": 1,
        "answers": 3,
    }
    teacher = seeded.scalar(select(User).where(User.role == Role.TEACHER))
    before = teacher.password_hash
    assert before.startswith("$argon2id$")
    assert verify_password(DEMO_PASSWORD, before)
    assert not verify_password("wrong-password", before)
    assert seed(seeded) is False
    assert teacher.password_hash == before
    assert table_counts(seeded)["answers"] == 3
    attempt = seeded.scalar(select(Attempt))
    answers = seeded.scalars(select(Answer)).all()
    assert sum(answer.points_awarded for answer in answers) == attempt.score == 2


def test_seed_refuses_conflicting_student_without_writes(db):
    db.add(User(name="Existing", email=DEMO_EMAILS[1], role=Role.STUDENT, password_hash="x"))
    db.commit()
    with pytest.raises(ValueError, match="already exists"):
        seed(db)
    assert table_counts(db)["users"] == 1
    assert table_counts(db)["questions"] == 0


def test_dangling_foreign_key_rejected(db):
    db.add(QuizAssignment(quiz_id=999, student_id=999))
    with pytest.raises(IntegrityError):
        db.flush()


def test_snapshots_survive_source_edit_and_delete(seeded):
    link = seeded.scalar(select(QuizQuestion).order_by(QuizQuestion.position))
    original = deepcopy(link.snapshot)
    question = seeded.get(Question, link.question_id)
    question.text = "Edited prompt"
    question.correct_answer = "b"
    seeded.commit()
    seeded.refresh(link)
    assert link.snapshot == original
    seeded.delete(question)
    seeded.commit()
    seeded.refresh(link)
    assert link.question_id is None
    assert link.snapshot == original
    assert table_counts(seeded)["answers"] == 3


def test_deleting_quiz_with_history_is_rejected(seeded):
    quiz = seeded.scalar(select(Quiz))
    with pytest.raises(IntegrityError):
        seeded.execute(delete(Quiz).where(Quiz.id == quiz.id))


def test_duplicate_assignments_rejected(seeded):
    existing = seeded.scalar(select(QuizAssignment))
    # Direct SQL avoids an ORM identity-map warning for the same composite key.
    with pytest.raises(IntegrityError):
        seeded.execute(
            text("INSERT INTO quiz_assignments VALUES (:quiz, :student, :date)"),
            {"quiz": existing.quiz_id, "student": existing.student_id, "date": "2026-11-07"},
        )


def test_duplicate_answers_rejected(seeded):
    answer = seeded.scalar(select(Answer))
    seeded.add(
        Answer(
            attempt_id=answer.attempt_id,
            quiz_id=answer.quiz_id,
            quiz_question_id=answer.quiz_question_id,
            response=None,
            is_correct=False,
            points_awarded=0,
        )
    )
    with pytest.raises(IntegrityError):
        seeded.flush()


def test_cross_quiz_answer_rejected(seeded):
    first_attempt = seeded.scalar(select(Attempt))
    first_quiz = seeded.get(Quiz, first_attempt.quiz_id)
    other_quiz = Quiz(owner_id=first_quiz.owner_id, title="Other", kind=QuizKind.ASSIGNED)
    seeded.add(other_quiz)
    seeded.flush()
    other_link = QuizQuestion(quiz_id=other_quiz.id, position=0)
    seeded.add(other_link)
    seeded.flush()
    seeded.add(
        Answer(
            attempt_id=first_attempt.id,
            quiz_id=first_quiz.id,
            quiz_question_id=other_link.id,
            response=None,
            is_correct=False,
            points_awarded=0,
        )
    )
    with pytest.raises(IntegrityError):
        seeded.flush()


def test_quiz_defaults_distinguish_unlimited_and_unspecified(seeded):
    owner = seeded.scalar(select(User.id))
    assigned = Quiz(owner_id=owner, title="Assigned", kind=QuizKind.ASSIGNED)
    practice = Quiz(owner_id=owner, title="Practice", kind=QuizKind.SELF_MADE)
    unlimited = Quiz(owner_id=owner, title="Unlimited", kind=QuizKind.ASSIGNED, max_attempts=None)
    seeded.add_all([assigned, practice, unlimited])
    seeded.flush()
    assert assigned.max_attempts == 1
    assert practice.max_attempts is None
    assert unlimited.max_attempts is None


@pytest.mark.parametrize("limit", [0, -1])
def test_invalid_attempt_limit_rejected(seeded, limit):
    quiz = seeded.scalar(select(Quiz))
    quiz.max_attempts = limit
    with pytest.raises(IntegrityError):
        seeded.flush()


def test_role_enum_enforced_by_database(db):
    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO users (name, email, password_hash, role, created_at) "
                "VALUES ('X', 'x@test', 'hash', 'admin', '2026-11-07')"
            )
        )


def test_score_bounds_enforced(seeded):
    attempt = seeded.scalar(select(Attempt))
    attempt.score = attempt.max_score + 1
    with pytest.raises(IntegrityError):
        seeded.flush()


def test_timestamps_round_trip_as_utc(db):
    local_time = datetime(2026, 11, 7, 10, 30, tzinfo=timezone(timedelta(hours=-5)))
    user = User(
        name="UTC",
        email="utc@example.test",
        role=Role.STUDENT,
        password_hash="test-hash",
        created_at=local_time,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    assert user.created_at == datetime(2026, 11, 7, 15, 30, tzinfo=UTC)
    assert user.created_at.tzinfo == UTC


def test_naive_datetimes_rejected(db):
    db.add(
        User(
            name="Naive",
            email="naive@example.test",
            role=Role.STUDENT,
            password_hash="test-hash",
            created_at=datetime(2026, 11, 7),
        )
    )
    with pytest.raises(StatementError, match="must include a timezone"):
        db.flush()


def test_seed_persists_across_connections(tmp_path):
    engine = make_engine(f"sqlite:///{(tmp_path / 'persistent.db').as_posix()}")
    try:
        create_tables(engine)
        with Session(engine) as db, db.begin():
            seed(db)
        engine.dispose()
        with Session(engine) as db:
            assert table_counts(db)["answers"] == 3
            assert seed(db) is False
    finally:
        engine.dispose()


def test_environment_configuration(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///override.db")
    monkeypatch.setenv("ACCESS_TOKEN_MINUTES", "15")
    monkeypatch.setenv("SECRET_KEY", "a-test-secret")
    settings = Settings(_env_file=None)
    assert settings.database_url == "sqlite:///override.db"
    assert settings.access_token_minutes == 15
    assert settings.secret_key.get_secret_value() == "a-test-secret"
