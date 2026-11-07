from pydantic import BaseModel


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
