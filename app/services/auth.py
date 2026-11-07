from secrets import compare_digest, token_urlsafe

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import User
from app.schemas import LoginRequest, LoginResponse, RegisterRequest, UserPublic
from app.security import (
    TokenIdentity,
    account_version,
    create_access_token,
    hash_password,
    verify_password,
)

# Unknown accounts still take the expensive password-verification path.
_DUMMY_PASSWORD_HASH = hash_password(token_urlsafe(32))


class InvalidCredentials(Exception):
    pass


class EmailAlreadyRegistered(Exception):
    pass


def public_user(user: User) -> UserPublic:
    return UserPublic(
        id=user.id, name=user.name, email=user.email, role=user.role, created_at=user.created_at
    )


def register(db: Session, data: RegisterRequest) -> UserPublic:
    if db.scalar(select(User.id).where(User.email == data.email)) is not None:
        raise EmailAlreadyRegistered
    user = User(
        name=data.name,
        email=data.email,
        role=data.role,
        password_hash=hash_password(data.password.get_secret_value()),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return public_user(user)


def authenticate(db: Session, data: LoginRequest, settings: Settings) -> LoginResponse:
    user = db.scalar(select(User).where(User.email == data.email))
    hashed = user.password_hash if user is not None else _DUMMY_PASSWORD_HASH
    valid = verify_password(data.password.get_secret_value(), hashed)
    if user is None or not valid:
        raise InvalidCredentials
    return LoginResponse(
        user=public_user(user),
        access_token=create_access_token(user.id, settings, hashed_password=user.password_hash),
        expires_in=settings.access_token_minutes * 60,
    )


def current_user(db: Session, identity: TokenIdentity, settings: Settings) -> UserPublic:
    user = db.get(User, identity.user_id)
    if user is None or not compare_digest(
        identity.account_version, account_version(user.password_hash, settings)
    ):
        raise InvalidCredentials
    return public_user(user)
