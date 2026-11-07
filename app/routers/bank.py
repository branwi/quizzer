from typing import Annotated

from fastapi import APIRouter, Query, Response

from app.dependencies import CurrentUser, DbSession
from app.routers.auth import no_store
from app.services import bank
from app.workflow_schemas import BankFilters, BankPage

router = APIRouter(prefix="/bank", tags=["bank"])


@router.get("/questions", response_model=BankPage)
def search(
    filters: Annotated[BankFilters, Query()], user: CurrentUser, db: DbSession, response: Response
) -> BankPage:
    no_store(response)
    return bank.search(db, user, filters)
