import pytest
from sqlalchemy import func, select

from backend.models import AssignedProblem


def test_multiple_bank_questions_can_be_assigned_to_multiple_students(
    client, teacher, teacher_profile, short_answer
):
    students = [
        client.post("/api/auth/login", json={"first_name": name, "grade": 6}).json()["user"]
        for name in ("Maya", "Sam")
    ]
    client.post("/api/auth/login", json=teacher_profile)
    questions = [
        client.post("/api/questions", json={**short_answer, "text": text}).json()
        for text in ("First", "Second")
    ]
    payload = {
        "student_ids": [s["id"] for s in students],
        "question_ids": [q["id"] for q in questions],
    }
    assert client.post("/api/assignments", json=payload).status_code == 200
    for student in students:
        listed = client.get(f"/api/assignments/{student['id']}").json()
        assert [item["id"] for item in listed] == payload["question_ids"]


def test_flat_assignments_survive_login_and_are_specific_to_student(client, assigned):
    expected = client.get("/api/assignments").json()
    assert len(expected) == 1 and expected[0]["id"] == assigned["question"]["id"]
    assert "quiz_id" not in expected[0] and "points" not in expected[0]
    client.post("/api/auth/login", json={"first_name": "Other", "grade": 6})
    assert client.get("/api/assignments").json() == []
    client.post("/api/auth/login", json={"first_name": "Maya", "grade": 6})
    assert client.get("/api/assignments").json() == expected


def test_assignment_is_idempotent_and_can_be_removed(client, assigned, teacher_profile, db):
    student_id, question_id = assigned["student"]["id"], assigned["question"]["id"]
    client.post("/api/auth/login", json=teacher_profile)
    payload = {"student_ids": [student_id, student_id], "question_ids": [question_id, question_id]}
    for _ in range(2):
        assert client.post("/api/assignments", json=payload).json() == {
            "student_ids": [student_id],
            "question_ids": [question_id],
        }
    assert db.scalar(select(func.count()).select_from(AssignedProblem)) == 1
    assert len(client.get(f"/api/assignments/{student_id}").json()) == 1
    for _ in range(2):
        assert client.delete(f"/api/assignments/{student_id}/{question_id}").status_code == 204
    assert client.get(f"/api/assignments/{student_id}").json() == []


def test_assignment_validates_whole_selection_before_writing(
    client, teacher, student, teacher_profile, short_answer, db
):
    client.post("/api/auth/login", json=teacher_profile)
    question = client.post("/api/questions", json=short_answer).json()
    for students, questions in [
        ([student["id"], 99999], [question["id"]]),
        ([student["id"]], [question["id"], 99999]),
        ([teacher["id"]], [question["id"]]),
        ([], [question["id"]]),
    ]:
        response = client.post(
            "/api/assignments", json={"student_ids": students, "question_ids": questions}
        )
        assert response.status_code == 422
        assert db.scalar(select(func.count()).select_from(AssignedProblem)) == 0


def test_edits_are_live_and_deleting_question_cleans_assignment(
    client, assigned, teacher_profile, short_answer, db
):
    student_id, question_id = assigned["student"]["id"], assigned["question"]["id"]
    client.post("/api/auth/login", json=teacher_profile)
    client.put(f"/api/questions/{question_id}", json={**short_answer, "text": "New wording"})
    assert client.get(f"/api/assignments/{student_id}").json()[0]["text"] == "New wording"
    assert client.delete(f"/api/questions/{question_id}").status_code == 204
    assert client.get(f"/api/assignments/{student_id}").json() == []
    assert db.scalar(select(func.count()).select_from(AssignedProblem)) == 0


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", "/api/assignments"),
        ("GET", "/api/assignments/999"),
        ("DELETE", "/api/assignments/1/1"),
        ("GET", "/api/students"),
    ],
)
def test_students_cannot_manage_assignments_or_list_profiles(client, student, method, path):
    assert client.request(method, path).status_code == 403


def test_teacher_can_list_students_but_not_select_student_views(client, assigned, teacher_profile):
    client.post("/api/auth/login", json=teacher_profile)
    assert client.get("/api/students").json() == [assigned["student"]]
    assert client.get("/api/assignments").status_code == 403
    assert client.get("/api/assignments/99999").status_code == 404


def test_teacher_can_replace_and_clear_current_problems(
    client, assigned, teacher_profile, short_answer
):
    client.post("/api/auth/login", json=teacher_profile)
    second = client.post("/api/questions", json={**short_answer, "text": "Another problem"}).json()
    path = f"/api/assignments/{assigned['student']['id']}"
    replaced = client.put(path, json={"question_ids": [second["id"], second["id"]]})
    assert replaced.status_code == 200
    assert [question["id"] for question in replaced.json()] == [second["id"]]
    assert "correct_answer" not in replaced.text
    assert client.get(path).json() == replaced.json()
    assert client.put(path, json={"question_ids": []}).json() == []
    client.post("/api/auth/login", json={"first_name": "Maya", "grade": 6})
    assert client.get("/api/assignments").json() == []


def test_invalid_replacement_preserves_current_problems(client, assigned, teacher_profile):
    client.post("/api/auth/login", json=teacher_profile)
    path = f"/api/assignments/{assigned['student']['id']}"
    before = client.get(path).json()
    assert client.put(path, json={"question_ids": [999999]}).status_code == 422
    assert client.get(path).json() == before
    assert client.put("/api/assignments/999999", json={"question_ids": []}).status_code == 404
    assert (
        client.put(
            f"/api/assignments/{assigned['teacher']['id']}", json={"question_ids": []}
        ).status_code
        == 404
    )


def test_student_cannot_replace_their_own_or_other_students_assignments(client, assigned):
    for student_id in (assigned["student"]["id"], 999999):
        assert (
            client.put(f"/api/assignments/{student_id}", json={"question_ids": []}).status_code
            == 403
        )
