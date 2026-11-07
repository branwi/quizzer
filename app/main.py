from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import create_tables, get_db
from app.schemas import HealthResponse


@asynccontextmanager
async def lifespan(_app: FastAPI):
    create_tables()
    yield


app = FastAPI(
    title="Quiz Platform",
    description="Milestone 1: database foundations. Login and quiz routes come next.",
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse, tags=["operations"])
def health(db: Annotated[Session, Depends(get_db)]) -> HealthResponse:
    db.execute(text("SELECT 1"))
    return HealthResponse(status="ok", milestone="foundations")
