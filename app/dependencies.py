from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_db
from app.schemas import UserPublic
from app.security import COOKIE_NAME, decode_access_token
from app.services import auth

DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]
bearer_scheme = HTTPBearer(auto_error=False)


def unauthorized(detail: str = "Not authenticated") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    request: Request,
    db: DbSession,
    settings: AppSettings,
    bearer: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> UserPublic:
    # A nonempty cookie takes precedence, even if a valid header is also present.
    token = request.cookies.get(COOKIE_NAME) or (bearer.credentials if bearer else None)
    if not token:
        raise unauthorized()
    try:
        user_id = decode_access_token(token, settings)
        return auth.current_user(db, user_id)
    except (InvalidTokenError, auth.InvalidCredentials):
        raise unauthorized() from None


CurrentUser = Annotated[UserPublic, Depends(get_current_user)]
