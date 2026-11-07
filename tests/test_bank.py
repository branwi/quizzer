import pytest
from sqlalchemy import func, select

from app.models import Quiz


def assert_safe(response):
    assert "correct_answer" not in response.text
    assert "explanation" not in response.text


def login_teacher(client, workflow):
    assert client.post("/api/auth/login", json=workflow["teacher_credentials"]).status_code == 200


def test_bank_only_public_with_role_specific_serialization(client, workflow):
    response = client.get("/api/bank/questions")
    assert response.status_code == 200
    assert response.json()["view"] == "student"
    assert response.json()["total"] == 2
    assert {q["id"] for q in response.json()["items"]} == {
        workflow["questions"][0]["id"],
        workflow["questions"][1]["id"],
    }
    assert_safe(response)
    login_teacher(client, workflow)
    teacher = client.get("/api/bank/questions")
    assert teacher.json()["view"] == "teacher"
    assert all("correct_answer" in q and "explanation" in q for q in teacher.json()["items"])
    assert teacher.json()["total"] == 2


def test_bank_filters_literal_search_and_pagination(client, workflow):
    login_teacher(client, workflow)
    client.post(
        "/api/questions",
        json={
            "type": "true_false",
            "text": "100% under_score",
            "topic": "Science",
            "correct_answer": False,
            "is_public": True,
        },
    )
    client.post("/api/auth/login", json=workflow["student_credentials"])
    first = client.get("/api/bank/questions", params={"page_size": 2}).json()
    second = client.get("/api/bank/questions", params={"page_size": 2, "page": 2}).json()
    assert first["total"] == second["total"] == 3
    assert not {q["id"] for q in first["items"]} & {q["id"] for q in second["items"]}
    for query in ("science", "%", "_"):
        result = client.get("/api/bank/questions", params={"q": query})
        assert result.json()["total"] == 1
        assert_safe(result)
    assert client.get("/api/bank/questions", params={"topic": "Math"}).json()["total"] == 2
    assert client.get("/api/bank/questions", params={"type": "true_false"}).json()["total"] == 2
    assert client.get("/api/bank/questions", params={"page": 99}).json()["items"] == []
    for params in ({"page_size": 51}, {"page": 0}, {"is_public": "false"}, {"type": "essay"}):
        assert client.get("/api/bank/questions", params=params).status_code == 422


@pytest.mark.parametrize("selection", ["private", "missing", "mixed", "duplicate", "empty"])
def test_practice_validates_every_selected_question_atomically(client, workflow, db, selection):
    ids = {
        "private": [workflow["questions"][2]["id"]],
        "missing": [99999],
        "mixed": [q["id"] for q in workflow["questions"]],
        "duplicate": [workflow["questions"][0]["id"]] * 2,
        "empty": [],
    }[selection]
    before = db.scalar(select(func.count()).select_from(Quiz))
    assert client.post("/api/quizzes/practice", json={"question_ids": ids}).status_code == 422
    assert db.scalar(select(func.count()).select_from(Quiz)) == before


def test_practice_reuses_grading_and_has_unlimited_retakes(client, workflow):
    response = client.post(
        "/api/quizzes/practice",
        json={
            "title": "My practice",
            "question_ids": [workflow["questions"][0]["id"]],
        },
    )
    assert response.status_code == 201, response.text
    quiz = response.json()
    assert quiz["kind"] == "self_made"
    assert quiz["status"] == "published"
    assert quiz["max_attempts"] is None
    assert quiz["due_at"] is None
    assert_safe(response)
    assert client.get("/api/quizzes").json()["total"] == 1
    assert client.get("/api/quizzes/assigned").json()["total"] == 1
    for _ in range(3):
        active = client.post(f"/api/quizzes/{quiz['id']}/attempts")
        assert active.status_code == 201
        assert_safe(active)
        attempt = active.json()
        result = client.post(
            f"/api/attempts/{attempt['id']}/submit",
            json={
                "answers": [
                    {"quiz_question_id": attempt["questions"][0]["id"], "response": "a"},
                ]
            },
        )
        assert result.status_code == 200
        assert result.json()["score"] == result.json()["max_score"] == 1
    assert_safe(client.get(f"/api/quizzes/{quiz['id']}"))
    teacher = client.post("/api/auth/login", json=workflow["teacher_credentials"])
    assert teacher.status_code == 200
    assert client.get(f"/api/quizzes/{quiz['id']}").status_code == 404
    assert (
        client.post(
            "/api/quizzes/practice",
            json={
                "question_ids": [workflow["questions"][0]["id"]],
            },
        ).status_code
        == 403
    )


def test_practice_owner_only_and_frozen_even_after_bank_question_deleted(client, workflow):
    question_id = workflow["questions"][0]["id"]
    practice = client.post("/api/quizzes/practice", json={"question_ids": [question_id]}).json()
    login_teacher(client, workflow)
    client.delete(f"/api/questions/{question_id}")
    client.post("/api/auth/login", json=workflow["student_credentials"])
    active = client.post(f"/api/quizzes/{practice['id']}/attempts").json()
    assert active["questions"][0]["question_id"] is None
    result = client.post(
        f"/api/attempts/{active['id']}/submit",
        json={
            "answers": [
                {"quiz_question_id": active["questions"][0]["id"], "response": "a"},
            ]
        },
    )
    assert result.json()["score"] == 1
    other = {"email": "other-student@example.test", "password": "another-student-password"}
    client.post("/api/auth/register", json={**other, "role": "student", "name": "Other"})
    client.post("/api/auth/login", json=other)
    assert client.get(f"/api/quizzes/{practice['id']}").status_code == 404
    assert client.post(f"/api/quizzes/{practice['id']}/attempts").status_code == 404
    assert client.get(f"/api/attempts/{active['id']}").status_code == 404


def test_other_teachers_public_questions_can_be_used_but_rechecked_at_publish(client, workflow):
    other = {"email": "public-author@example.test", "password": "public-author-password"}
    client.post("/api/auth/register", json={**other, "name": "Author", "role": "teacher"})
    client.post("/api/auth/login", json=other)
    content = {"type": "true_false", "text": "Shared", "topic": "Logic", "correct_answer": True}
    public = client.post("/api/questions", json={**content, "is_public": True}).json()
    private = client.post("/api/questions", json=content).json()
    login_teacher(client, workflow)
    assert (
        client.post(
            "/api/quizzes",
            json={
                "title": "Unavailable",
                "questions": [
                    {"question_id": public["id"]},
                    {"question_id": private["id"]},
                ],
            },
        ).status_code
        == 422
    )
    draft = client.post(
        "/api/quizzes",
        json={
            "title": "Shared",
            "questions": [
                {"question_id": public["id"]},
            ],
        },
    ).json()
    client.post("/api/auth/login", json=other)
    client.put(f"/api/questions/{public['id']}", json=content)
    login_teacher(client, workflow)
    path = f"/api/quizzes/{draft['id']}"
    assert client.get(path).json()["questions"][0]["content"] is None
    assert client.post(path + "/publish").status_code == 422
    assert client.get(path).json()["status"] == "draft"
    client.post("/api/auth/login", json=other)
    client.put(
        f"/api/questions/{public['id']}",
        json={**content, "is_public": True, "correct_answer": False},
    )
    login_teacher(client, workflow)
    published = client.post(path + "/publish")
    assert published.status_code == 200
    assert published.json()["questions"][0]["content"]["correct_answer"] is False
