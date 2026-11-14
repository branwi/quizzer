from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from backend import main
from backend.config import Settings
from backend.models import Role, User
from backend.security import signing_key


def test_login_creates_student_profile_and_reopens_it(client, db):
    first = client.post("/api/auth/login", json={"first_name": " Maya ", "grade": 6})
    assert first.status_code == 200
    user = first.json()["user"]
    assert user == {"id": user["id"], "first_name": "Maya", "grade": "6", "role": "student"}
    assert client.get("/api/me").json() == user
    assert "HttpOnly" in first.headers["set-cookie"]
    repeated = client.post("/api/auth/login", json={"first_name": "Maya", "grade": " 6 "})
    assert repeated.json()["user"] == user
    assert db.scalar(select(func.count()).select_from(User)) == 1
    other = client.post("/api/auth/login", json={"first_name": "Maya", "grade": "7"})
    assert other.json()["user"]["id"] != user["id"]


def test_teacher_and_student_use_same_login_and_keep_stored_roles(
    client, teacher, teacher_profile, db
):
    assert teacher["role"] == Role.TEACHER
    client.post("/api/auth/logout")
    teacher_login = client.post("/api/auth/login", json=teacher_profile)
    assert teacher_login.status_code == 200
    assert teacher_login.json()["user"] == teacher
    assert client.get("/api/questions").status_code == 200
    assert db.scalar(select(func.count()).select_from(User)) == 1
    student_login = client.post("/api/auth/login", json={"first_name": "Maya", "grade": 6})
    assert student_login.json()["user"]["role"] == Role.STUDENT
    assert client.get("/api/questions").status_code == 403
    # A different grade selects a new student profile, even with a teacher's name.
    other = client.post("/api/auth/login", json={**teacher_profile, "grade": "7"})
    assert other.json()["user"]["role"] == Role.STUDENT
    assert client.get("/api/students").status_code == 403


@pytest.mark.parametrize(
    "profile,expected_role",
    [
        ({"first_name": "brian", "grade": 12}, "teacher"),
        ({"first_name": " brian ", "grade": " 12 "}, "teacher"),
        ({"first_name": "brian", "grade": 11}, "student"),
        ({"first_name": "other", "grade": 12}, "student"),
        ({"first_name": "Brian", "grade": 12}, "teacher"),
        ({"first_name": "BRIAN", "grade": 12}, "teacher"),
        ({"first_name": "bRiAn", "grade": 12}, "teacher"),
    ],
)
def test_only_configured_name_and_grade_get_teacher_access(client, profile, expected_role):
    response = client.post("/api/auth/login", json=profile)
    assert response.status_code == 200
    assert response.json()["user"]["role"] == expected_role
    expected_status = 200 if expected_role == "teacher" else 403
    assert client.get("/api/questions").status_code == expected_status


@pytest.mark.parametrize(
    "first_name,other_case,grade,other_grade",
    [
        ("Brian", "BRIAN", "12", "12"),
        ("Maya", "mAyA", "6", "6"),
        ("Émile", "ÉMILE", "K", "k"),
        ("Straße", "STRASSE", "college", "COLLEGE"),
    ],
)
def test_capitalization_reuses_profile_and_preserves_display_name(
    client, db, first_name, other_case, grade, other_grade
):
    original = client.post("/api/auth/login", json={"first_name": first_name, "grade": grade})
    repeated = client.post("/api/auth/login", json={"first_name": other_case, "grade": other_grade})
    assert original.status_code == repeated.status_code == 200
    assert repeated.json()["user"] == original.json()["user"]
    assert repeated.json()["user"]["first_name"] == first_name
    assert db.scalar(select(func.count()).select_from(User)) == 1


def test_capitalization_keeps_existing_assigned_problems(client, assigned):
    expected = client.get("/api/assignments").json()
    response = client.post("/api/auth/login", json={"first_name": "MAYA", "grade": 6})
    assert response.json()["user"]["id"] == assigned["student"]["id"]
    assert client.get("/api/assignments").json() == expected


@pytest.mark.parametrize(
    "name,old_role,new_role",
    [("brian", Role.STUDENT, Role.TEACHER), ("Former", Role.TEACHER, Role.STUDENT)],
)
def test_login_applies_teacher_rule_to_existing_profiles(client, db, name, old_role, new_role):
    user = User(first_name=name, grade="12", role=old_role)
    db.add(user)
    db.commit()
    response = client.post("/api/auth/login", json={"first_name": name, "grade": 12})
    assert response.json()["user"]["id"] == user.id
    assert response.json()["user"]["role"] == new_role
    expected_status = 200 if new_role == Role.TEACHER else 403
    assert client.get("/api/students").status_code == expected_status


@pytest.mark.parametrize("grade", ["K", "college"])
def test_grade_can_be_a_label(client, grade):
    response = client.post("/api/auth/login", json={"first_name": "Sam", "grade": grade})
    assert response.status_code == 200
    assert response.json()["user"]["grade"] == grade


@pytest.mark.parametrize(
    "payload",
    [
        {"first_name": " ", "grade": 6},
        {"first_name": "Maya", "grade": " "},
        {"first_name": "Maya", "grade": True},
        {"first_name": "Maya", "grade": None},
        {"first_name": "Maya", "grade": 6, "role": "teacher"},
        {"first_name": "Maya"},
        {"email": "teacher@example.test", "password": "no-longer-used"},
    ],
)
def test_invalid_login_creates_no_profile(client, db, payload):
    response = client.post("/api/auth/login", json=payload)
    assert response.status_code == 422
    assert "no-longer-used" not in response.text
    assert db.scalar(select(func.count()).select_from(User)) == 0


def test_separate_teacher_endpoints_are_removed(client):
    for path in ("/api/auth/teacher/login", "/api/auth/teacher/register"):
        assert client.post(path, json={}).status_code == 404


def test_token_expiry_logout_and_bearer_header(client, student, auth_settings):
    token = client.post("/api/auth/login", json={"first_name": "Maya", "grade": 6}).json()[
        "access_token"
    ]
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/me").status_code == 401
    assert client.get("/api/me", headers={"Authorization": f"Bearer {token}"}).json() == student
    claims = jwt.decode(
        token, signing_key(auth_settings), algorithms=["HS256"], audience="problem-bank"
    )
    claims["exp"] = datetime.now(UTC) - timedelta(minutes=1)
    expired = jwt.encode(claims, signing_key(auth_settings), algorithm="HS256")
    for invalid in ("bad-token", expired):
        assert (
            client.get("/api/me", headers={"Authorization": f"Bearer {invalid}"}).status_code == 401
        )


def test_old_quiz_tokens_are_not_accepted(client, student, auth_settings):
    old = jwt.encode(
        {"sub": str(student["id"]), "exp": datetime.now(UTC) + timedelta(hours=1)},
        signing_key(auth_settings),
        algorithm="HS256",
    )
    client.cookies.clear()
    assert client.get("/api/me", headers={"Authorization": f"Bearer {old}"}).status_code == 401


def test_deleted_profile_token_cannot_select_reused_id(client, db, student):
    token = client.post("/api/auth/login", json={"first_name": "Maya", "grade": 6}).json()[
        "access_token"
    ]
    db.delete(db.get(User, student["id"]))
    db.commit()
    replacement = client.post("/api/auth/login", json={"first_name": "Other", "grade": 6})
    assert replacement.json()["user"]["id"] != student["id"]
    client.cookies.clear()
    assert client.get("/api/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_secret_is_required_before_startup(monkeypatch):
    monkeypatch.setattr(main, "get_settings", lambda: Settings(_env_file=None, secret_key=None))
    with pytest.raises(RuntimeError, match="Set SECRET_KEY"):
        with TestClient(main.app):
            pass
