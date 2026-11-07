from datetime import datetime
from typing import Annotated, Literal, Self

from email_validator import EmailNotValidError, validate_email
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    StrictBool,
    StrictStr,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.models import QuestionType, Role


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


NonblankAnswer = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
]


class Choice(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(min_length=1, max_length=50)
    text: str = Field(min_length=1, max_length=2000)


class QuestionContent(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    text: str = Field(min_length=1, max_length=10000)
    topic: str = Field(min_length=1, max_length=120)
    explanation: str | None = Field(default=None, max_length=10000)
    is_public: StrictBool = False


class MCQCreate(QuestionContent):
    type: Literal["mcq"]
    choices: list[Choice] = Field(min_length=2, max_length=6)
    correct_answer: StrictStr

    @model_validator(mode="after")
    def validate_choice_ids(self) -> Self:
        ids = [choice.id for choice in self.choices]
        if len(ids) != len(set(ids)):
            raise ValueError("Choice ids must be unique")
        if self.correct_answer not in ids:
            raise ValueError("Correct answer must match a choice id")
        return self


class TrueFalseCreate(QuestionContent):
    type: Literal["true_false"]
    choices: None = None
    correct_answer: StrictBool


class ShortAnswerCreate(QuestionContent):
    type: Literal["short_answer"]
    choices: None = None
    correct_answer: list[NonblankAnswer] = Field(min_length=1, max_length=100)


QuestionCreate = Annotated[
    MCQCreate | TrueFalseCreate | ShortAnswerCreate, Field(discriminator="type")
]


class QuestionForStudent(BaseModel):
    id: int
    author_id: int
    type: QuestionType
    text: str
    choices: list[Choice] | None
    topic: str
    is_public: bool
    created_at: datetime
    updated_at: datetime


class QuestionForTeacher(QuestionForStudent):
    correct_answer: StrictStr | StrictBool | list[StrictStr]
    explanation: str | None


class QuestionFilters(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    q: str | None = Field(default=None, max_length=200)
    topic: str | None = Field(default=None, max_length=120)
    type: QuestionType | None = None
    is_public: bool | None = None
    page: int = Field(default=1, ge=1, le=2**31 - 1)
    page_size: int = Field(default=20, ge=1, le=50)


class QuestionPage(BaseModel):
    items: list[QuestionForTeacher]
    total: int
    page: int
    page_size: int
