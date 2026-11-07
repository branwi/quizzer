from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import get_settings
from app.database import create_tables, get_db
from app.dependencies import get_current_user
from app.routers import attempts, auth, bank, questions, quizzes, users
from app.schemas import HealthResponse
from app.security import signing_key
from app.services.access import PermissionDenied
from app.services.errors import InvalidInput, ResourceNotFound, ServiceError, StateConflict
from app.services.questions import QuestionNotFound
from app.web.common import error_page, is_web
from app.web.forms import messages
from app.web.routes import router as web_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    signing_key(get_settings())  # Fail before serving requests if no usable secret was configured.
    create_tables()
    yield


app = FastAPI(
    title="Quiz Platform",
    description="Quiz authoring, assignment, graded attempts, and public-bank practice quizzes.",
    lifespan=lifespan,
)

app.include_router(auth.public_router, prefix="/api")
# All private API routes inherit login enforcement; add future resource routers here.
api_router = APIRouter(prefix="/api", dependencies=[Depends(get_current_user)])
api_router.include_router(auth.private_router)
api_router.include_router(users.router)
api_router.include_router(questions.router)
api_router.include_router(quizzes.router)
api_router.include_router(attempts.router)
api_router.include_router(bank.router)
app.include_router(api_router)
app.mount(
    "/static", StaticFiles(directory=Path(__file__).resolve().parent / "static"), name="static"
)
app.include_router(web_router)


@app.exception_handler(QuestionNotFound)
async def question_not_found(_request: Request, _exc: QuestionNotFound) -> JSONResponse:
    if is_web(_request):
        return error_page(_request, 404, "Question not found.")
    return JSONResponse(status_code=404, content={"detail": "Question not found"})


@app.exception_handler(PermissionDenied)
async def permission_denied(_request: Request, _exc: PermissionDenied) -> JSONResponse:
    if is_web(_request):
        return error_page(_request, 403, str(_exc))
    return JSONResponse(status_code=403, content={"detail": str(_exc)})


@app.exception_handler(ServiceError)
async def workflow_error(_request: Request, exc: ServiceError) -> JSONResponse:
    status = {ResourceNotFound: 404, StateConflict: 409, InvalidInput: 422}[type(exc)]
    if is_web(_request):
        return error_page(_request, status, str(exc))
    return JSONResponse(status_code=status, content={"detail": str(exc)})


@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
    # Default validation errors echo raw input, including invalid passwords.
    errors = [{key: error[key] for key in ("type", "loc", "msg")} for error in exc.errors()]
    if is_web(_request):
        return error_page(_request, 422, "Check the page address and form fields, then try again.")
    return JSONResponse(status_code=422, content={"detail": errors})


@app.exception_handler(ValidationError)
async def form_validation_error(request: Request, exc: ValidationError):
    if is_web(request):
        return error_page(request, 422, " ".join(messages(exc)))
    return JSONResponse(status_code=500, content={"detail": "Unexpected validation error"})


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException):
    if is_web(request):
        if exc.status_code == 401:
            if request.headers.get("HX-Request"):
                return HTMLResponse(
                    "", headers={"HX-Redirect": "/login", "Cache-Control": "no-store"}
                )
            return RedirectResponse(
                "/login", status_code=303, headers={"Cache-Control": "no-store"}
            )
        return error_page(request, exc.status_code, str(exc.detail))
    return JSONResponse(
        status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers
    )


@app.get("/health", response_model=HealthResponse, tags=["operations"])
def health(db: Annotated[Session, Depends(get_db)]) -> HealthResponse:
    db.execute(text("SELECT 1"))
    return HealthResponse(status="ok", milestone="authentication")
