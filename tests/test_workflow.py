from copy import deepcopy
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.database import utc_now
from app.models import Answer, Attempt, Quiz, QuizAssignment, QuizQuestion


def assert_safe(value):
    if isinstance(value, dict):
        assert not {"correct_answer", "explanation"} & value.keys()
        for child in value.values():
            assert_safe(child)
    elif isinstance(value, list):
        for child in value:
            assert_safe(child)


def teacher_login(client, flow):
    assert client.post("/api/auth/login", json=flow["teacher_credentials"]).status_code == 200


def start(client, flow):
    response = client.post(f"/api/quizzes/{flow['quiz_id']}/attempts")
    assert response.status_code == 201, response.text
    assert_safe(response.json())
    return response.json()


def test_weighted_attempt_resume_submit_review_and_results(client, workflow, db):
    flow = workflow
    assigned = client.get("/api/quizzes/assigned").json()
    assert assigned["total"] == 1
    assert assigned["items"][0]["id"] == flow["quiz_id"]
    assert_safe(assigned)
    quiz_path = f"/api/quizzes/{flow['quiz_id']}"
    assert_safe(client.get(quiz_path).json())
    attempt = start(client, flow)
    assert attempt["max_score"] == 10
    resumed = client.post(quiz_path + "/attempts")
    assert resumed.status_code == 200
    assert resumed.json() == attempt
    assert_safe(client.get(f"/api/attempts/{attempt['id']}").json())
    assert db.scalar(select(func.count()).select_from(Answer)) == 0
    payload = {
        "answers": [
            {"quiz_question_id": question["id"], "response": response}
            for question, response in zip(
                attempt["questions"], ("a", False, "  FOUR\t"), strict=True
            )
        ]
    }
    submitted = client.post(f"/api/attempts/{attempt['id']}/submit", json=payload)
    assert submitted.status_code == 200, submitted.text
    review = submitted.json()
    assert review["state"] == "submitted"
    assert review["score"] == 7
    assert [item["points_awarded"] for item in review["questions"]] == [2, 0, 5]
    assert review["questions"][0]["content"]["correct_answer"] == "a"
    assert review["questions"][0]["content"]["explanation"]
    assert client.get(f"/api/attempts/{attempt['id']}").json() == review
    assert client.post(f"/api/attempts/{attempt['id']}/submit", json=payload).status_code == 409
    assert client.post(quiz_path + "/attempts").status_code == 409
    assert db.scalar(select(func.count()).select_from(Answer)) == 3
    assert_safe(client.get(quiz_path).json())
    teacher_login(client, flow)
    results = client.get(quiz_path + "/results").json()
    assert results["total"] == 1
    assert results["items"][0]["score"] == 7
    assert results["items"][0]["student_id"] == flow["student"]["id"]
    assert_safe(results)
    students = client.get("/api/students").json()
    assert students["total"] == 1
    assert students["items"][0]["role"] == "student"
    assert "password_hash" not in str(students)


def test_omitted_answers_are_stored_as_wrong(client, workflow, db):
    attempt = start(client, workflow)
    result = client.post(f"/api/attempts/{attempt['id']}/submit", json={"answers": []})
    assert result.status_code == 200, result.text
    assert result.json()["score"] == 0
    assert all(q["response"] is None and (not q["is_correct"]) for q in result.json()["questions"])
    assert db.scalar(select(func.count()).select_from(Answer)) == 3


def test_draft_replace_publish_and_frozen_source_history(client, workflow, db):
    flow = workflow
    teacher_login(client, flow)
    draft = client.post("/api/quizzes", json={"title": "Empty"}).json()
    path = f"/api/quizzes/{draft['id']}"
    assert client.post(path + "/publish").status_code == 422
    assert (
        client.post(
            path + "/assignments", json={"student_ids": [flow["student"]["id"]]}
        ).status_code
        == 409
    )
    updated = client.put(
        path, json={**flow["payload"], "title": "Replacement", "max_attempts": None}
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["max_attempts"] is None
    assert [q["points"] for q in updated.json()["questions"]] == [2, 3, 5]
    assert client.post(path + "/publish").status_code == 200
    assert client.put(path, json=flow["payload"]).status_code == 409
    assert client.post(path + "/publish").status_code == 409
    frozen = deepcopy(client.get(path).json()["questions"])
    source_id = flow["questions"][0]["id"]
    assert (
        client.put(
            f"/api/questions/{source_id}",
            json={
                "type": "short_answer",
                "text": "Changed",
                "topic": "New",
                "correct_answer": ["new"],
            },
        ).status_code
        == 200
    )
    assert client.get(path).json()["questions"] == frozen
    assert client.delete(f"/api/questions/{source_id}").status_code == 204
    after = client.get(path).json()["questions"]
    assert after[0]["question_id"] is None
    assert after[0]["content"] == frozen[0]["content"]
    client.post("/api/auth/login", json=flow["student_credentials"])
    attempt = start(client, flow)
    result = client.post(
        f"/api/attempts/{attempt['id']}/submit",
        json={"answers": [{"quiz_question_id": attempt["questions"][0]["id"], "response": "a"}]},
    )
    assert result.status_code == 200
    assert result.json()["score"] == 2
    assert result.json()["questions"][0]["content"]["correct_answer"] == "a"


def test_deleted_draft_source_cannot_be_published(client, workflow, db):
    teacher_login(client, workflow)
    draft = client.post("/api/quizzes", json=workflow["payload"]).json()
    client.delete(f"/api/questions/{workflow['questions'][0]['id']}")
    assert client.post(f"/api/quizzes/{draft['id']}/publish").status_code == 422
    assert db.get(Quiz, draft["id"]).status == "draft"
    assert all(
        link.snapshot is None
        for link in db.scalars(select(QuizQuestion).where(QuizQuestion.quiz_id == draft["id"]))
    )


def test_assignment_is_atomic_idempotent_and_rejects_nonstudents(client, workflow, db):
    teacher_login(client, workflow)
    path = f"/api/quizzes/{workflow['quiz_id']}/assignments"
    student_id = workflow["student"]["id"]
    for _ in range(2):
        response = client.post(path, json={"student_ids": [student_id, student_id]})
        assert response.status_code == 200
        assert response.json()["student_ids"] == [student_id]
    for invalid_id in (workflow["teacher"]["id"], 99999):
        assert client.post(path, json={"student_ids": [student_id, invalid_id]}).status_code == 422
    assert db.scalar(select(func.count()).select_from(QuizAssignment)) == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"title": " "},
        {"max_attempts": 0},
        {"max_attempts": True},
        {"max_attempts": -1},
        {"due_at": "2027-01-01T12:00:00"},
        {"questions": [{"question_id": 9999}]},
        {"kind": "self_made"},
        {"status": "published"},
    ],
)
def test_invalid_quiz_input_never_creates_partial_quiz(client, workflow, db, changes):
    teacher_login(client, workflow)
    before = db.scalar(select(func.count()).select_from(Quiz))
    assert client.post("/api/quizzes", json={**workflow["payload"], **changes}).status_code == 422
    assert db.scalar(select(func.count()).select_from(Quiz)) == before


@pytest.mark.parametrize("points", [0, -1, True, 1.5])
def test_points_are_positive_integers(client, workflow, points):
    teacher_login(client, workflow)
    assert (
        client.post(
            "/api/quizzes",
            json={
                "title": "Bad",
                "questions": [{"question_id": workflow["questions"][0]["id"], "points": points}],
            },
        ).status_code
        == 422
    )


def test_duplicate_question_ids_rejected(client, workflow):
    teacher_login(client, workflow)
    item = workflow["payload"]["questions"][0]
    assert (
        client.post("/api/quizzes", json={"title": "Bad", "questions": [item, item]}).status_code
        == 422
    )


def test_other_students_and_teachers_cannot_access_quiz_or_attempt(client, workflow):
    attempt = start(client, workflow)
    for role in ("student", "teacher"):
        credentials = {"email": f"other-{role}@example.test", "password": "other-test-password"}
        client.post("/api/auth/register", json={**credentials, "name": "Other", "role": role})
        client.post("/api/auth/login", json=credentials)
        quiz_path = f"/api/quizzes/{workflow['quiz_id']}"
        assert client.get(quiz_path).status_code == 404
        assert client.post(quiz_path + "/attempts").status_code == (
            404 if role == "student" else 403
        )
        assert client.get(f"/api/attempts/{attempt['id']}").status_code == (
            404 if role == "student" else 403
        )
        assert client.post(f"/api/attempts/{attempt['id']}/submit", json={}).status_code == (
            404 if role == "student" else 403
        )
        for suffix in ("/publish", "/assignments"):
            response = client.post(
                quiz_path + suffix, json={"student_ids": [workflow["student"]["id"]]}
            )
            assert response.status_code == (403 if role == "student" else 404)
        assert client.get(quiz_path + "/results").status_code == (403 if role == "student" else 404)
        assert client.get("/api/quizzes").json()["total"] == 0
        if role == "student":
            assert client.get("/api/quizzes/assigned").json()["total"] == 0
            assert client.get("/api/students").status_code == 403
        else:
            assert client.get("/api/quizzes/assigned").status_code == 403


@pytest.mark.parametrize(
    "kind",
    ["foreign", "duplicate", "numeric_boolean", "string_boolean", "invalid_choice", "boolean_text"],
)
def test_invalid_submission_rolls_back_and_can_be_corrected(client, workflow, db, kind):
    attempt = start(client, workflow)
    qid = attempt["questions"][0]["id"]
    rows = [{"quiz_question_id": qid, "response": "a"}]
    if kind == "foreign":
        rows.append({"quiz_question_id": 999999, "response": "a"})
    elif kind == "duplicate":
        rows *= 2
    elif kind in ("numeric_boolean", "string_boolean"):
        rows.append(
            {
                "quiz_question_id": attempt["questions"][1]["id"],
                "response": 1 if kind == "numeric_boolean" else "true",
            }
        )
    elif kind == "invalid_choice":
        rows[0]["response"] = "not-a-choice"
    elif kind == "boolean_text":
        rows.append({"quiz_question_id": attempt["questions"][2]["id"], "response": True})
    path = f"/api/attempts/{attempt['id']}/submit"
    assert client.post(path, json={"answers": rows}).status_code == 422
    assert db.scalar(select(func.count()).select_from(Answer)) == 0
    assert db.get(Attempt, attempt["id"]).submitted_at is None
    assert client.post(path, json={}).status_code == 200


def test_due_date_blocks_start_resume_and_submit_at_boundary(client, workflow, monkeypatch, db):
    from app.services import attempts as service

    teacher_login(client, workflow)
    deadline = utc_now() + timedelta(hours=1)
    draft = client.post(
        "/api/quizzes", json={**workflow["payload"], "due_at": deadline.isoformat()}
    ).json()
    path = f"/api/quizzes/{draft['id']}"
    client.post(path + "/publish")
    client.post(path + "/assignments", json={"student_ids": [workflow["student"]["id"]]})
    client.post("/api/auth/login", json=workflow["student_credentials"])
    original = service.utc_now
    monkeypatch.setattr(service, "utc_now", lambda: deadline)
    assert client.post(path + "/attempts").status_code == 409
    assert db.scalar(select(func.count()).select_from(Attempt)) == 0
    monkeypatch.setattr(service, "utc_now", original)
    active = client.post(path + "/attempts").json()
    monkeypatch.setattr(service, "utc_now", lambda: deadline)
    assert client.post(path + "/attempts").status_code == 409
    assert client.post(f"/api/attempts/{active['id']}/submit", json={}).status_code == 409
    assert client.get(f"/api/attempts/{active['id']}").status_code == 200
    assert db.get(Attempt, active["id"]).score is None
