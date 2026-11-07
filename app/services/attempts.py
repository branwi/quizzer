from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.database import utc_now
from app.models import Answer, Attempt, Quiz, QuizQuestion
from app.schemas import UserPublic
from app.services import quizzes
from app.services.access import require_student
from app.services.errors import InvalidInput, ResourceNotFound, StateConflict
from app.services.grading import grade
from app.services.transactions import write_transaction
from app.workflow_schemas import (
    AttemptInProgress,
    AttemptResult,
    AttemptReview,
    AttemptSubmit,
    AttemptView,
    PageFilters,
    ResultPage,
    ReviewQuestion,
    SnapshotForTeacher,
)


def history(db: Session, user: UserPublic, filters: PageFilters) -> ResultPage:
    require_student(user)
    total = db.scalar(
        select(func.count()).select_from(Attempt).where(Attempt.student_id == user.id)
    )
    rows = db.execute(
        select(Attempt, Quiz.title)
        .join(Quiz, Quiz.id == Attempt.quiz_id)
        .where(Attempt.student_id == user.id)
        .order_by(Attempt.id.desc())
        .offset((filters.page - 1) * filters.page_size)
        .limit(filters.page_size)
    )
    return ResultPage(
        items=[
            AttemptResult(
                id=a.id,
                quiz_id=a.quiz_id,
                quiz_title=title,
                student_id=a.student_id,
                student_name=user.name,
                started_at=a.started_at,
                submitted_at=a.submitted_at,
                score=a.score,
                max_score=a.max_score,
            )
            for a, title in rows
        ],
        total=total,
        page=filters.page,
        page_size=filters.page_size,
    )


def _in_progress(db: Session, attempt: Attempt) -> AttemptInProgress:
    return AttemptInProgress(
        id=attempt.id,
        quiz_id=attempt.quiz_id,
        student_id=attempt.student_id,
        started_at=attempt.started_at,
        max_score=attempt.max_score,
        questions=[quizzes.student_question(link) for link in quizzes.links(db, attempt.quiz_id)],
    )


def _review(db: Session, attempt: Attempt) -> AttemptReview:
    answers = {
        a.quiz_question_id: a
        for a in db.scalars(select(Answer).where(Answer.attempt_id == attempt.id))
    }
    items = []
    for link in quizzes.links(db, attempt.quiz_id):
        answer = answers[link.id]
        items.append(
            ReviewQuestion(
                id=link.id,
                question_id=link.question_id,
                position=link.position,
                points=link.points,
                content=SnapshotForTeacher.model_validate(link.snapshot),
                response=answer.response,
                is_correct=answer.is_correct,
                points_awarded=answer.points_awarded,
            )
        )
    return AttemptReview(
        id=attempt.id,
        quiz_id=attempt.quiz_id,
        student_id=attempt.student_id,
        started_at=attempt.started_at,
        submitted_at=attempt.submitted_at,
        score=attempt.score,
        max_score=attempt.max_score,
        questions=items,
    )


def _own_attempt(db: Session, user: UserPublic, attempt_id: int) -> Attempt:
    require_student(user)
    attempt = db.scalar(
        select(Attempt)
        .where(
            Attempt.id == attempt_id,
            Attempt.student_id == user.id,
        )
        .with_for_update()
    )
    if attempt is None:
        raise ResourceNotFound("Attempt not found")
    return attempt


def _before_deadline(quiz) -> None:
    if quiz.due_at is not None and utc_now() >= quiz.due_at:
        raise StateConflict("The quiz deadline has passed")


def start(db: Session, user: UserPublic, quiz_id: int) -> tuple[AttemptInProgress, bool]:
    require_student(user)
    with write_transaction(db):
        quiz = quizzes.eligible_quiz(db, user, quiz_id)
        _before_deadline(quiz)
        active = db.scalar(
            select(Attempt)
            .where(
                Attempt.quiz_id == quiz.id,
                Attempt.student_id == user.id,
                Attempt.submitted_at.is_(None),
            )
            .order_by(Attempt.id)
        )
        if active is not None:
            return _in_progress(db, active), False
        count = db.scalar(
            select(func.count())
            .select_from(Attempt)
            .where(
                Attempt.quiz_id == quiz.id,
                Attempt.student_id == user.id,
            )
        )
        if quiz.max_attempts is not None and count >= quiz.max_attempts:
            raise StateConflict("Maximum attempts reached")
        links = quizzes.links(db, quiz.id)
        if not links or any(link.snapshot is None for link in links):
            raise StateConflict("Quiz has no published question content")
        attempt = Attempt(
            quiz_id=quiz.id,
            student_id=user.id,
            max_score=sum(link.points for link in links),
        )
        db.add(attempt)
        db.flush()
        return _in_progress(db, attempt), True


def get(db: Session, user: UserPublic, attempt_id: int) -> AttemptView:
    attempt = _own_attempt(db, user, attempt_id)
    return _review(db, attempt) if attempt.submitted_at is not None else _in_progress(db, attempt)


def _validate_response(link: QuizQuestion, response) -> None:
    if response is None:
        return
    kind = link.snapshot["type"]
    if kind == "true_false" and type(response) is not bool:
        raise InvalidInput("True/false responses must be JSON booleans or null")
    if kind in ("mcq", "short_answer") and not isinstance(response, str):
        raise InvalidInput("Text and choice responses must be strings or null")
    if (
        kind == "mcq"
        and response != ""
        and response not in {choice["id"] for choice in link.snapshot["choices"]}
    ):
        raise InvalidInput("MCQ response must be a choice id from this question")


def submit(db: Session, user: UserPublic, attempt_id: int, data: AttemptSubmit) -> AttemptReview:
    require_student(user)
    with write_transaction(db):
        attempt = _own_attempt(db, user, attempt_id)
        if attempt.submitted_at is not None:
            raise StateConflict("Attempt has already been submitted")
        quiz = quizzes.eligible_quiz(db, user, attempt.quiz_id)
        _before_deadline(quiz)
        links = quizzes.links(db, quiz.id)
        responses = {answer.quiz_question_id: answer.response for answer in data.answers}
        if not responses.keys() <= {link.id for link in links}:
            raise InvalidInput("Answers contain a question outside this attempt")
        rows = []
        for link in links:
            response = responses.get(link.id)
            _validate_response(link, response)
            correct = grade(link.snapshot, response)
            rows.append(
                Answer(
                    attempt_id=attempt.id,
                    quiz_id=quiz.id,
                    quiz_question_id=link.id,
                    response=response,
                    is_correct=correct,
                    points_awarded=link.points if correct else 0,
                )
            )
        score = sum(row.points_awarded for row in rows)
        changed = db.execute(
            update(Attempt)
            .where(
                Attempt.id == attempt.id,
                Attempt.submitted_at.is_(None),
            )
            .values(score=score, submitted_at=utc_now())
        )
        if changed.rowcount != 1:
            raise StateConflict("Attempt has already been submitted")
        db.add_all(rows)
        db.flush()
        db.refresh(attempt)
        return _review(db, attempt)
