import re
from datetime import timedelta

import jwt
from pwdlib import PasswordHash

from app.config import Settings
from app.database import utc_now

COOKIE_NAME = "access_token"
password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return password_hash.verify(password, hashed)


def signing_key(settings: Settings) -> str:
    key = settings.secret_key.get_secret_value() if settings.secret_key else ""
    if len(key.encode("utf-8")) < 32:
        raise RuntimeError("Set SECRET_KEY to a random secret of at least 32 bytes before startup")
    return key


def create_access_token(user_id: int, settings: Settings) -> str:
    now = utc_now()
    return jwt.encode(
        {
            "sub": str(user_id),
            "iat": now,
            "exp": now + timedelta(minutes=settings.access_token_minutes),
        },
        signing_key(settings),
        algorithm="HS256",
    )


def decode_access_token(token: str, settings: Settings) -> int:
    """Raise InvalidTokenError for any untrusted or malformed credential."""
    try:
        claims = jwt.decode(
            token,
            signing_key(settings),
            algorithms=["HS256"],
            options={"require": ["sub", "iat", "exp"]},
        )
    except (TypeError, ValueError):
        raise jwt.InvalidTokenError("Invalid token claims") from None
    if type(claims["iat"]) is not int or type(claims["exp"]) is not int:
        raise jwt.InvalidTokenError("Invalid token timestamps")
    subject = claims["sub"]
    if not isinstance(subject, str) or re.fullmatch(r"[1-9][0-9]{0,18}", subject) is None:
        raise jwt.InvalidTokenError("Invalid user subject")
    user_id = int(subject)
    if user_id > 2**63 - 1:
        raise jwt.InvalidTokenError("Invalid user subject")
    return user_id
