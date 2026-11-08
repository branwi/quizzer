from typing import Annotated

from fastapi import APIRouter, Path, Query

from app.dependencies import CurrentStudent, DbSession
from app.schemas import AnswerFeedback, CheckAnswer, QuestionFilters, QuestionForStudent
from app.services import questions

router = APIRouter(prefix="/bank/questions", tags=["problem bank"])
QuestionId = Annotated[int, Path(ge=1, le=2**63 - 1)]


@router.get("", response_model=list[QuestionForStudent])
def list_questions(filters: Annotated[QuestionFilters, Query()], db: DbSession):
    return questions.list_questions(db, filters)


@router.get("/{question_id}", response_model=QuestionForStudent)
def get(question_id: QuestionId, db: DbSession):
    return questions.get(db, question_id)


@router.post("/{question_id}/check", response_model=AnswerFeedback)
def check(question_id: QuestionId, data: CheckAnswer, _user: CurrentStudent, db: DbSession):
    return questions.check_answer(db, question_id, data)
