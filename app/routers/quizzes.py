from typing import Annotated

from fastapi import APIRouter, Path, Query, Response, status

from app.analytics_schemas import QuizAnalytics
from app.dependencies import CurrentStudent, CurrentTeacher, CurrentUser, DbSession
from app.routers.auth import no_store
from app.services import analytics, attempts, quizzes
from app.workflow_schemas import (
    AssignmentCreate,
    AssignmentResult,
    AttemptInProgress,
    PageFilters,
    PracticeCreate,
    QuizCreate,
    QuizForStudent,
    QuizForTeacher,
    QuizPage,
    QuizView,
    ResultPage,
)

router = APIRouter(prefix="/quizzes", tags=["quizzes"])
QuizId = Annotated[int, Path(ge=1, le=2**63 - 1)]


@router.get("/assigned", response_model=QuizPage)
def assigned(
    filters: Annotated[PageFilters, Query()],
    user: CurrentStudent,
    db: DbSession,
    response: Response,
) -> QuizPage:
    no_store(response)
    return quizzes.list_quizzes(db, user, filters, assigned=True)


@router.post("/practice", response_model=QuizForStudent, status_code=status.HTTP_201_CREATED)
def practice(
    data: PracticeCreate, user: CurrentStudent, db: DbSession, response: Response
) -> QuizForStudent:
    no_store(response)
    return quizzes.practice(db, user, data)


@router.get("", response_model=QuizPage)
def list_own(
    filters: Annotated[PageFilters, Query()], user: CurrentUser, db: DbSession, response: Response
) -> QuizPage:
    no_store(response)
    return quizzes.list_quizzes(db, user, filters)


@router.post("", response_model=QuizForTeacher, status_code=status.HTTP_201_CREATED)
def create(
    data: QuizCreate, user: CurrentTeacher, db: DbSession, response: Response
) -> QuizForTeacher:
    no_store(response)
    return quizzes.create(db, user, data)


@router.get("/{quiz_id}", response_model=QuizView)
def get(quiz_id: QuizId, user: CurrentUser, db: DbSession, response: Response) -> QuizView:
    no_store(response)
    return quizzes.get(db, user, quiz_id)


@router.put("/{quiz_id}", response_model=QuizForTeacher)
def replace(
    quiz_id: QuizId, data: QuizCreate, user: CurrentTeacher, db: DbSession, response: Response
) -> QuizForTeacher:
    no_store(response)
    return quizzes.replace(db, user, quiz_id, data)


@router.post("/{quiz_id}/publish", response_model=QuizForTeacher)
def publish(
    quiz_id: QuizId, user: CurrentTeacher, db: DbSession, response: Response
) -> QuizForTeacher:
    no_store(response)
    return quizzes.publish(db, user, quiz_id)


@router.post("/{quiz_id}/assignments", response_model=AssignmentResult)
def assign(
    quiz_id: QuizId, data: AssignmentCreate, user: CurrentTeacher, db: DbSession, response: Response
) -> AssignmentResult:
    no_store(response)
    return quizzes.assign(db, user, quiz_id, data)


@router.get("/{quiz_id}/results", response_model=ResultPage)
def results(
    quiz_id: QuizId,
    filters: Annotated[PageFilters, Query()],
    user: CurrentTeacher,
    db: DbSession,
    response: Response,
) -> ResultPage:
    no_store(response)
    return quizzes.results(db, user, quiz_id, filters)


@router.post("/{quiz_id}/attempts", response_model=AttemptInProgress)
def start(
    quiz_id: QuizId, user: CurrentStudent, db: DbSession, response: Response
) -> AttemptInProgress:
    result, created = attempts.start(db, user, quiz_id)
    response.status_code = 201 if created else 200
    no_store(response)
    return result


@router.get("/{quiz_id}/analytics", response_model=QuizAnalytics)
def quiz_analytics(
    quiz_id: QuizId, user: CurrentTeacher, db: DbSession, response: Response
) -> QuizAnalytics:
    no_store(response)
    return analytics.for_quiz(db, user, quiz_id)
