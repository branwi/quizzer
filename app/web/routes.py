from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request
from fastapi.responses import RedirectResponse
from pydantic import ValidationError

from app.dependencies import AppSettings, DbSession
from app.models import Role
from app.schemas import LoginRequest, QuestionFilters, RegisterRequest
from app.security import COOKIE_NAME
from app.services import analytics, attempts, auth, bank, questions, quizzes
from app.services.errors import ServiceError
from app.web.common import (
    BrowserForm,
    WebStudent,
    WebTeacher,
    WebUser,
    render,
    set_settings,
)
from app.web.forms import messages, question_data, question_values, quiz_data, selected
from app.workflow_schemas import (
    AssignmentCreate,
    AttemptSubmit,
    BankFilters,
    PageFilters,
    PracticeCreate,
)

router = APIRouter(include_in_schema=False, dependencies=[Depends(set_settings)])
ResourceId = Annotated[int, Path(ge=1, le=2**63 - 1)]


def query_filters(request, cls):
    return cls.model_validate(
        {
            key: value
            for key, value in request.query_params.items()
            if key in cls.model_fields and value != ""
        }
    )


def go(path):
    return RedirectResponse(path, status_code=303, headers={"Cache-Control": "no-store"})


@router.get("/login")
def login_page(request: Request):
    return render(request, "auth.html", title="Welcome back", mode="login", values={}, errors=[])


@router.get("/register")
def register_page(request: Request):
    return render(
        request, "auth.html", title="Make room for learning", mode="register", values={}, errors=[]
    )


@router.post("/login")
def login(request: Request, form: BrowserForm, db: DbSession, settings: AppSettings):
    try:
        data = LoginRequest.model_validate(
            {"email": form.get("email"), "password": form.get("password")}
        )
        result = auth.authenticate(db, data, settings)
    except (ValidationError, auth.InvalidCredentials):
        return render(
            request,
            "auth.html",
            status_code=401,
            title="Welcome back",
            mode="login",
            values={"email": form.get("email", "")},
            errors=["Check your email and password and try again."],
        )
    response = go("/dashboard")
    response.set_cookie(
        COOKIE_NAME,
        result.access_token,
        max_age=result.expires_in,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return response


@router.post("/register")
def register(request: Request, form: BrowserForm, db: DbSession):
    values = {key: form.get(key, "") for key in ("name", "email", "role")}
    try:
        data = RegisterRequest.model_validate({**values, "password": form.get("password")})
        auth.register(db, data)
    except (ValidationError, auth.EmailAlreadyRegistered) as exc:
        errors = (
            ["That email is already registered. Try signing in."]
            if isinstance(exc, auth.EmailAlreadyRegistered)
            else messages(exc)
        )
        return render(
            request,
            "auth.html",
            status_code=422,
            title="Make room for learning",
            mode="register",
            values=values,
            errors=errors,
        )
    return go("/login?registered=1")


@router.post("/logout")
def logout(user: WebUser, form: BrowserForm, settings: AppSettings):
    response = go("/login")
    response.delete_cookie(
        COOKIE_NAME, path="/", httponly=True, secure=settings.cookie_secure, samesite="lax"
    )
    return response


@router.get("/")
@router.get("/dashboard")
def dashboard(request: Request, user: WebUser, db: DbSession):
    recent = PageFilters(page_size=5)
    if user.role == Role.TEACHER:
        return render(
            request,
            "dashboard.html",
            title="Your teaching workspace",
            nav="dashboard",
            question_page=questions.list_own(db, user, QuestionFilters(page_size=5)),
            quiz_page=quizzes.list_quizzes(db, user, recent),
            student_page=quizzes.students(db, user, recent),
        )
    return render(
        request,
        "dashboard.html",
        title="A little progress, every day",
        nav="dashboard",
        assigned=quizzes.list_quizzes(db, user, recent, assigned=True),
        practice=quizzes.list_quizzes(db, user, recent),
        history=attempts.history(db, user, recent),
    )


@router.get("/questions")
def question_list(request: Request, user: WebTeacher, db: DbSession):
    filters = query_filters(request, QuestionFilters)
    page = questions.list_own(db, user, filters)
    return render(
        request,
        "questions.html",
        title="Your question collection",
        nav="questions",
        page=page,
        filters=filters,
    )


@router.get("/questions/new")
def question_new(request: Request, user: WebTeacher):
    return render(
        request,
        "question_form.html",
        title="A good question starts here",
        nav="questions",
        values=question_values(),
        question_id=None,
        errors=[],
    )


@router.get("/questions/{question_id}/edit")
def question_edit(request: Request, question_id: ResourceId, user: WebTeacher, db: DbSession):
    question = questions.get(db, user, question_id)
    return render(
        request,
        "question_form.html",
        title="Refine your question",
        nav="questions",
        values=question_values(question),
        question_id=question_id,
        errors=[],
    )


@router.post("/questions")
def question_create(request: Request, user: WebTeacher, form: BrowserForm, db: DbSession):
    try:
        questions.create(db, user, question_data(form))
    except (ValidationError, ValueError) as exc:
        return render(
            request,
            "question_form.html",
            status_code=422,
            title="A good question starts here",
            nav="questions",
            values=question_values(form=form),
            question_id=None,
            errors=messages(exc),
        )
    return go("/questions")


@router.post("/questions/{question_id}/edit")
def question_update(
    request: Request, question_id: ResourceId, user: WebTeacher, form: BrowserForm, db: DbSession
):
    try:
        questions.replace(db, user, question_id, question_data(form))
    except (ValidationError, ValueError) as exc:
        return render(
            request,
            "question_form.html",
            status_code=422,
            title="Refine your question",
            nav="questions",
            values=question_values(form=form),
            question_id=question_id,
            errors=messages(exc),
        )
    return go("/questions")


@router.post("/questions/{question_id}/delete")
def question_delete(question_id: ResourceId, user: WebTeacher, form: BrowserForm, db: DbSession):
    questions.delete(db, user, question_id)
    return go("/questions")


def builder(request, user, db, *, quiz=None, form=None, errors=None):
    filters = query_filters(request, BankFilters)
    page = quizzes.available_questions(db, user, filters)
    initial = (
        [{"id": q.question_id, "points": q.points} for q in quiz.questions if q.question_id]
        if quiz
        else []
    )
    values = {
        "title": quiz.title if quiz else "",
        "max_attempts": quiz.max_attempts if quiz else 1,
        "due_at": quiz.due_at.strftime("%Y-%m-%dT%H:%M") if quiz and quiz.due_at else "",
    }
    if form is not None:
        values.update(dict(form))
        try:
            initial = [item.model_dump() for item in selected(form)]
        except (ValueError, ValidationError):
            initial = []
    elif request.query_params.get("selection"):
        initial = [item.model_dump() for item in selected(request.query_params)]
    context = dict(
        title="Build something worth knowing",
        nav="quizzes",
        page=page,
        filters=filters,
        values=values,
        initial_selection=initial,
        initial_labels=quizzes.selection_labels(db, user, [item["id"] for item in initial]),
        quiz=quiz,
        errors=errors or [],
        selected_map={item["id"]: item["points"] for item in initial},
        catalog_base=f"/quizzes/{quiz.id}/edit" if quiz else "/quizzes/new",
        selection_mode="builder",
    )
    return render(
        request,
        "partials/catalog.html" if request.headers.get("HX-Request") else "quiz_form.html",
        status_code=422 if errors else 200,
        **context,
    )


@router.get("/quizzes/new")
def quiz_new(request: Request, user: WebTeacher, db: DbSession):
    return builder(request, user, db)


@router.get("/quizzes/{quiz_id}/edit")
def quiz_edit(request: Request, quiz_id: ResourceId, user: WebTeacher, db: DbSession):
    quiz = quizzes.get(db, user, quiz_id)
    if quiz.status != "draft":
        return go(f"/quizzes/{quiz_id}")
    return builder(request, user, db, quiz=quiz)


@router.post("/quizzes")
def quiz_create(request: Request, user: WebTeacher, form: BrowserForm, db: DbSession):
    try:
        result = quizzes.create(db, user, quiz_data(form))
    except (ValidationError, ValueError, ServiceError) as exc:
        return builder(request, user, db, form=form, errors=messages(exc))
    return go(f"/quizzes/{result.id}")


@router.post("/quizzes/{quiz_id}/edit")
def quiz_update(
    request: Request, quiz_id: ResourceId, user: WebTeacher, form: BrowserForm, db: DbSession
):
    try:
        result = quizzes.replace(db, user, quiz_id, quiz_data(form))
    except (ValidationError, ValueError) as exc:
        return builder(
            request, user, db, quiz=quizzes.get(db, user, quiz_id), form=form, errors=messages(exc)
        )
    return go(f"/quizzes/{result.id}")


@router.get("/quizzes")
def quiz_list(request: Request, user: WebUser, db: DbSession):
    filters = query_filters(request, PageFilters)
    return render(
        request,
        "quizzes.html",
        title="Your quizzes",
        nav="quizzes",
        page=quizzes.list_quizzes(db, user, filters),
        filters=filters,
    )


@router.get("/assigned")
def assigned_page(request: Request, user: WebStudent, db: DbSession):
    filters = query_filters(request, PageFilters)
    return render(
        request,
        "quizzes.html",
        title="Your assigned quizzes",
        nav="assigned",
        assigned_view=True,
        page=quizzes.list_quizzes(db, user, filters, assigned=True),
        filters=filters,
    )


@router.get("/quizzes/{quiz_id}")
def quiz_detail(request: Request, quiz_id: ResourceId, user: WebUser, db: DbSession):
    quiz = quizzes.get(db, user, quiz_id)
    count = (
        len(quizzes.assignment_ids(db, user, quiz_id).student_ids)
        if user.role == Role.TEACHER
        else None
    )
    return render(
        request,
        "quiz_detail.html",
        title=quiz.title,
        nav="quizzes",
        quiz=quiz,
        assigned_count=count,
    )


@router.post("/quizzes/{quiz_id}/publish")
def publish(quiz_id: ResourceId, user: WebTeacher, form: BrowserForm, db: DbSession):
    quizzes.publish(db, user, quiz_id)
    return go(f"/quizzes/{quiz_id}")


@router.get("/quizzes/{quiz_id}/assign")
def assign_page(request: Request, quiz_id: ResourceId, user: WebTeacher, db: DbSession):
    quiz = quizzes.get(db, user, quiz_id)
    if quiz.status != "published":
        return go(f"/quizzes/{quiz_id}")
    filters = query_filters(request, PageFilters)
    return render(
        request,
        "partials/students.html" if request.headers.get("HX-Request") else "assign.html",
        title="Send it to your students",
        nav="quizzes",
        quiz=quiz,
        page=quizzes.students(db, user, filters),
        filters=filters,
        assigned_ids=quizzes.assignment_ids(db, user, quiz_id).student_ids,
        catalog_base=f"/quizzes/{quiz_id}/assign",
        initial_selection=[],
    )


@router.post("/quizzes/{quiz_id}/assign")
def assign(quiz_id: ResourceId, user: WebTeacher, form: BrowserForm, db: DbSession):
    quizzes.assign(
        db,
        user,
        quiz_id,
        AssignmentCreate(student_ids=[item.id for item in selected(form, limit=500)]),
    )
    return go(f"/quizzes/{quiz_id}")


@router.get("/quizzes/{quiz_id}/results")
def result_page(request: Request, quiz_id: ResourceId, user: WebTeacher, db: DbSession):
    filters = query_filters(request, PageFilters)
    return render(
        request,
        "results.html",
        title="See what is sticking",
        nav="quizzes",
        quiz=quizzes.get(db, user, quiz_id),
        page=quizzes.results(db, user, quiz_id, filters),
        filters=filters,
        analytics=analytics.for_quiz(db, user, quiz_id),
    )


@router.get("/bank")
def question_bank(request: Request, user: WebUser, db: DbSession):
    filters = query_filters(request, BankFilters)
    return render(
        request,
        "partials/catalog.html" if request.headers.get("HX-Request") else "bank.html",
        title="Good questions travel",
        nav="bank",
        page=bank.search(db, user, filters),
        filters=filters,
        catalog_base="/bank",
        selection_mode="bank",
        initial_selection=[],
        errors=[],
    )


@router.post("/practice")
def practice(request: Request, user: WebStudent, form: BrowserForm, db: DbSession):
    data = PracticeCreate(
        title=form.get("title") or "Practice quiz",
        question_ids=[item.id for item in selected(form)],
    )
    quiz = quizzes.practice(db, user, data)
    return go(f"/quizzes/{quiz.id}")


@router.post("/quizzes/{quiz_id}/start")
def start(quiz_id: ResourceId, user: WebStudent, form: BrowserForm, db: DbSession):
    attempt, _ = attempts.start(db, user, quiz_id)
    return go(f"/attempts/{attempt.id}")


@router.get("/attempts")
def history_page(request: Request, user: WebStudent, db: DbSession):
    filters = query_filters(request, PageFilters)
    return render(
        request,
        "history.html",
        title="Every attempt is progress",
        nav="history",
        page=attempts.history(db, user, filters),
        filters=filters,
    )


@router.get("/attempts/{attempt_id}")
def take_or_review(request: Request, attempt_id: ResourceId, user: WebStudent, db: DbSession):
    attempt = attempts.get(db, user, attempt_id)
    return render(
        request,
        "review.html" if attempt.state == "submitted" else "take.html",
        title="Your results" if attempt.state == "submitted" else "One question at a time",
        nav="history",
        attempt=attempt,
        errors=[],
        values={},
    )


@router.post("/attempts/{attempt_id}/submit")
def submit(
    request: Request, attempt_id: ResourceId, user: WebStudent, form: BrowserForm, db: DbSession
):
    attempt = attempts.get(db, user, attempt_id)
    types = {q.id: q.content.type for q in attempt.questions}
    try:
        answers = []
        for key, value in form.multi_items():
            if not key.startswith("answer_"):
                continue
            qid = int(key.removeprefix("answer_"))
            response = None if value == "" else value
            if types.get(qid) == "true_false" and value in ("true", "false"):
                response = value == "true"
            answers.append({"quiz_question_id": qid, "response": response})
        attempts.submit(db, user, attempt_id, AttemptSubmit(answers=answers))
    except (ValidationError, ValueError) as exc:
        return render(
            request,
            "take.html",
            status_code=422,
            title="One question at a time",
            nav="history",
            attempt=attempt,
            errors=messages(exc),
            values=dict(form),
        )
    return go(f"/attempts/{attempt_id}")
