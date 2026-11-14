from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    StringConstraints,
    field_validator,
)

from backend.models import Role


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Id = Annotated[StrictInt, Field(ge=1, le=2**63 - 1)]


class LoginRequest(RequestModel):
    first_name: Name
    grade: str = Field(min_length=1, max_length=20)

    @field_validator("grade", mode="before")
    @classmethod
    def accept_grade_number(cls, value):
        # Grades are labels: allow 6 as well as "6", "K", or "college".
        return str(value) if type(value) is int else value


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    first_name: str
    grade: str
    role: Role


class LoginResponse(BaseModel):
    user: UserPublic
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


NonblankAnswer = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
]


class QuestionCreate(RequestModel):
    text: str = Field(min_length=1, max_length=10000)
    topic: str = Field(min_length=1, max_length=120)
    explanation: str | None = Field(default=None, max_length=10000)
    correct_answer: list[NonblankAnswer] = Field(min_length=1, max_length=100)


class QuestionForStudent(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    text: str
    topic: str


class QuestionForTeacher(QuestionForStudent):
    correct_answer: list[StrictStr]
    explanation: str | None


class QuestionFilters(RequestModel):
    topic: str | None = Field(default=None, max_length=120)
    page: int = Field(default=1, ge=1, le=2**31 - 1)
    page_size: int = Field(default=20, ge=1, le=100)


class AssignmentCreate(RequestModel):
    student_ids: list[Id] = Field(min_length=1, max_length=100)
    question_ids: list[Id] = Field(min_length=1, max_length=100)


class AssignmentResult(BaseModel):
    student_ids: list[int]
    question_ids: list[int]


class AssignmentUpdate(RequestModel):
    question_ids: list[Id] = Field(max_length=100)


class CheckAnswer(RequestModel):
    response: Annotated[StrictStr, Field(max_length=2000)] | None = None


class AnswerFeedback(BaseModel):
    question_id: int
    is_correct: bool
    correct_answer: list[StrictStr]
    explanation: str | None
