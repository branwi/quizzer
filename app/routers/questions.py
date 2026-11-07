from typing import Annotated

from fastapi import APIRouter, Path, Query, Response, status

from app.dependencies import CurrentTeacher, DbSession
from app.routers.auth import no_store
from app.schemas import QuestionCreate, QuestionFilters, QuestionForTeacher, QuestionPage
from app.services import questions

router = APIRouter(prefix="/questions", tags=["questions"])
QuestionId = Annotated[int, Path(ge=1, le=2**63 - 1)]


@router.post("", response_model=QuestionForTeacher, status_code=status.HTTP_201_CREATED)
def create(
    data: QuestionCreate, user: CurrentTeacher, db: DbSession, response: Response
) -> QuestionForTeacher:
    no_store(response)
    return questions.create(db, user, data)


@router.get("", response_model=QuestionPage)
def list_own(
    filters: Annotated[QuestionFilters, Query()],
    user: CurrentTeacher,
    db: DbSession,
    response: Response,
) -> QuestionPage:
    no_store(response)
    return questions.list_own(db, user, filters)


@router.get("/{question_id}", response_model=QuestionForTeacher)
def get(
    question_id: QuestionId, user: CurrentTeacher, db: DbSession, response: Response
) -> QuestionForTeacher:
    no_store(response)
    return questions.get(db, user, question_id)


@router.put("/{question_id}", response_model=QuestionForTeacher)
def replace(
    question_id: QuestionId,
    data: QuestionCreate,
    user: CurrentTeacher,
    db: DbSession,
    response: Response,
) -> QuestionForTeacher:
    no_store(response)
    return questions.replace(db, user, question_id, data)


@router.delete("/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(question_id: QuestionId, user: CurrentTeacher, db: DbSession) -> Response:
    questions.delete(db, user, question_id)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    no_store(response)
    return response
