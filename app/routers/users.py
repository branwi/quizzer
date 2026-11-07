from typing import Annotated

from fastapi import APIRouter, Query, Response

from app.dependencies import CurrentTeacher, CurrentUser, DbSession
from app.routers.auth import no_store
from app.schemas import UserPublic
from app.services import quizzes
from app.workflow_schemas import PageFilters, StudentPage

router = APIRouter(tags=["users"])


@router.get("/me", response_model=UserPublic)
def me(user: CurrentUser, response: Response) -> UserPublic:
    no_store(response)
    return user


@router.get("/students", response_model=StudentPage)
def students(
    filters: Annotated[PageFilters, Query()],
    user: CurrentTeacher,
    db: DbSession,
    response: Response,
) -> StudentPage:
    no_store(response)
    return quizzes.students(db, user, filters)
