from fastapi import APIRouter, Response

from backend.dependencies import AppSettings, DbSession
from backend.schemas import LoginRequest, LoginResponse, UserPublic
from backend.security import COOKIE_NAME, create_access_token
from backend.services import auth

router = APIRouter(prefix="/auth", tags=["login"])


@router.post("/login", response_model=LoginResponse)
def login(data: LoginRequest, response: Response, db: DbSession, settings: AppSettings):
    user = auth.login(db, data)
    token = create_access_token(user.id, settings)
    expires_in = settings.access_token_minutes * 60
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=expires_in,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )
    return LoginResponse(
        user=UserPublic.model_validate(user), access_token=token, expires_in=expires_in
    )


@router.post("/logout", status_code=204)
def logout(settings: AppSettings) -> Response:
    response = Response(status_code=204)
    response.delete_cookie(
        COOKIE_NAME, httponly=True, secure=settings.cookie_secure, samesite="lax"
    )
    return response
