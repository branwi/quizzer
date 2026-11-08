from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import get_settings
from app.database import create_tables
from app.dependencies import DbSession, get_current_user
from app.routers import assignments, auth, bank, questions, users
from app.security import signing_key
from app.services.errors import InvalidInput, ResourceNotFound, ServiceError


@asynccontextmanager
async def lifespan(_app: FastAPI):
    signing_key(get_settings())
    create_tables()
    yield


app = FastAPI(title="Problem Bank API", lifespan=lifespan)
app.include_router(auth.router, prefix="/api")

api = APIRouter(prefix="/api", dependencies=[Depends(get_current_user)])
for router in (users.router, questions.router, bank.router, assignments.router):
    api.include_router(router)
app.include_router(api)


@app.exception_handler(ServiceError)
async def service_error(_request: Request, exc: ServiceError):
    status = {ResourceNotFound: 404, InvalidInput: 422}[type(exc)]
    return JSONResponse(status_code=status, content={"detail": str(exc)})


@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, exc: RequestValidationError):
    # Report the invalid fields without echoing raw input.
    errors = [{key: error[key] for key in ("type", "loc", "msg")} for error in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": errors})


@app.get("/health")
def health(db: DbSession):
    db.execute(text("SELECT 1"))
    return {"status": "ok"}
