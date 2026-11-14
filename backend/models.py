from enum import StrEnum

from sqlalchemy import JSON, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class Role(StrEnum):
    TEACHER = "teacher"
    STUDENT = "student"


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
    text: Mapped[str] = mapped_column(Text)
    topic: Mapped[str] = mapped_column(String(120))
    correct_answer: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    explanation: Mapped[str | None] = mapped_column(Text)


class AssignedProblem(Base):
    __tablename__ = "assigned_problems"

    student_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"), primary_key=True)
    question_id: Mapped[int] = mapped_column(
        ForeignKey("problems.id", ondelete="CASCADE"), primary_key=True
    )
