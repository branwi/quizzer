import json
import re

import pytest
from sqlalchemy import select

from app.models import Question


def csrf(client, path="/login"):
    response = client.get(path)
    assert response.status_code == 200, response.text[:300]
    match = re.search(r'name="csrf_token" value="([^"]+)"', response.text)
    assert match, response.text[:500]
    return match.group(1)


def login(client, credentials):
    token = csrf(client)
    response = client.post("/login", data={**credentials, "csrf_token": token})
    assert response.status_code == 200, response.text[:500]
    assert response.url.path == "/dashboard"
    return response


def test_public_pages_assets_and_private_redirect(client):
    for path in ("/login", "/register"):
        response = client.get(path)
        assert response.status_code == 200
        assert "quizzer" in response.text
        assert response.headers["cache-control"] == "no-store"
    for path in ("/", "/dashboard", "/questions", "/quizzes", "/bank", "/attempts"):
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/login"
    for path in (
        "/static/app.css",
        "/static/app.js",
        "/static/vendor/htmx.min.js",
        "/static/favicon.svg",
    ):
        assert client.get(path).status_code == 200


def test_register_login_logout_with_normal_html_forms(client):
    data = {
        "name": "Web Student",
        "email": "web@example.test",
        "password": "web-student-password",
        "role": "student",
    }
    registered = client.post("/register", data={**data, "csrf_token": csrf(client, "/register")})
    assert registered.status_code == 200
    assert "Your account is ready" in registered.text
    dashboard = login(client, {key: data[key] for key in ("email", "password")})
    assert "Web Student" in dashboard.text
    assert data["password"] not in dashboard.text
    response = client.post(
        "/logout", data={"csrf_token": csrf(client, "/dashboard")}, follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/login"
    assert client.get("/api/me").status_code == 401


def test_csrf_missing_forged_or_wrong_account_tokens_rejected(client, teacher):
    token = csrf(client)
    for value in (None, "forged-token"):
        data = {"email": "teacher@example.test", "password": "teacher-test-password"}
        if value:
            data["csrf_token"] = value
        assert client.post("/login", data=data).status_code == 403
    client.post("/api/auth/logout")
    assert (
        client.post(
            "/login",
            data={
                "email": "teacher@example.test",
                "password": "teacher-test-password",
                "csrf_token": token,
            },
        ).status_code
        == 403
    )


def test_bad_login_does_not_echo_password(client):
    password = "never-echo-this-password"
    response = client.post(
        "/login",
        data={"email": "unknown@example.test", "password": password, "csrf_token": csrf(client)},
    )
    assert response.status_code == 401
    assert "Check your email and password" in response.text
    assert password not in response.text


@pytest.mark.parametrize(
    "content",
    [
        {
            "type": "mcq",
            "choice_id_0": "a",
            "choice_text_0": "Four",
            "choice_id_1": "b",
            "choice_text_1": "Five",
            "correct_choice": "0",
        },
        {"type": "true_false", "true_false_answer": "false"},
        {"type": "short_answer", "accepted_answers": "4\nfour"},
    ],
)
def test_question_editor_crud_all_types(client, teacher, db, content):
    payload = {"text": "A web question", "topic": "Math", "is_public": "on", **content}
    result = client.post(
        "/questions", data={**payload, "csrf_token": csrf(client, "/questions/new")}
    )
    assert result.status_code == 200, result.text[:500]
    question = db.scalar(select(Question))
    question_id = question.id
    assert question.type == content["type"]
    if question.type == "true_false":
        assert question.correct_answer is False
    path = f"/questions/{question.id}/edit"
    edited = client.post(
        path, data={**payload, "text": "Updated in the browser", "csrf_token": csrf(client, path)}
    )
    assert edited.status_code == 200
    db.refresh(question)
    assert question.text == "Updated in the browser"
    assert (
        client.post(
            f"/questions/{question.id}/delete", data={"csrf_token": csrf(client, "/questions")}
        ).status_code
        == 200
    )
    db.expire_all()
    assert db.scalar(select(Question.id).where(Question.id == question_id)) is None


def test_editor_validation_escapes_user_text_and_preserves_values(client, teacher):
    response = client.post(
        "/questions",
        data={
            "csrf_token": csrf(client, "/questions/new"),
            "type": "mcq",
            "text": '<script>alert("x")</script>',
            "topic": "Math",
        },
    )
    assert response.status_code == 422
    assert "&lt;script&gt;" in response.text
    assert '<script>alert("x")</script>' not in response.text


def test_teacher_html_builder_publish_assignment_results(client, workflow):
    login(client, workflow["teacher_credentials"])
    token = csrf(client, "/quizzes/new")
    selection = json.dumps([{"id": q["id"], "points": 2} for q in workflow["questions"]])
    created = client.post(
        "/quizzes",
        data={
            "title": "Built on the web",
            "selection": selection,
            "max_attempts": "2",
            "csrf_token": token,
        },
    )
    assert created.status_code == 200, created.text[:400]
    path = created.url.path
    assert "Built on the web" in created.text
    assert "6" in created.text
    edited = client.post(
        path + "/edit",
        data={
            "title": "Web draft revised",
            "selection": selection,
            "max_attempts": "",
            "csrf_token": csrf(client, path + "/edit"),
        },
    )
    assert edited.status_code == 200
    assert "Unlimited attempts" in edited.text
    published = client.post(path + "/publish", data={"csrf_token": csrf(client, path)})
    assert published.status_code == 200
    assigned = client.post(
        path + "/assign",
        data={
            "csrf_token": csrf(client, path + "/assign"),
            "selection": json.dumps([{"id": workflow["student"]["id"]}]),
        },
    )
    assert assigned.status_code == 200
    assert "1 student assigned" in assigned.text
    results = client.get(path + "/results")
    assert results.status_code == 200
    assert "How the scores fall" in results.text
    assert "The first submission" in results.text


def test_student_html_start_submit_review_history_and_bank(client, workflow):
    path = f"/quizzes/{workflow['quiz_id']}"
    page = client.get(path)
    assert page.status_code == 200
    assert "correct_answer" not in page.text
    assert workflow["questions"][0]["explanation"] not in page.text
    active = client.post(path + "/start", data={"csrf_token": csrf(client, path)})
    assert active.status_code == 200, active.text[:500]
    attempt_path = active.url.path
    assert "One question at a time" in active.text
    assert workflow["questions"][0]["explanation"] not in active.text
    ids = [q["id"] for q in client.get("/api" + attempt_path).json()["questions"]]
    review = client.post(
        attempt_path + "/submit",
        data={
            "csrf_token": csrf(client, attempt_path),
            f"answer_{ids[0]}": "a",
            f"answer_{ids[1]}": "false",
            f"answer_{ids[2]}": " FOUR ",
        },
    )
    assert review.status_code == 200, review.text[:500]
    assert "7" in review.text and "Correct answer" in review.text
    assert workflow["questions"][0]["explanation"] in review.text
    assert "Review" in client.get("/attempts").text
    assert workflow["quiz"]["title"] in client.get("/attempts").text
    assert (
        client.post(
            attempt_path + "/submit", data={"csrf_token": csrf(client, attempt_path)}
        ).status_code
        == 409
    )
    for forbidden in (
        "/questions",
        "/questions/new",
        "/quizzes/new",
        path + "/results",
        path + "/assign",
    ):
        assert client.get(forbidden).status_code == 403


def test_htmx_bank_partial_and_practice_form(client, workflow):
    response = client.get("/bank", params={"q": "Math", "type": ""}, headers={"HX-Request": "true"})
    assert response.status_code == 200, response.text[:300]
    assert "<!doctype" not in response.text
    assert "correct_answer" not in response.text
    assert "explanation" not in response.text
    assert "HX-Request" in response.headers["vary"]
    result = client.post(
        "/practice",
        data={
            "csrf_token": csrf(client, "/bank"),
            "title": "Browser practice",
            "selection": json.dumps([{"id": workflow["questions"][0]["id"]}]),
        },
    )
    assert result.status_code == 200
    assert "Browser practice" in result.text
    assert "Unlimited attempts" in result.text
    assert client.get("/dashboard").status_code == 200


def test_invalid_filters_and_empty_selection_produce_html_errors(client, workflow):
    assert client.get("/bank?page=0").status_code == 422
    response = client.post(
        "/practice", data={"csrf_token": csrf(client, "/bank"), "selection": "[]"}
    )
    assert response.status_code == 422
    assert "Let’s take a step back" in response.text


def test_assignment_pagination_and_invalid_selection_errors(client, workflow):
    page = client.get("/assigned?page_size=1")
    assert page.status_code == 200
    assert workflow["quiz"]["title"] in page.text
    for selection in ("not-json", '[{"id": true}]', '[{"id": 1, "points": true}]'):
        response = client.post(
            "/practice", data={"csrf_token": csrf(client, "/bank"), "selection": selection}
        )
        assert response.status_code == 422


def test_expired_browser_session_redirects_htmx_to_sign_in(client):
    client.cookies.set("access_token", "invalid")
    response = client.get("/bank", headers={"HX-Request": "true"})
    assert response.headers["HX-Redirect"] == "/login"
