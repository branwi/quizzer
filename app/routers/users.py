from fastapi import APIRouter, Response

from app.dependencies import CurrentUser
from app.routers.auth import no_store
from app.schemas import UserPublic

router = APIRouter(tags=["users"])


@router.get("/me", response_model=UserPublic)
def me(user: CurrentUser, response: Response) -> UserPublic:
    no_store(response)
    return user
