from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Role, User
from app.schemas import LoginRequest

TEACHER_PROFILE = ("brian", "12")


def login(db: Session, data: LoginRequest) -> User:
    profile_key = (data.first_name.casefold(), data.grade.casefold())
    teacher_key = tuple(value.casefold() for value in TEACHER_PROFILE)
    role = Role.TEACHER if profile_key == teacher_key else Role.STUDENT
    user = db.scalar(
        select(User).where(
            func.casefold(User.first_name) == profile_key[0],
            func.casefold(User.grade) == profile_key[1],
        )
    )
    if user is None:
        user = User(first_name=data.first_name, grade=data.grade)
        db.add(user)
    user.role = role
    db.commit()
    db.refresh(user)
    return user
