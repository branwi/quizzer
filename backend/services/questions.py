from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models import Question
from backend.schemas import AnswerFeedback, CheckAnswer, QuestionCreate, QuestionFilters
from backend.services.errors import ResourceNotFound
from backend.services.grading import grade


def get(db: Session, question_id: int) -> Question:
    question = db.get(Question, question_id)
    if question is None:
        raise ResourceNotFound("Question not found")
    return question


def list_topics(db: Session) -> list[str]:
    return list(db.scalars(select(Question.topic).distinct().order_by(Question.topic)))


def list_questions(db: Session, filters: QuestionFilters) -> tuple[list[Question], int, int]:
    statement = select(Question)
    if filters.topic:
        statement = statement.where(Question.topic == filters.topic)
    total = db.scalar(select(func.count()).select_from(statement.subquery()))
    last_page = max(1, (total + filters.page_size - 1) // filters.page_size)
    page = min(filters.page, last_page)
    items = list(
        db.scalars(
            statement.order_by(Question.id)
            .limit(filters.page_size)
            .offset((page - 1) * filters.page_size)
        )
    )
    return items, total, page


def create(db: Session, data: QuestionCreate) -> Question:
    question = Question(**data.model_dump())
    db.add(question)
    db.commit()
    db.refresh(question)
    return question


def replace(db: Session, question_id: int, data: QuestionCreate) -> Question:
    question = get(db, question_id)
    for field, value in data.model_dump().items():
        setattr(question, field, value)
    db.commit()
    db.refresh(question)
    return question


def delete(db: Session, question_id: int) -> None:
    db.delete(get(db, question_id))
    db.commit()


def check_answer(db: Session, question_id: int, data: CheckAnswer) -> AnswerFeedback:
    question = get(db, question_id)
    return AnswerFeedback(
        question_id=question.id,
        is_correct=grade(question.correct_answer, data.response),
        correct_answer=question.correct_answer,
        explanation=question.explanation,
    )
