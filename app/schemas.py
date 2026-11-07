from datetime import datetime
from typing import Annotated, Literal, Self

from email_validator import EmailNotValidError, validate_email
from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    StrictBool,
    StrictInt,
    StrictStr,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.models import QuestionType, QuizKind, QuizStatus, Role


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


Id = Annotated[StrictInt, Field(ge=1, le=2**63 - 1)]
AnswerValue = Annotated[StrictStr, Field(max_length=2000)] | StrictBool | None


class PageFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    page: int = Field(default=1, ge=1, le=2**31 - 1)
    page_size: int = Field(default=20, ge=1, le=50)


class BankFilters(PageFilters):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    q: str | None = Field(default=None, max_length=200)
    topic: str | None = Field(default=None, max_length=120)
    type: QuestionType | None = None


class StudentBankPage(BaseModel):
    view: Literal["student"] = "student"
    items: list[QuestionForStudent]
    total: int
    page: int
    page_size: int


class TeacherBankPage(BaseModel):
    view: Literal["teacher"] = "teacher"
    items: list[QuestionForTeacher]
    total: int
    page: int
    page_size: int


BankPage = Annotated[StudentBankPage | TeacherBankPage, Field(discriminator="view")]


class QuizQuestionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question_id: Id
    points: Annotated[StrictInt, Field(ge=1, le=1000000)] = 1


class QuizCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=200)
    questions: list[QuizQuestionInput] = Field(default_factory=list, max_length=100)
    due_at: AwareDatetime | None = None
    max_attempts: Annotated[StrictInt, Field(ge=1, le=1000)] | None = 1

    @model_validator(mode="after")
    def unique_questions(self) -> Self:
        ids = [question.question_id for question in self.questions]
        if len(ids) != len(set(ids)):
            raise ValueError("Question ids must be unique")
        return self


class PracticeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(default="Practice quiz", min_length=1, max_length=200)
    question_ids: list[Id] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_questions(self) -> Self:
        if len(self.question_ids) != len(set(self.question_ids)):
            raise ValueError("Question ids must be unique")
        return self


class AssignmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    student_ids: list[Id] = Field(min_length=1, max_length=500)


class AssignmentResult(BaseModel):
    quiz_id: int
    student_ids: list[int]


class SnapshotForStudent(BaseModel):
    type: QuestionType
    text: str
    choices: list[Choice] | None = None


class SnapshotForTeacher(SnapshotForStudent):
    correct_answer: StrictStr | StrictBool | list[StrictStr]
    explanation: str | None = None


class QuizQuestionForStudent(BaseModel):
    id: int
    question_id: int | None
    position: int
    points: int
    content: SnapshotForStudent


class QuizQuestionForTeacher(BaseModel):
    id: int
    question_id: int | None
    position: int
    points: int
    content: SnapshotForTeacher | None  # A draft's source may have been deleted.


class QuizSummary(BaseModel):
    id: int
    owner_id: int
    title: str
    kind: QuizKind
    due_at: datetime | None
    max_attempts: int | None
    status: QuizStatus
    created_at: datetime


class QuizForStudent(QuizSummary):
    view: Literal["student"] = "student"
    questions: list[QuizQuestionForStudent]


class QuizForTeacher(QuizSummary):
    view: Literal["teacher"] = "teacher"
    questions: list[QuizQuestionForTeacher]


QuizView = Annotated[QuizForStudent | QuizForTeacher, Field(discriminator="view")]


class QuizPage(BaseModel):
    items: list[QuizSummary]
    total: int
    page: int
    page_size: int


class StudentPage(BaseModel):
    items: list[UserPublic]
    total: int
    page: int
    page_size: int


class AnswerSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")
    quiz_question_id: Id
    response: AnswerValue = None


class AttemptSubmit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answers: list[AnswerSubmission] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def unique_answers(self) -> Self:
        ids = [answer.quiz_question_id for answer in self.answers]
        if len(ids) != len(set(ids)):
            raise ValueError("Each quiz question may be answered only once")
        return self


class AttemptBase(BaseModel):
    id: int
    quiz_id: int
    student_id: int
    started_at: datetime
    max_score: int


class AttemptInProgress(AttemptBase):
    state: Literal["in_progress"] = "in_progress"
    questions: list[QuizQuestionForStudent]


class ReviewQuestion(BaseModel):
    id: int
    question_id: int | None
    position: int
    points: int
    content: SnapshotForTeacher
    response: AnswerValue
    is_correct: bool
    points_awarded: int


class AttemptReview(AttemptBase):
    state: Literal["submitted"] = "submitted"
    submitted_at: datetime
    score: int
    questions: list[ReviewQuestion]


AttemptView = Annotated[AttemptInProgress | AttemptReview, Field(discriminator="state")]


class AttemptResult(AttemptBase):
    quiz_title: str
    student_name: str
    submitted_at: datetime | None
    score: int | None


class ResultPage(BaseModel):
    items: list[AttemptResult]
    total: int
    page: int
    page_size: int


class QuestionAccuracy(BaseModel):
    quiz_question_id: int
    position: int
    text: str
    responses: int
    correct: int
    accuracy: float | None


class ScoreBucket(BaseModel):
    label: str
    lower_percent: int
    upper_percent: int
    count: int


class QuizAnalytics(BaseModel):
    quiz_id: int
    total_attempts: int
    submitted_attempts: int
    in_progress_attempts: int
    average_percent: float | None
    lowest_percent: float | None
    highest_percent: float | None
    questions: list[QuestionAccuracy]
    score_distribution: list[ScoreBucket]
