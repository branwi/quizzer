from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from sqlalchemy.orm import Session

from backend.config import Settings, get_settings
from backend.database import get_db
from backend.models import Role, User
from backend.security import COOKIE_NAME, decode_access_token

DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]
bearer_scheme = HTTPBearer(auto_error=False)


def unauthorized() -> HTTPException:
    return HTTPException(401, "Not authenticated", headers={"WWW-Authenticate": "Bearer"})


def get_current_user(
    request: Request,
    db: DbSession,
    settings: AppSettings,
    bearer: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User:
    token = request.cookies.get(COOKIE_NAME) or (bearer.credentials if bearer else None)
    if not token:
        raise unauthorized()
    try:
        user_id = decode_access_token(token, settings)
    except InvalidTokenError:
        raise unauthorized() from None
    user = db.get(User, user_id)
    if user is None:
        raise unauthorized()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_teacher(user: CurrentUser) -> User:
    if user.role != Role.TEACHER:
        raise HTTPException(403, "Teacher access required")
    return user


def get_student(user: CurrentUser) -> User:
    if user.role != Role.STUDENT:
        raise HTTPException(403, "Student access required")
    return user


CurrentStudent = Annotated[User, Depends(get_student)]
