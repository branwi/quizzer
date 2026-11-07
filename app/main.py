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
from app.routers import auth, users
from app.schemas import HealthResponse
from app.security import signing_key


@asynccontextmanager
async def lifespan(_app: FastAPI):
    signing_key(get_settings())  # Fail before serving requests if no usable secret was configured.
    create_tables()
    yield


app = FastAPI(
    title="Quiz Platform",
    description="Milestone 2: registration, JWT cookie/bearer login, logout, and current user.",
    lifespan=lifespan,
)

app.include_router(auth.public_router, prefix="/api")
# All private API routes inherit login enforcement; add future resource routers here.
api_router = APIRouter(prefix="/api", dependencies=[Depends(get_current_user)])
api_router.include_router(auth.private_router)
api_router.include_router(users.router)
app.include_router(api_router)


@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
    # Default validation errors echo raw input, including invalid passwords.
    errors = [{key: error[key] for key in ("type", "loc", "msg")} for error in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": errors})


@app.get("/health", response_model=HealthResponse, tags=["operations"])
def health(db: Annotated[Session, Depends(get_db)]) -> HealthResponse:
    db.execute(text("SELECT 1"))
    return HealthResponse(status="ok", milestone="authentication")
