from typing import Annotated

from fastapi import APIRouter, Path

from app.dependencies import CurrentStudent, DbSession
from app.schemas import AttemptReview, AttemptSubmit, AttemptView
from app.services import attempts

router = APIRouter(prefix="/attempts", tags=["attempts"])
AttemptId = Annotated[int, Path(ge=1, le=2**63 - 1)]


@router.get("/{attempt_id}", response_model=AttemptView)
def get(attempt_id: AttemptId, user: CurrentStudent, db: DbSession) -> AttemptView:
    return attempts.get(db, user, attempt_id)


@router.post("/{attempt_id}/submit", response_model=AttemptReview)
def submit(
    attempt_id: AttemptId, data: AttemptSubmit, user: CurrentStudent, db: DbSession
) -> AttemptReview:
    return attempts.submit(db, user, attempt_id, data)
