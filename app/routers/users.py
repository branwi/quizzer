from typing import Annotated

from fastapi import APIRouter, Query

from app.dependencies import CurrentTeacher, CurrentUser, DbSession
from app.schemas import PageFilters, StudentPage, UserPublic
from app.services import quizzes

router = APIRouter(tags=["users"])


@router.get("/me", response_model=UserPublic)
def me(user: CurrentUser) -> UserPublic:
    return user


@router.get("/students", response_model=StudentPage)
def students(
    filters: Annotated[PageFilters, Query()], user: CurrentTeacher, db: DbSession
) -> StudentPage:
    return quizzes.students(db, user, filters)
