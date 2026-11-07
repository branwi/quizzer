from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import create_tables, make_engine
from app.models import Answer, Attempt, Quiz, QuizAssignment, User
from app.services import attempts, quizzes
from app.services.auth import public_user
from app.services.errors import StateConflict
from app.workflow_schemas import AssignmentCreate, AttemptSubmit
from scripts.seed import seed


@pytest.fixture
def race_data(tmp_path):
    engine = make_engine(f"sqlite:///{(tmp_path / 'races.db').as_posix()}")
    create_tables(engine)
    with Session(engine) as db:
        with db.begin():
            seed(db)
        bob = public_user(db.scalar(select(User).where(User.email == "bob@example.test")))
        teacher = public_user(db.scalar(select(User).where(User.email == "teacher@example.test")))
        quiz_id = db.scalar(select(Quiz.id))
    yield engine, bob, teacher, quiz_id
    engine.dispose()


def concurrently(engine, operation):
    barrier = Barrier(2)

    def run():
        with Session(engine, expire_on_commit=False) as db:
            barrier.wait(timeout=10)
            return operation(db)

    with ThreadPoolExecutor(max_workers=2) as workers:
        futures = [workers.submit(run) for _ in range(2)]
        return [future.result(timeout=20) for future in futures]


def test_simultaneous_starts_resume_one_attempt(race_data):
    engine, bob, _teacher, quiz_id = race_data
    results = concurrently(engine, lambda db: attempts.start(db, bob, quiz_id))
    assert {result[0].id for result in results} == {results[0][0].id}
    assert sorted(result[1] for result in results) == [False, True]
    with Session(engine) as db:
        assert (
            db.scalar(select(func.count()).select_from(Attempt).where(Attempt.student_id == bob.id))
            == 1
        )


def test_simultaneous_submits_grade_once_and_limit_remains_enforced(race_data):
    engine, bob, _teacher, quiz_id = race_data
    with Session(engine) as db:
        active, _ = attempts.start(db, bob, quiz_id)
    payload = AttemptSubmit.model_validate(
        {
            "answers": [
                {"quiz_question_id": q.id, "response": response}
                for q, response in zip(active.questions, ("a", True, "four"), strict=True)
            ]
        }
    )

    def submit(db):
        try:
            return attempts.submit(db, bob, active.id, payload)
        except StateConflict as exc:
            assert "already been submitted" in str(exc)
            return None

    results = concurrently(engine, submit)
    assert sum(result is not None for result in results) == 1
    assert next(result for result in results if result is not None).score == 3
    with Session(engine) as db:
        assert (
            db.scalar(
                select(func.count()).select_from(Answer).where(Answer.attempt_id == active.id)
            )
            == 3
        )

    def try_start(db):
        with pytest.raises(StateConflict, match="Maximum attempts"):
            attempts.start(db, bob, quiz_id)

    concurrently(engine, try_start)
    with Session(engine) as db:
        assert (
            db.scalar(select(func.count()).select_from(Attempt).where(Attempt.student_id == bob.id))
            == 1
        )


def test_simultaneous_assignment_is_idempotent(race_data):
    engine, bob, teacher, quiz_id = race_data
    with Session(engine) as db:
        row = db.get(QuizAssignment, (quiz_id, bob.id))
        db.delete(row)
        db.commit()
    data = AssignmentCreate(student_ids=[bob.id])
    results = concurrently(engine, lambda db: quizzes.assign(db, teacher, quiz_id, data))
    assert results[0] == results[1]
    with Session(engine) as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(QuizAssignment)
                .where(
                    QuizAssignment.quiz_id == quiz_id,
                    QuizAssignment.student_id == bob.id,
                )
            )
            == 1
        )
