from fastapi import APIRouter, HTTPException, Response, status

from app.dependencies import AppSettings, DbSession, unauthorized
from app.schemas import LoginRequest, LoginResponse, RegisterRequest, UserPublic
from app.security import COOKIE_NAME, create_access_token
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
        user = auth.authenticate(db, data)
    except auth.InvalidCredentials:
        raise unauthorized("Invalid email or password") from None
    token = create_access_token(user.id, settings)
    seconds = settings.access_token_minutes * 60
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=seconds,
        path="/",
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )
    no_store(response)
    return LoginResponse(user=user, access_token=token, expires_in=seconds)


@private_router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(settings: AppSettings) -> Response:
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(
        key=COOKIE_NAME, path="/", httponly=True, secure=settings.cookie_secure, samesite="lax"
    )
    no_store(response)
    return response
