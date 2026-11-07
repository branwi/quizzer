from copy import deepcopy

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    Attempt,
    Question,
    Quiz,
    QuizAssignment,
    QuizKind,
    QuizQuestion,
    QuizStatus,
    Role,
    User,
)
from app.schemas import QuestionPage, UserPublic
from app.services.access import require_student, require_teacher
from app.services.auth import public_user
from app.services.errors import InvalidInput, ResourceNotFound, StateConflict
from app.services.questions import for_teacher
from app.services.transactions import write_transaction
from app.workflow_schemas import (
    AssignmentCreate,
    AssignmentResult,
    AttemptResult,
    BankFilters,
    PageFilters,
    PracticeCreate,
    QuizCreate,
    QuizForStudent,
    QuizForTeacher,
    QuizPage,
    QuizQuestionForStudent,
    QuizQuestionForTeacher,
    QuizSummary,
    QuizView,
    ResultPage,
    SnapshotForStudent,
    SnapshotForTeacher,
    StudentPage,
)


def summary(quiz: Quiz) -> QuizSummary:
    return QuizSummary(
        id=quiz.id,
        owner_id=quiz.owner_id,
        title=quiz.title,
        kind=quiz.kind,
        due_at=quiz.due_at,
        max_attempts=quiz.max_attempts,
        status=quiz.status,
        created_at=quiz.created_at,
    )


def links(db: Session, quiz_id: int) -> list[QuizQuestion]:
    return list(
        db.scalars(
            select(QuizQuestion)
            .where(QuizQuestion.quiz_id == quiz_id)
            .order_by(QuizQuestion.position)
        )
    )


def snapshot(question: Question) -> dict:
    return deepcopy(
        {
            "type": question.type.value,
            "text": question.text,
            "choices": question.choices,
            "correct_answer": question.correct_answer,
            "explanation": question.explanation,
        }
    )


def student_question(link: QuizQuestion) -> QuizQuestionForStudent:
    if link.snapshot is None:
        raise StateConflict("Published quiz is missing question content")
    # Explicit projection before returning from the service; no answer key reaches the router.
    return QuizQuestionForStudent(
        id=link.id,
        question_id=link.question_id,
        position=link.position,
        points=link.points,
        content=SnapshotForStudent(
            type=link.snapshot["type"],
            text=link.snapshot["text"],
            choices=link.snapshot["choices"],
        ),
    )


def _teacher_view(db: Session, quiz: Quiz) -> QuizForTeacher:
    items = []
    for link in links(db, quiz.id):
        content = link.snapshot
        if quiz.status == QuizStatus.DRAFT:
            source = db.get(Question, link.question_id) if link.question_id else None
            content = (
                snapshot(source)
                if source and (source.author_id == quiz.owner_id or source.is_public)
                else None
            )
        items.append(
            QuizQuestionForTeacher(
                id=link.id,
                question_id=link.question_id,
                position=link.position,
                points=link.points,
                content=SnapshotForTeacher.model_validate(content) if content is not None else None,
            )
        )
    return QuizForTeacher(**summary(quiz).model_dump(), questions=items)


def _student_view(db: Session, quiz: Quiz) -> QuizForStudent:
    return QuizForStudent(
        **summary(quiz).model_dump(),
        questions=[student_question(link) for link in links(db, quiz.id)],
    )


def teacher_quiz(db: Session, user: UserPublic, quiz_id: int) -> Quiz:
    require_teacher(user)
    quiz = db.scalar(select(Quiz).where(Quiz.id == quiz_id).with_for_update())
    if quiz is None or quiz.owner_id != user.id or quiz.kind != QuizKind.ASSIGNED:
        raise ResourceNotFound("Quiz not found")
    return quiz


def eligible_quiz(db: Session, user: UserPublic, quiz_id: int) -> Quiz:
    require_student(user)
    quiz = db.scalar(select(Quiz).where(Quiz.id == quiz_id).with_for_update())
    if quiz is None:
        raise ResourceNotFound("Quiz not found")
    if quiz.kind == QuizKind.SELF_MADE:
        allowed = quiz.owner_id == user.id
    else:
        allowed = db.get(QuizAssignment, (quiz.id, user.id)) is not None
    if not allowed:
        raise ResourceNotFound("Quiz not found")
    if quiz.status != QuizStatus.PUBLISHED:
        raise StateConflict("Quiz is not published")
    return quiz


def _sources(db: Session, owner_id: int, ids: list[int], *, public_only: bool = False) -> dict:
    rows = list(db.scalars(select(Question).where(Question.id.in_(ids)))) if ids else []
    available = {
        q.id: q for q in rows if q.is_public or (not public_only and q.author_id == owner_id)
    }
    if set(ids) != available.keys():
        raise InvalidInput("One or more questions are unavailable")
    return available


def _replace_links(db: Session, quiz: Quiz, data: QuizCreate) -> None:
    _sources(db, quiz.owner_id, [item.question_id for item in data.questions])
    db.execute(delete(QuizQuestion).where(QuizQuestion.quiz_id == quiz.id))
    db.add_all(
        [
            QuizQuestion(
                quiz_id=quiz.id, question_id=item.question_id, position=position, points=item.points
            )
            for position, item in enumerate(data.questions)
        ]
    )
    db.flush()


def create(db: Session, user: UserPublic, data: QuizCreate) -> QuizForTeacher:
    require_teacher(user)
    with write_transaction(db):
        quiz = Quiz(
            owner_id=user.id,
            title=data.title,
            kind=QuizKind.ASSIGNED,
            due_at=data.due_at,
            max_attempts=data.max_attempts,
        )
        db.add(quiz)
        db.flush()
        _replace_links(db, quiz, data)
        db.refresh(quiz)
        return _teacher_view(db, quiz)


def replace(db: Session, user: UserPublic, quiz_id: int, data: QuizCreate) -> QuizForTeacher:
    with write_transaction(db):
        quiz = teacher_quiz(db, user, quiz_id)
        if quiz.status != QuizStatus.DRAFT:
            raise StateConflict("Published quizzes cannot be edited")
        quiz.title, quiz.due_at, quiz.max_attempts = data.title, data.due_at, data.max_attempts
        _replace_links(db, quiz, data)
        db.refresh(quiz)
        return _teacher_view(db, quiz)


def publish(db: Session, user: UserPublic, quiz_id: int) -> QuizForTeacher:
    with write_transaction(db):
        quiz = teacher_quiz(db, user, quiz_id)
        if quiz.status != QuizStatus.DRAFT:
            raise StateConflict("Quiz is already published")
        items = links(db, quiz.id)
        if not items or any(item.question_id is None for item in items):
            raise InvalidInput("Publishing requires at least one available question")
        sources = _sources(db, user.id, [item.question_id for item in items])
        for item in items:
            item.snapshot = snapshot(sources[item.question_id])
        quiz.status = QuizStatus.PUBLISHED
        db.flush()
        return _teacher_view(db, quiz)


def assign(db: Session, user: UserPublic, quiz_id: int, data: AssignmentCreate) -> AssignmentResult:
    with write_transaction(db):
        quiz = teacher_quiz(db, user, quiz_id)
        if quiz.status != QuizStatus.PUBLISHED:
            raise StateConflict("Publish the quiz before assigning it")
        ids = set(data.student_ids)
        valid = set(db.scalars(select(User.id).where(User.id.in_(ids), User.role == Role.STUDENT)))
        if ids != valid:
            raise InvalidInput("All assignees must be registered students")
        existing = set(
            db.scalars(select(QuizAssignment.student_id).where(QuizAssignment.quiz_id == quiz.id))
        )
        db.add_all(
            [
                QuizAssignment(quiz_id=quiz.id, student_id=student_id)
                for student_id in ids - existing
            ]
        )
        return AssignmentResult(quiz_id=quiz.id, student_ids=sorted(existing | ids))


def practice(db: Session, user: UserPublic, data: PracticeCreate) -> QuizForStudent:
    require_student(user)
    with write_transaction(db):
        sources = _sources(db, user.id, data.question_ids, public_only=True)
        quiz = Quiz(
            owner_id=user.id,
            title=data.title,
            kind=QuizKind.SELF_MADE,
            status=QuizStatus.PUBLISHED,
            max_attempts=None,
        )
        db.add(quiz)
        db.flush()
        db.add_all(
            [
                QuizQuestion(
                    quiz_id=quiz.id,
                    question_id=qid,
                    position=position,
                    points=1,
                    snapshot=snapshot(sources[qid]),
                )
                for position, qid in enumerate(data.question_ids)
            ]
        )
        db.flush()
        return _student_view(db, quiz)


def get(db: Session, user: UserPublic, quiz_id: int) -> QuizView:
    if user.role == Role.TEACHER:
        return _teacher_view(db, teacher_quiz(db, user, quiz_id))
    return _student_view(db, eligible_quiz(db, user, quiz_id))


def list_quizzes(
    db: Session, user: UserPublic, filters: PageFilters, *, assigned=False
) -> QuizPage:
    statement = select(Quiz)
    if assigned:
        require_student(user)
        statement = statement.join(QuizAssignment).where(
            QuizAssignment.student_id == user.id,
            Quiz.status == QuizStatus.PUBLISHED,
            Quiz.kind == QuizKind.ASSIGNED,
        )
    else:
        statement = statement.where(Quiz.owner_id == user.id)
    total = db.scalar(select(func.count()).select_from(statement.subquery()))
    rows = db.scalars(
        statement.order_by(Quiz.created_at.desc(), Quiz.id.desc())
        .offset((filters.page - 1) * filters.page_size)
        .limit(filters.page_size)
    )
    return QuizPage(
        items=[summary(q) for q in rows],
        total=total,
        page=filters.page,
        page_size=filters.page_size,
    )


def students(db: Session, user: UserPublic, filters: PageFilters) -> StudentPage:
    require_teacher(user)
    total = db.scalar(select(func.count()).select_from(User).where(User.role == Role.STUDENT))
    rows = db.scalars(
        select(User)
        .where(User.role == Role.STUDENT)
        .order_by(User.name, User.id)
        .offset((filters.page - 1) * filters.page_size)
        .limit(filters.page_size)
    )
    return StudentPage(
        items=[public_user(row) for row in rows],
        total=total,
        page=filters.page,
        page_size=filters.page_size,
    )


def assignment_ids(db: Session, user: UserPublic, quiz_id: int) -> AssignmentResult:
    teacher_quiz(db, user, quiz_id)
    return AssignmentResult(
        quiz_id=quiz_id,
        student_ids=list(
            db.scalars(
                select(QuizAssignment.student_id)
                .where(QuizAssignment.quiz_id == quiz_id)
                .order_by(QuizAssignment.student_id)
            )
        ),
    )


def available_questions(db: Session, user: UserPublic, filters: BankFilters) -> QuestionPage:
    require_teacher(user)
    conditions = [or_(Question.author_id == user.id, Question.is_public.is_(True))]
    if filters.q:
        conditions.append(
            or_(
                Question.text.icontains(filters.q, autoescape=True),
                Question.topic.icontains(filters.q, autoescape=True),
            )
        )
    if filters.topic:
        conditions.append(Question.topic == filters.topic)
    if filters.type is not None:
        conditions.append(Question.type == filters.type)
    total = db.scalar(select(func.count()).select_from(Question).where(*conditions))
    rows = db.scalars(
        select(Question)
        .where(*conditions)
        .order_by(Question.created_at.desc(), Question.id.desc())
        .offset((filters.page - 1) * filters.page_size)
        .limit(filters.page_size)
    )
    return QuestionPage(
        items=[for_teacher(q) for q in rows],
        total=total,
        page=filters.page,
        page_size=filters.page_size,
    )


def selection_labels(db: Session, user: UserPublic, ids: list[int]) -> dict[str, str]:
    require_teacher(user)
    rows = db.execute(
        select(Question.id, Question.text).where(
            Question.id.in_(ids),
            or_(Question.author_id == user.id, Question.is_public.is_(True)),
        )
    )
    return {str(qid): text[:160] for qid, text in rows}


def results(db: Session, user: UserPublic, quiz_id: int, filters: PageFilters) -> ResultPage:
    quiz = teacher_quiz(db, user, quiz_id)
    total = db.scalar(select(func.count()).select_from(Attempt).where(Attempt.quiz_id == quiz.id))
    rows = db.execute(
        select(Attempt, User.name)
        .join(User, User.id == Attempt.student_id)
        .where(Attempt.quiz_id == quiz.id)
        .order_by(Attempt.id.desc())
        .offset((filters.page - 1) * filters.page_size)
        .limit(filters.page_size)
    )
    return ResultPage(
        items=[
            AttemptResult(
                id=a.id,
                quiz_id=a.quiz_id,
                quiz_title=quiz.title,
                student_id=a.student_id,
                student_name=name,
                started_at=a.started_at,
                submitted_at=a.submitted_at,
                score=a.score,
                max_score=a.max_score,
            )
            for a, name in rows
        ],
        total=total,
        page=filters.page,
        page_size=filters.page_size,
    )
