from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response

from app.dependencies import DbSession, get_teacher
from app.schemas import QuestionCreate, QuestionFilters, QuestionForTeacher
from app.services import questions

router = APIRouter(prefix="/questions", tags=["manage bank"], dependencies=[Depends(get_teacher)])
QuestionId = Annotated[int, Path(ge=1, le=2**63 - 1)]


@router.post("", response_model=QuestionForTeacher, status_code=201)
def create(data: QuestionCreate, db: DbSession):
    return questions.create(db, data)


@router.get("", response_model=list[QuestionForTeacher])
def list_questions(filters: Annotated[QuestionFilters, Query()], db: DbSession):
    return questions.list_questions(db, filters)


@router.get("/{question_id}", response_model=QuestionForTeacher)
def get(question_id: QuestionId, db: DbSession):
    return questions.get(db, question_id)


@router.put("/{question_id}", response_model=QuestionForTeacher)
def replace(question_id: QuestionId, data: QuestionCreate, db: DbSession):
    return questions.replace(db, question_id, data)


@router.delete("/{question_id}", status_code=204)
def delete(question_id: QuestionId, db: DbSession):
    questions.delete(db, question_id)
    return Response(status_code=204)
