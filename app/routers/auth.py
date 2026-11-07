from fastapi import APIRouter, HTTPException, Response, status

from app.dependencies import AppSettings, DbSession, unauthorized
from app.schemas import LoginRequest, LoginResponse, RegisterRequest, UserPublic
from app.security import COOKIE_NAME
from app.services import auth

public_router = APIRouter(prefix="/auth", tags=["auth"])
private_router = APIRouter(prefix="/auth", tags=["auth"])


def no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


@public_router.post("/register", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
def register(data: RegisterRequest, db: DbSession, response: Response) -> UserPublic:
    try:
        user = auth.register(db, data)
    except auth.EmailAlreadyRegistered:
        raise HTTPException(status_code=409, detail="Email already registered") from None
    no_store(response)
    return user


@public_router.post("/login", response_model=LoginResponse)
def login(
    data: LoginRequest, db: DbSession, settings: AppSettings, response: Response
) -> LoginResponse:
    try:
        result = auth.authenticate(db, data, settings)
    except auth.InvalidCredentials:
        raise unauthorized("Invalid email or password") from None
    response.set_cookie(
        key=COOKIE_NAME,
        value=result.access_token,
        max_age=result.expires_in,
        path="/",
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )
    no_store(response)
    return result


@private_router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(settings: AppSettings) -> Response:
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(
        key=COOKIE_NAME, path="/", httponly=True, secure=settings.cookie_secure, samesite="lax"
    )
    no_store(response)
    return response
