from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import Question
from app.schemas import (
    QuestionCreate,
    QuestionFilters,
    QuestionForStudent,
    QuestionForTeacher,
    QuestionPage,
    UserPublic,
)
from app.services.access import require_teacher


class QuestionNotFound(Exception):
    pass


def for_student(question: Question) -> QuestionForStudent:
    # Explicit projection: never pass the ORM object or an answer key to a student view.
    return QuestionForStudent(
        id=question.id,
        author_id=question.author_id,
        type=question.type,
        text=question.text,
        choices=question.choices,
        topic=question.topic,
        is_public=question.is_public,
        created_at=question.created_at,
        updated_at=question.updated_at,
    )


def for_teacher(question: Question) -> QuestionForTeacher:
    return QuestionForTeacher(
        **for_student(question).model_dump(),
        correct_answer=question.correct_answer,
        explanation=question.explanation,
    )


def _own_question(db: Session, user: UserPublic, question_id: int) -> Question:
    require_teacher(user)
    question = db.scalar(
        select(Question).where(
            Question.id == question_id,
            Question.author_id == user.id,
        )
    )
    if question is None:
        raise QuestionNotFound
    return question


def create(db: Session, user: UserPublic, data: QuestionCreate) -> QuestionForTeacher:
    require_teacher(user)
    question = Question(author_id=user.id, **data.model_dump())
    db.add(question)
    db.commit()
    db.refresh(question)
    return for_teacher(question)


def get(db: Session, user: UserPublic, question_id: int) -> QuestionForTeacher:
    return for_teacher(_own_question(db, user, question_id))


def list_own(db: Session, user: UserPublic, filters: QuestionFilters) -> QuestionPage:
    require_teacher(user)
    conditions = [Question.author_id == user.id]
    if filters.q:
        conditions.append(
            or_(
                Question.text.icontains(filters.q, autoescape=True),
                Question.topic.icontains(filters.q, autoescape=True),
            )
        )
    if filters.topic:
        conditions.append(Question.topic == filters.topic)
    if filters.type is not None:
        conditions.append(Question.type == filters.type)
    if filters.is_public is not None:
        conditions.append(Question.is_public == filters.is_public)
    total = db.scalar(select(func.count()).select_from(Question).where(*conditions))
    rows = db.scalars(
        select(Question)
        .where(*conditions)
        .order_by(Question.created_at.desc(), Question.id.desc())
        .offset((filters.page - 1) * filters.page_size)
        .limit(filters.page_size)
    ).all()
    return QuestionPage(
        items=[for_teacher(question) for question in rows],
        total=total,
        page=filters.page,
        page_size=filters.page_size,
    )


def replace(
    db: Session, user: UserPublic, question_id: int, data: QuestionCreate
) -> QuestionForTeacher:
    question = _own_question(db, user, question_id)
    # PUT replaces the complete content, including clearing obsolete choices on a type change.
    for field, value in data.model_dump().items():
        setattr(question, field, value)
    db.commit()
    db.refresh(question)
    return for_teacher(question)


def delete(db: Session, user: UserPublic, question_id: int) -> None:
    question = _own_question(db, user, question_id)
    db.delete(question)
    db.commit()
