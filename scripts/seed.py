"""Create a complete fixture once. Never reset or overwrite an existing database."""

from copy import deepcopy
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import Base, SessionLocal, create_tables, utc_now
from app.models import (
    Answer,
    Attempt,
    Question,
    QuestionType,
    Quiz,
    QuizAssignment,
    QuizKind,
    QuizQuestion,
    QuizStatus,
    Role,
    User,
)
from app.security import hash_password

DEMO_PASSWORD = "quiz-demo-password"
DEMO_EMAILS = ("teacher@example.test", "alice@example.test", "bob@example.test")


def seed(db: Session) -> bool:
    """Caller owns the transaction. An existing demo teacher makes this a no-op."""
    if db.scalar(select(User.id).where(User.email == DEMO_EMAILS[0])) is not None:
        return False
    if db.scalar(select(User.id).where(User.email.in_(DEMO_EMAILS))) is not None:
        raise ValueError("A demo student email already exists; no demo data was changed.")

    teacher, alice, bob = [
        User(name=name, email=email, role=role, password_hash=hash_password(DEMO_PASSWORD))
        for name, email, role in zip(
            ("Demo Teacher", "Alice", "Bob"),
            DEMO_EMAILS,
            (Role.TEACHER, Role.STUDENT, Role.STUDENT),
            strict=True,
        )
    ]
    db.add_all([teacher, alice, bob])
    db.flush()
    questions = [
        Question(
            author_id=teacher.id,
            type=QuestionType.MCQ,
            text="What is the capital of France?",
            choices=[{"id": "a", "text": "Paris"}, {"id": "b", "text": "Rome"}],
            correct_answer="a",
            explanation="Paris is the capital of France.",
            topic="Geography",
            is_public=True,
        ),
        Question(
            author_id=teacher.id,
            type=QuestionType.TRUE_FALSE,
            text="An integer divisible by 2 is even.",
            correct_answer=True,
            explanation="Divisibility by 2 defines an even integer.",
            topic="Math",
            is_public=True,
        ),
        Question(
            author_id=teacher.id,
            type=QuestionType.SHORT_ANSWER,
            text="What is 2 + 2?",
            correct_answer=["4", "four"],
            explanation="Adding two and two gives four.",
            topic="Math",
            is_public=False,
        ),
    ]
    db.add_all(questions)
    quiz = Quiz(
        owner_id=teacher.id,
        title="Demo knowledge check",
        kind=QuizKind.ASSIGNED,
        status=QuizStatus.PUBLISHED,
    )
    db.add(quiz)
    db.flush()
    links = []
    for position, question in enumerate(questions):
        link = QuizQuestion(
            quiz_id=quiz.id,
            question_id=question.id,
            position=position,
            snapshot=deepcopy(
                {
                    "type": question.type.value,
                    "text": question.text,
                    "choices": question.choices,
                    "correct_answer": question.correct_answer,
                    "explanation": question.explanation,
                }
            ),
        )
        links.append(link)
    db.add_all(links)
    db.add_all([QuizAssignment(quiz_id=quiz.id, student_id=student.id) for student in (alice, bob)])
    now = utc_now()
    attempt = Attempt(
        quiz_id=quiz.id,
        student_id=alice.id,
        started_at=now - timedelta(minutes=5),
        submitted_at=now,
        score=2,
        max_score=3,
    )
    db.add(attempt)
    db.flush()
    # Fixed illustrative history, not a substitute for the future grading service.
    db.add_all(
        [
            Answer(
                attempt_id=attempt.id,
                quiz_id=quiz.id,
                quiz_question_id=link.id,
                response=response,
                is_correct=correct,
                points_awarded=int(correct),
            )
            for link, response, correct in zip(
                links, ("a", False, "four"), (True, False, True), strict=True
            )
        ]
    )
    db.flush()
    return True


def table_counts(db: Session) -> dict[str, int]:
    return {
        table.name: db.scalar(select(func.count()).select_from(table))
        for table in Base.metadata.sorted_tables
    }


def main() -> None:
    create_tables()
    with SessionLocal.begin() as db:
        created = seed(db)
        counts = table_counts(db)
    print("Created demo data." if created else "Demo data already exists; left unchanged.")
    for name, count in counts.items():
        print(f"{name}: {count}")
    print("Demo accounts: " + ", ".join(DEMO_EMAILS))
    print(f"Local demo password: {DEMO_PASSWORD} (use POST /api/auth/login)")


if __name__ == "__main__":
    main()
