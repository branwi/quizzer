from datetime import UTC, datetime, timedelta

import jwt

from backend.config import Settings

COOKIE_NAME = "access_token"


def signing_key(settings: Settings) -> str:
    key = settings.secret_key.get_secret_value() if settings.secret_key else ""
    if len(key.encode()) < 32:
        raise RuntimeError("Set SECRET_KEY to a random secret of at least 32 bytes before startup")
    return key


def create_access_token(user_id: int, settings: Settings) -> str:
    return jwt.encode(
        {
            "sub": str(user_id),
            "aud": "problem-bank",
            "exp": datetime.now(UTC) + timedelta(minutes=settings.access_token_minutes),
        },
        signing_key(settings),
        algorithm="HS256",
    )


def decode_access_token(token: str, settings: Settings) -> int:
    claims = jwt.decode(
        token,
        signing_key(settings),
        algorithms=["HS256"],
        audience="problem-bank",
        options={"require": ["sub", "exp", "aud"]},
    )
    try:
        user_id = int(claims["sub"])
    except (TypeError, ValueError):
        raise jwt.InvalidTokenError("Invalid user id") from None
    if not 0 < user_id <= 2**63 - 1:
        raise jwt.InvalidTokenError("Invalid user id")
    return user_id
