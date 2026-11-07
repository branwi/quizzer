from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, UTCDateTime, utc_now


class Role(StrEnum):
    TEACHER = "teacher"
    STUDENT = "student"


class QuestionType(StrEnum):
    MCQ = "mcq"
    TRUE_FALSE = "true_false"
    SHORT_ANSWER = "short_answer"


class QuizKind(StrEnum):
    ASSIGNED = "assigned"
    SELF_MADE = "self_made"


class QuizStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"


def enum_column(enum_type):
    # Store lowercase enum values; Pydantic validates incoming values.
    return Enum(
        enum_type,
        values_callable=lambda members: [member.value for member in members],
        native_enum=False,
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(enum_column(Role))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    type: Mapped[QuestionType] = mapped_column(enum_column(QuestionType))
    text: Mapped[str] = mapped_column(Text)
    choices: Mapped[list[dict[str, str]] | None] = mapped_column(JSON(none_as_null=True))
    correct_answer: Mapped[Any] = mapped_column(JSON, nullable=False)
    explanation: Mapped[str | None] = mapped_column(Text)
    topic: Mapped[str] = mapped_column(String(120), index=True)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, onupdate=utc_now)


class Quiz(Base):
    __tablename__ = "quizzes"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(200))
    kind: Mapped[QuizKind] = mapped_column(enum_column(QuizKind))
    due_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    max_attempts: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[QuizStatus] = mapped_column(enum_column(QuizStatus), default=QuizStatus.DRAFT)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)


class QuizAssignment(Base):
    __tablename__ = "quiz_assignments"

    quiz_id: Mapped[int] = mapped_column(ForeignKey("quizzes.id"), primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True, index=True)
    assigned_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)


class QuizQuestion(Base):
    __tablename__ = "quiz_questions"
    __table_args__ = (CheckConstraint("points > 0", name="ck_quiz_question_points"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    quiz_id: Mapped[int] = mapped_column(ForeignKey("quizzes.id"))
    question_id: Mapped[int | None] = mapped_column(ForeignKey("questions.id", ondelete="SET NULL"))
    position: Mapped[int] = mapped_column(Integer)
    points: Mapped[int] = mapped_column(Integer, default=1)
    # Publishing copies question content into this snapshot.
    snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON(none_as_null=True))


class Attempt(Base):
    __tablename__ = "attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    quiz_id: Mapped[int] = mapped_column(ForeignKey("quizzes.id"))
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    submitted_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    score: Mapped[int | None] = mapped_column(Integer)
    max_score: Mapped[int] = mapped_column(Integer)


class Answer(Base):
    __tablename__ = "answers"
    __table_args__ = (
        UniqueConstraint("attempt_id", "quiz_question_id", name="uq_answer_attempt_question"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    attempt_id: Mapped[int] = mapped_column(ForeignKey("attempts.id"))
    quiz_question_id: Mapped[int] = mapped_column(ForeignKey("quiz_questions.id"))
    quiz_id: Mapped[int] = mapped_column(ForeignKey("quizzes.id"))
    response: Mapped[Any] = mapped_column(JSON(none_as_null=True), nullable=True)
    is_correct: Mapped[bool] = mapped_column(Boolean)
    points_awarded: Mapped[int] = mapped_column(Integer)
