from typing import Annotated

from fastapi import APIRouter, Depends, Path, Response

from backend.dependencies import CurrentStudent, DbSession, get_teacher
from backend.schemas import AssignmentCreate, AssignmentResult, AssignmentUpdate, QuestionForStudent
from backend.services import assignments

router = APIRouter(prefix="/assignments", tags=["assigned problems"])
PositiveId = Annotated[int, Path(ge=1, le=2**63 - 1)]


@router.get("", response_model=list[QuestionForStudent])
def my_problems(user: CurrentStudent, db: DbSession):
    return assignments.list_assigned(db, user.id)


@router.post("", response_model=AssignmentResult, dependencies=[Depends(get_teacher)])
def assign(data: AssignmentCreate, db: DbSession):
    return assignments.assign(db, data)


@router.get(
    "/{student_id}", response_model=list[QuestionForStudent], dependencies=[Depends(get_teacher)]
)
def for_student(student_id: PositiveId, db: DbSession):
    return assignments.list_assigned(db, student_id)


@router.put(
    "/{student_id}", response_model=list[QuestionForStudent], dependencies=[Depends(get_teacher)]
)
def replace(student_id: PositiveId, data: AssignmentUpdate, db: DbSession):
    return assignments.replace(db, student_id, data)


@router.delete("/{student_id}/{question_id}", status_code=204, dependencies=[Depends(get_teacher)])
def unassign(student_id: PositiveId, question_id: PositiveId, db: DbSession):
    assignments.unassign(db, student_id, question_id)
    return Response(status_code=204)
