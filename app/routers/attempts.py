from typing import Annotated

from fastapi import APIRouter, Path, Response

from app.dependencies import CurrentStudent, DbSession
from app.routers.auth import no_store
from app.services import attempts
from app.workflow_schemas import AttemptReview, AttemptSubmit, AttemptView

router = APIRouter(prefix="/attempts", tags=["attempts"])
AttemptId = Annotated[int, Path(ge=1, le=2**63 - 1)]


@router.get("/{attempt_id}", response_model=AttemptView)
def get(
    attempt_id: AttemptId, user: CurrentStudent, db: DbSession, response: Response
) -> AttemptView:
    no_store(response)
    return attempts.get(db, user, attempt_id)


@router.post("/{attempt_id}/submit", response_model=AttemptReview)
def submit(
    attempt_id: AttemptId,
    data: AttemptSubmit,
    user: CurrentStudent,
    db: DbSession,
    response: Response,
) -> AttemptReview:
    no_store(response)
    return attempts.submit(db, user, attempt_id, data)
