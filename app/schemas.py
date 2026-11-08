from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.models import QuestionType, Role


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


class Choice(RequestModel):
    id: str = Field(min_length=1, max_length=50)
    text: str = Field(min_length=1, max_length=2000)


class QuestionContent(RequestModel):
    text: str = Field(min_length=1, max_length=10000)
    topic: str = Field(min_length=1, max_length=120)
    explanation: str | None = Field(default=None, max_length=10000)


class MCQCreate(QuestionContent):
    type: Literal["mcq"]
    choices: list[Choice] = Field(min_length=2, max_length=6)
    correct_answer: StrictStr

    @model_validator(mode="after")
    def validate_choices(self) -> Self:
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


NonblankAnswer = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
]


class ShortAnswerCreate(QuestionContent):
    type: Literal["short_answer"]
    choices: None = None
    correct_answer: list[NonblankAnswer] = Field(min_length=1, max_length=100)


QuestionCreate = Annotated[
    MCQCreate | TrueFalseCreate | ShortAnswerCreate, Field(discriminator="type")
]


class QuestionForStudent(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: QuestionType
    text: str
    topic: str
    choices: list[Choice] | None


class QuestionForTeacher(QuestionForStudent):
    correct_answer: StrictStr | StrictBool | list[StrictStr]
    explanation: str | None


class QuestionFilters(RequestModel):
    q: str | None = Field(default=None, max_length=200)
    topic: str | None = Field(default=None, max_length=120)
    type: QuestionType | None = None


class AssignmentCreate(RequestModel):
    student_ids: list[Id] = Field(min_length=1, max_length=100)
    question_ids: list[Id] = Field(min_length=1, max_length=100)


class AssignmentResult(BaseModel):
    student_ids: list[int]
    question_ids: list[int]


AnswerValue = Annotated[StrictStr, Field(max_length=2000)] | StrictBool | None


class CheckAnswer(RequestModel):
    response: AnswerValue = None


class AnswerFeedback(BaseModel):
    question_id: int
    is_correct: bool
    correct_answer: StrictStr | StrictBool | list[StrictStr]
    explanation: str | None
