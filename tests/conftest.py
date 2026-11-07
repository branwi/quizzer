import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import main
from app.config import Settings, get_settings
from app.database import create_tables, get_db, make_engine


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
    return Settings(
        _env_file=None,
        database_url="sqlite:///:memory:",
        secret_key="test-only-signing-secret-" + "x" * 40,
        access_token_minutes=60,
        cookie_secure=False,
    )


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
def credentials():
    return {"email": "student@example.test", "password": "a-long-test-password"}


@pytest.fixture
def registered(client, credentials):
    response = client.post(
        "/api/auth/register", json={**credentials, "name": "Test Student", "role": "student"}
    )
    assert response.status_code == 201
    return response.json()


@pytest.fixture
def teacher(client):
    credentials = {"email": "teacher@example.test", "password": "teacher-test-password"}
    response = client.post(
        "/api/auth/register", json={**credentials, "name": "Test Teacher", "role": "teacher"}
    )
    assert response.status_code == 201
    assert client.post("/api/auth/login", json=credentials).status_code == 200
    return response.json()


@pytest.fixture
def mcq():
    return {
        "type": "mcq",
        "text": "What is 2 + 2?",
        "topic": "Math",
        "choices": [{"id": "a", "text": "Four"}, {"id": "b", "text": "Five"}],
        "correct_answer": "a",
        "explanation": "Two plus two equals four.",
    }


@pytest.fixture
def workflow(client, teacher, registered, credentials, mcq):
    payloads = [
        {**mcq, "is_public": True},
        {
            "type": "true_false",
            "text": "Two is even.",
            "topic": "Math",
            "correct_answer": True,
            "explanation": "Two divides evenly by two.",
            "is_public": True,
        },
        {
            "type": "short_answer",
            "text": "What is 2 + 2?",
            "topic": "Math",
            "correct_answer": ["4", "four"],
            "explanation": "Four.",
            "is_public": False,
        },
    ]
    questions = []
    for payload in payloads:
        response = client.post("/api/questions", json=payload)
        assert response.status_code == 201, response.text
        questions.append(response.json())
    data = {
        "title": "Weighted quiz",
        "questions": [
            {"question_id": question["id"], "points": weight}
            for question, weight in zip(questions, (2, 3, 5), strict=True)
        ],
    }
    draft = client.post("/api/quizzes", json=data)
    assert draft.status_code == 201, draft.text
    quiz_id = draft.json()["id"]
    published = client.post(f"/api/quizzes/{quiz_id}/publish")
    assert published.status_code == 200, published.text
    assigned = client.post(
        f"/api/quizzes/{quiz_id}/assignments", json={"student_ids": [registered["id"]]}
    )
    assert assigned.status_code == 200, assigned.text
    assert client.post("/api/auth/login", json=credentials).status_code == 200
    return {
        "quiz": published.json(),
        "quiz_id": quiz_id,
        "questions": questions,
        "payload": data,
        "student": registered,
        "student_credentials": credentials,
        "teacher": teacher,
        "teacher_credentials": {
            "email": "teacher@example.test",
            "password": "teacher-test-password",
        },
    }
