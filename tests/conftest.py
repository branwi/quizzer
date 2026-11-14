import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend import main
from backend.config import Settings, get_settings
from backend.database import create_tables, get_db, make_engine


@pytest.fixture
def engine():
    engine = make_engine("sqlite:///:memory:")
    create_tables(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db(engine):
    with Session(engine, expire_on_commit=False) as session:
        yield session


@pytest.fixture
def auth_settings():
    return Settings(_env_file=None, secret_key="test-signing-secret-" + "x" * 40)


@pytest.fixture
def client(engine, auth_settings, monkeypatch):
    monkeypatch.setattr(main, "create_tables", lambda: create_tables(engine))
    monkeypatch.setattr(main, "get_settings", lambda: auth_settings)

    def override_db():
        with Session(engine, expire_on_commit=False) as session:
            yield session

    main.app.dependency_overrides[get_db] = override_db
    main.app.dependency_overrides[get_settings] = lambda: auth_settings
    try:
        with TestClient(main.app) as client:
            yield client
    finally:
        main.app.dependency_overrides.clear()


@pytest.fixture
def teacher_profile():
    return {"first_name": "brian", "grade": 12}


@pytest.fixture
def teacher(client, teacher_profile):
    response = client.post("/api/auth/login", json=teacher_profile)
    assert response.status_code == 200, response.text
    return response.json()["user"]


@pytest.fixture
def student(client):
    response = client.post("/api/auth/login", json={"first_name": "Maya", "grade": 6})
    assert response.status_code == 200, response.text
    return response.json()["user"]


@pytest.fixture
def short_answer():
    return {
        "text": "What is 2 + 2?",
        "topic": "Math",
        "correct_answer": ["four", "4"],
        "explanation": "Two plus two equals four.",
    }


@pytest.fixture
def assigned(client, teacher, student, teacher_profile, short_answer):
    client.post("/api/auth/login", json=teacher_profile)
    response = client.post("/api/questions", json=short_answer)
    assert response.status_code == 201, response.text
    question = response.json()
    response = client.post(
        "/api/assignments", json={"student_ids": [student["id"]], "question_ids": [question["id"]]}
    )
    assert response.status_code == 200, response.text
    client.post("/api/auth/login", json={"first_name": "Maya", "grade": 6})
    return {"student": student, "teacher": teacher, "question": question}
