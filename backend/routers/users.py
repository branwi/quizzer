from fastapi import APIRouter, Depends
from sqlalchemy import select

from backend.dependencies import CurrentUser, DbSession, get_teacher
from backend.models import Role, User
from backend.schemas import UserPublic

router = APIRouter(tags=["users"])


@router.get("/me", response_model=UserPublic)
def me(user: CurrentUser):
    return user


@router.get("/students", response_model=list[UserPublic], dependencies=[Depends(get_teacher)])
def students(db: DbSession):
    return list(
        db.scalars(select(User).where(User.role == Role.STUDENT).order_by(User.first_name, User.id))
    )
