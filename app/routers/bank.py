from typing import Annotated

from fastapi import APIRouter, Query

from app.dependencies import CurrentUser, DbSession
from app.schemas import BankFilters, BankPage
from app.services import bank

router = APIRouter(prefix="/bank", tags=["bank"])


@router.get("/questions", response_model=BankPage)
def search(filters: Annotated[BankFilters, Query()], user: CurrentUser, db: DbSession) -> BankPage:
    return bank.search(db, user, filters)
