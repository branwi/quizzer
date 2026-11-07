from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import create_tables, get_db
from app.dependencies import get_current_user
from app.routers import attempts, auth, bank, questions, quizzes, users
from app.schemas import HealthResponse
from app.security import signing_key
from app.services.access import PermissionDenied
from app.services.errors import InvalidInput, ResourceNotFound, ServiceError, StateConflict
from app.services.questions import QuestionNotFound


@asynccontextmanager
async def lifespan(_app: FastAPI):
    signing_key(get_settings())
    create_tables()
    yield


app = FastAPI(title="Quiz API", lifespan=lifespan)
app.include_router(auth.public_router, prefix="/api")

# Register/login are public. Other API routers require a logged-in user.
api = APIRouter(prefix="/api", dependencies=[Depends(get_current_user)])
for router in (
    auth.private_router,
    users.router,
    questions.router,
    quizzes.router,
    attempts.router,
    bank.router,
):
    api.include_router(router)
app.include_router(api)


@app.exception_handler(QuestionNotFound)
async def question_not_found(_request: Request, _exc: QuestionNotFound):
    return JSONResponse(status_code=404, content={"detail": "Question not found"})


@app.exception_handler(PermissionDenied)
async def permission_denied(_request: Request, exc: PermissionDenied):
    return JSONResponse(status_code=403, content={"detail": str(exc)})


@app.exception_handler(ServiceError)
async def workflow_error(_request: Request, exc: ServiceError):
    status = {ResourceNotFound: 404, StateConflict: 409, InvalidInput: 422}[type(exc)]
    return JSONResponse(status_code=status, content={"detail": str(exc)})


@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, exc: RequestValidationError):
    # Report validation errors without echoing passwords or raw input.
    errors = [{key: error[key] for key in ("type", "loc", "msg")} for error in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": errors})


@app.get("/health", response_model=HealthResponse)
def health(db: Annotated[Session, Depends(get_db)]):
    db.execute(text("SELECT 1"))
    return HealthResponse(status="ok")
