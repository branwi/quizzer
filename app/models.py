from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Role(StrEnum):
    TEACHER = "teacher"
    STUDENT = "student"


class QuestionType(StrEnum):
    MCQ = "mcq"
    TRUE_FALSE = "true_false"
    SHORT_ANSWER = "short_answer"


class User(Base):
    __tablename__ = "profiles"
    __table_args__ = (
        UniqueConstraint("first_name", "grade"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str] = mapped_column(String(120))
    grade: Mapped[str] = mapped_column(String(20))
    role: Mapped[str] = mapped_column(String(20))


class Question(Base):
    __tablename__ = "problems"

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String(20))
    text: Mapped[str] = mapped_column(Text)
    topic: Mapped[str] = mapped_column(String(120))
    choices: Mapped[list[dict[str, str]] | None] = mapped_column(JSON(none_as_null=True))
    correct_answer: Mapped[Any] = mapped_column(JSON, nullable=False)
    explanation: Mapped[str | None] = mapped_column(Text)


class AssignedProblem(Base):
    __tablename__ = "assigned_problems"

    student_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"), primary_key=True)
    question_id: Mapped[int] = mapped_column(
        ForeignKey("problems.id", ondelete="CASCADE"), primary_key=True
    )
