from datetime import datetime
from typing import Annotated, Literal

from email_validator import EmailNotValidError, validate_email
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, SecretStr, field_validator

from app.models import Role


def normalize_email(value: str) -> str:
    try:
        # .test domains are intentional in the existing local demo fixture.
        email = validate_email(value.strip(), check_deliverability=False, test_environment=True)
    except EmailNotValidError as exc:
        raise ValueError("Enter a valid email address") from exc
    normalized = email.normalized.casefold()
    if len(normalized) > 254:
        raise ValueError("Email must be at most 254 characters")
    return normalized


Email = Annotated[str, AfterValidator(normalize_email)]


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    email: Email
    password: SecretStr = Field(min_length=8, max_length=128)
    role: Role

    @field_validator("name", mode="before")
    @classmethod
    def trim_name(cls, value):
        return value.strip() if isinstance(value, str) else value


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: Email
    password: SecretStr = Field(min_length=1, max_length=128)


class UserPublic(BaseModel):
    id: int
    name: str
    email: str
    role: Role
    created_at: datetime


class LoginResponse(BaseModel):
    user: UserPublic
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class HealthResponse(BaseModel):
    status: Literal["ok"]
    milestone: Literal["authentication"]
