import hashlib
import hmac
from pathlib import Path
from secrets import token_urlsafe
from typing import Annotated
from urllib.parse import urlencode

from fastapi import Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from starlette.datastructures import FormData

from app.config import get_settings
from app.dependencies import AppSettings, CurrentUser
from app.schemas import UserPublic
from app.security import COOKIE_NAME, signing_key
from app.services.access import require_student, require_teacher

templates = Jinja2Templates(directory=Path(__file__).resolve().parents[1] / "templates")
CSRF_COOKIE = "quizzer_csrf"


def is_web(request: Request) -> bool:
    return (
        not request.url.path.startswith(("/api", "/static", "/docs", "/redoc", "/openapi"))
        and request.url.path != "/health"
    )


def set_settings(request: Request, settings: AppSettings) -> None:
    request.state.web_settings = settings


def web_user(request: Request, user: CurrentUser) -> UserPublic:
    request.state.web_user = user
    return user


WebUser = Annotated[UserPublic, Depends(web_user)]


def web_teacher(user: WebUser) -> UserPublic:
    require_teacher(user)
    return user


def web_student(user: WebUser) -> UserPublic:
    require_student(user)
    return user


WebTeacher = Annotated[UserPublic, Depends(web_teacher)]
WebStudent = Annotated[UserPublic, Depends(web_student)]


def _signature(request: Request, nonce: str) -> str:
    settings = getattr(request.state, "web_settings", None) or get_settings()
    binding = request.cookies.get(COOKIE_NAME, "anonymous")
    return hmac.new(
        signing_key(settings).encode(), (nonce + ":" + binding).encode(), hashlib.sha256
    ).hexdigest()


def valid_csrf(request: Request, token: str) -> bool:
    nonce, separator, signature = token.partition(".")
    return bool(separator and nonce and hmac.compare_digest(signature, _signature(request, nonce)))


async def form_data(request: Request) -> FormData:
    form = await request.form()
    cookie, submitted = request.cookies.get(CSRF_COOKIE, ""), form.get("csrf_token", "")
    if (
        not isinstance(submitted, str)
        or not cookie
        or not hmac.compare_digest(cookie, submitted)
        or not valid_csrf(request, cookie)
    ):
        raise HTTPException(403, "This form expired. Reload the page and try again.")
    return form


BrowserForm = Annotated[FormData, Depends(form_data)]


def page_link(base: str, filters, page: int) -> str:
    query = filters.model_dump(mode="json", exclude_none=True) if filters else {}
    return base + "?" + urlencode({**query, "page": page})


templates.env.globals["page_link"] = page_link


def render(request: Request, template: str, *, status_code=200, **context):
    settings = getattr(request.state, "web_settings", None) or get_settings()
    token = request.cookies.get(CSRF_COOKIE, "")
    if not valid_csrf(request, token):
        nonce = token_urlsafe(32)
        token = nonce + "." + _signature(request, nonce)
    response = templates.TemplateResponse(
        request=request,
        name=template,
        status_code=status_code,
        context={"user": getattr(request.state, "web_user", None), "csrf_token": token, **context},
        headers={"Cache-Control": "no-store", "Pragma": "no-cache", "Vary": "Cookie, HX-Request"},
    )
    response.set_cookie(
        CSRF_COOKIE, token, httponly=True, secure=settings.cookie_secure, samesite="lax", path="/"
    )
    return response


def error_page(request: Request, status_code: int, message: str):
    return render(
        request,
        "error.html",
        status_code=status_code,
        title="Something needs attention",
        message=message,
    )
