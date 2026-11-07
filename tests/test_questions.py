from copy import deepcopy
from itertools import product

import pytest
from pydantic import TypeAdapter
from sqlalchemy import func, select

from app.models import Question, QuizQuestion, User
from app.schemas import QuestionCreate, QuestionFilters
from app.services import questions
from app.services.access import PermissionDenied
from app.services.auth import public_user

QUESTION_TYPES = [
    {
        "type": "mcq",
        "choices": [{"id": "a", "text": "Yes"}, {"id": "b", "text": "No"}],
        "correct_answer": "a",
    },
    {"type": "true_false", "correct_answer": False},
    {"type": "short_answer", "correct_answer": ["four", "4"]},
]
METHODS = [
    ("GET", "/api/questions"),
    ("POST", "/api/questions"),
    ("GET", "/api/questions/1"),
    ("PUT", "/api/questions/1"),
    ("DELETE", "/api/questions/1"),
]


@pytest.mark.parametrize("content", QUESTION_TYPES)
def test_create_get_list_and_delete_each_type(client, teacher, content):
    payload = {"text": "  A prompt  ", "topic": " Math ", **content}
    response = client.post("/api/questions", json=payload)
    assert response.status_code == 201, response.text
    question = response.json()
    assert question["author_id"] == teacher["id"]
    assert question["text"] == "A prompt"
    assert question["topic"] == "Math"
    assert question["is_public"] is False
    assert question["correct_answer"] == content["correct_answer"]
    assert question["created_at"].endswith("Z")
    path = f"/api/questions/{question['id']}"
    assert client.get(path).json() == question
    assert client.get("/api/questions").json() == {
        "items": [question],
        "total": 1,
        "page": 1,
        "page_size": 20,
    }
    deleted = client.delete(path)
    assert deleted.status_code == 204
    assert deleted.content == b""
    assert client.get(path).status_code == 404
    assert client.get("/api/questions").json()["total"] == 0


@pytest.mark.parametrize("first,second", list(product(QUESTION_TYPES, repeat=2)))
def test_put_can_replace_each_question_type(client, teacher, first, second):
    question = client.post(
        "/api/questions",
        json={
            "text": "Original",
            "topic": "Before",
            "is_public": True,
            "explanation": "Old",
            **first,
        },
    ).json()
    payload = {"text": "Updated", "topic": "After", **second}
    response = client.put(f"/api/questions/{question['id']}", json=payload)
    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["id"] == question["id"]
    assert updated["author_id"] == teacher["id"]
    assert updated["created_at"] == question["created_at"]
    assert updated["updated_at"] >= question["updated_at"]
    assert updated["text"] == "Updated"
    assert updated["type"] == second["type"]
    assert updated["correct_answer"] == second["correct_answer"]
    assert updated["choices"] == second.get("choices")
    assert updated["explanation"] is None
    assert updated["is_public"] is False  # PUT is a full replacement.


@pytest.mark.parametrize(
    "changes",
    [
        {"choices": []},
        {"choices": [{"id": "a", "text": "Only one"}]},
        {"choices": [{"id": str(i), "text": "Choice"} for i in range(7)]},
        {"choices": [{"id": "a", "text": "A"}, {"id": "a", "text": "B"}]},
        {"choices": [{"id": "a", "text": "A"}, {"id": " a ", "text": "B"}]},
        {"choices": [{"id": " ", "text": "A"}, {"id": "b", "text": "B"}]},
        {"choices": [{"id": "a", "text": " "}, {"id": "b", "text": "B"}]},
        {"correct_answer": "missing"},
        {"correct_answer": True},
        {"text": "  "},
        {"topic": "  "},
        {"is_public": "true"},
        {"author_id": 999},
        {"type": "essay"},
    ],
)
def test_invalid_mcq_rejected_without_inserting(client, teacher, db, mcq, changes):
    response = client.post("/api/questions", json={**mcq, **changes})
    assert response.status_code == 422, response.text
    assert db.scalar(select(func.count()).select_from(Question)) == 0


@pytest.mark.parametrize("value", [1, 0, "true", "false", None, [], {}])
def test_true_false_requires_actual_boolean(client, teacher, value):
    response = client.post(
        "/api/questions",
        json={
            "type": "true_false",
            "text": "True?",
            "topic": "Logic",
            "correct_answer": value,
        },
    )
    assert response.status_code == 422


@pytest.mark.parametrize("value", [[], [""], [" \t\n"], "answer", [123], None])
def test_short_answer_requires_nonblank_accepted_strings(client, teacher, value):
    response = client.post(
        "/api/questions",
        json={
            "type": "short_answer",
            "text": "Answer?",
            "topic": "General",
            "correct_answer": value,
        },
    )
    assert response.status_code == 422


@pytest.mark.parametrize("content", QUESTION_TYPES[1:])
def test_non_mcq_choices_rejected(client, teacher, content):
    response = client.post(
        "/api/questions",
        json={
            "text": "Question",
            "topic": "General",
            **content,
            "choices": [{"id": "a", "text": "Not allowed"}],
        },
    )
    assert response.status_code == 422


def test_invalid_put_preserves_original(client, teacher, mcq):
    question = client.post("/api/questions", json=mcq).json()
    path = f"/api/questions/{question['id']}"
    assert client.put(path, json={**mcq, "correct_answer": "bad"}).status_code == 422
    assert client.get(path).json() == question


@pytest.mark.parametrize("method,path", METHODS)
def test_question_routes_require_login(client, mcq, method, path):
    response = client.request(method, path, json=mcq if method in ("POST", "PUT") else None)
    assert response.status_code == 401


@pytest.mark.parametrize("method,path", METHODS)
def test_students_cannot_access_question_crud(client, credentials, registered, mcq, method, path):
    assert client.post("/api/auth/login", json=credentials).status_code == 200
    response = client.request(method, path, json=mcq if method in ("POST", "PUT") else None)
    assert response.status_code == 403
    assert "correct_answer" not in response.text
    assert "explanation" not in response.text


def test_other_teacher_cannot_read_edit_delete_or_list_own_question(client, teacher, mcq):
    question = client.post("/api/questions", json={**mcq, "is_public": True}).json()
    credentials = {"email": "other-teacher@example.test", "password": "other-teacher-password"}
    client.post("/api/auth/register", json={**credentials, "name": "Other", "role": "teacher"})
    client.post("/api/auth/login", json=credentials)
    path = f"/api/questions/{question['id']}"
    for method in ("GET", "PUT", "DELETE"):
        response = client.request(method, path, json=mcq if method == "PUT" else None)
        assert response.status_code == 404
        assert "correct_answer" not in response.text
    assert client.get("/api/questions").json()["total"] == 0


def test_filters_pagination_and_literal_search(client, teacher, mcq):
    payloads = [
        {**mcq, "text": "100% certain", "topic": "Math", "is_public": True},
        {**mcq, "text": "under_score", "topic": "Science"},
        {"text": "Logic question", "topic": "Math", "type": "true_false", "correct_answer": True},
    ]
    created = [client.post("/api/questions", json=payload).json() for payload in payloads]
    page1 = client.get("/api/questions", params={"page_size": 2}).json()
    page2 = client.get("/api/questions", params={"page_size": 2, "page": 2}).json()
    assert page1["total"] == page2["total"] == 3
    assert [q["id"] for q in page1["items"] + page2["items"]] == [
        q["id"] for q in reversed(created)
    ]
    assert client.get("/api/questions", params={"page": 99}).json()["items"] == []
    assert client.get("/api/questions", params={"q": "science"}).json()["total"] == 1
    assert client.get("/api/questions", params={"q": "%"}).json()["total"] == 1
    assert client.get("/api/questions", params={"q": "_"}).json()["total"] == 1
    assert client.get("/api/questions", params={"topic": "Math"}).json()["total"] == 2
    assert client.get("/api/questions", params={"type": "true_false"}).json()["total"] == 1
    assert client.get("/api/questions", params={"is_public": "false"}).json()["total"] == 2
    assert (
        client.get("/api/questions", params={"topic": "Math", "is_public": "true"}).json()["total"]
        == 1
    )


@pytest.mark.parametrize(
    "params",
    [
        {"page": 0},
        {"page": 10**30},
        {"page_size": 0},
        {"page_size": 51},
        {"type": "essay"},
        {"q": "x" * 201},
    ],
)
def test_bad_pagination_and_filters_rejected(client, teacher, params):
    assert client.get("/api/questions", params=params).status_code == 422


@pytest.mark.parametrize("question_id", [0, -1, 2**63, "not-an-id"])
def test_invalid_question_id_rejected(client, teacher, question_id):
    assert client.get(f"/api/questions/{question_id}").status_code == 422


def test_question_api_preserves_published_snapshots(client, seeded):
    from scripts.seed import DEMO_PASSWORD

    client.post(
        "/api/auth/login", json={"email": "teacher@example.test", "password": DEMO_PASSWORD}
    )
    link = seeded.scalar(select(QuizQuestion).order_by(QuizQuestion.position))
    original = deepcopy(link.snapshot)
    path = f"/api/questions/{link.question_id}"
    assert (
        client.put(
            path,
            json={
                "type": "short_answer",
                "text": "Changed",
                "topic": "New",
                "correct_answer": ["new"],
            },
        ).status_code
        == 200
    )
    seeded.refresh(link)
    assert link.snapshot == original
    assert client.delete(path).status_code == 204
    seeded.refresh(link)
    assert link.question_id is None
    assert link.snapshot == original


def test_service_enforces_roles_and_student_projection(db, registered, mcq, seeded):
    actor = public_user(db.get(User, registered["id"]))
    data = TypeAdapter(QuestionCreate).validate_python(mcq)
    with pytest.raises(PermissionDenied):
        questions.create(db, actor, data)
    with pytest.raises(PermissionDenied):
        questions.list_own(db, actor, QuestionFilters())
    question = db.scalar(select(Question))
    for operation in (
        lambda: questions.get(db, actor, question.id),
        lambda: questions.replace(db, actor, question.id, data),
        lambda: questions.delete(db, actor, question.id),
    ):
        with pytest.raises(PermissionDenied):
            operation()
    safe = questions.for_student(question).model_dump()
    assert "correct_answer" not in safe
    assert "explanation" not in safe
