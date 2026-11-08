from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Question, QuestionType
from app.schemas import AnswerFeedback, CheckAnswer, QuestionCreate, QuestionFilters
from app.services.errors import InvalidInput, ResourceNotFound
from app.services.grading import grade


def get(db: Session, question_id: int) -> Question:
    question = db.get(Question, question_id)
    if question is None:
        raise ResourceNotFound("Question not found")
    return question


def list_questions(db: Session, filters: QuestionFilters) -> list[Question]:
    statement = select(Question)
    if filters.q:
        statement = statement.where(
            or_(
                Question.text.icontains(filters.q, autoescape=True),
                Question.topic.icontains(filters.q, autoescape=True),
            )
        )
    if filters.topic:
        statement = statement.where(Question.topic == filters.topic)
    if filters.type:
        statement = statement.where(Question.type == filters.type)
    return list(db.scalars(statement.order_by(Question.id)))


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
    response = data.response
    if response is not None:
        if question.type == QuestionType.TRUE_FALSE:
            if type(response) is not bool:
                raise InvalidInput("True/false responses must be JSON booleans or null")
        elif not isinstance(response, str):
            raise InvalidInput("Text and choice responses must be strings or null")
        if question.type == QuestionType.MCQ and response != "":
            if response not in {choice["id"] for choice in question.choices}:
                raise InvalidInput("Response must be one of this question's choice ids")
    return AnswerFeedback(
        question_id=question.id,
        is_correct=grade(
            {"type": question.type, "correct_answer": question.correct_answer}, response
        ),
        correct_answer=question.correct_answer,
        explanation=question.explanation,
    )
