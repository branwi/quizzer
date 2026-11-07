from sqlalchemy import Integer, case, cast, func, select
from sqlalchemy.orm import Session

from app.analytics_schemas import QuestionAccuracy, QuizAnalytics, ScoreBucket
from app.models import Answer, Attempt, QuizQuestion
from app.schemas import UserPublic
from app.services.quizzes import teacher_quiz


def for_quiz(db: Session, user: UserPublic, quiz_id: int) -> QuizAnalytics:
    teacher_quiz(db, user, quiz_id)
    counts = (
        select(
            Answer.quiz_question_id.label("question_id"),
            func.count(Answer.id).label("responses"),
            func.sum(cast(Answer.is_correct, Integer)).label("correct"),
            func.avg(cast(Answer.is_correct, Integer)).label("accuracy"),
        )
        .join(Attempt, Attempt.id == Answer.attempt_id)
        .where(
            Attempt.quiz_id == quiz_id,
            Attempt.submitted_at.is_not(None),
        )
        .group_by(Answer.quiz_question_id)
        .subquery()
    )
    rows = db.execute(
        select(
            QuizQuestion,
            counts.c.responses,
            counts.c.correct,
            counts.c.accuracy,
        )
        .outerjoin(counts, counts.c.question_id == QuizQuestion.id)
        .where(QuizQuestion.quiz_id == quiz_id)
        .order_by(QuizQuestion.position)
    )
    questions = [
        QuestionAccuracy(
            quiz_question_id=link.id,
            position=link.position,
            text=link.snapshot["text"] if link.snapshot else f"Question {link.position + 1}",
            responses=responses or 0,
            correct=correct or 0,
            accuracy=accuracy,
        )
        for link, responses, correct, accuracy in rows
    ]
    percent = Attempt.score * 100.0 / Attempt.max_score
    total, submitted, average, lowest, highest = db.execute(
        select(
            func.count(Attempt.id),
            func.count(Attempt.submitted_at),
            func.avg(percent),
            func.min(percent),
            func.max(percent),
        ).where(Attempt.quiz_id == quiz_id)
    ).one()
    bucket = case(
        (percent < 20, 0), (percent < 40, 1), (percent < 60, 2), (percent < 80, 3), else_=4
    )
    bucket_counts = dict(
        db.execute(
            select(bucket, func.count(Attempt.id))
            .where(
                Attempt.quiz_id == quiz_id,
                Attempt.submitted_at.is_not(None),
            )
            .group_by(bucket)
        ).all()
    )
    return QuizAnalytics(
        quiz_id=quiz_id,
        total_attempts=total,
        submitted_attempts=submitted,
        in_progress_attempts=total - submitted,
        average_percent=round(average, 2) if average is not None else None,
        lowest_percent=round(lowest, 2) if lowest is not None else None,
        highest_percent=round(highest, 2) if highest is not None else None,
        questions=questions,
        score_distribution=[
            ScoreBucket(
                label=f"{i * 20}–<{(i + 1) * 20}%" if i < 4 else "80–100%",
                lower_percent=i * 20,
                upper_percent=(i + 1) * 20,
                count=bucket_counts.get(i, 0),
            )
            for i in range(5)
        ],
    )
