from fastapi.testclient import TestClient
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app import main
from app.database import create_tables, get_db, make_engine


def test_startup_health_and_docs(tmp_path, monkeypatch, auth_settings):
    engine = make_engine(f"sqlite:///{(tmp_path / 'startup.db').as_posix()}")
    monkeypatch.setattr(main, "create_tables", lambda: create_tables(engine))
    monkeypatch.setattr(main, "get_settings", lambda: auth_settings)

    def override_db():
        with Session(engine) as db:
            yield db

    main.app.dependency_overrides[get_db] = override_db
    try:
        assert inspect(engine).get_table_names() == []
        with TestClient(main.app) as client:
            assert len(inspect(engine).get_table_names()) == 7
            response = client.get("/health")
            assert response.status_code == 200
            assert response.json() == {"status": "ok"}
            assert client.get("/docs").status_code == 200
            for removed in ("/login", "/dashboard", "/bank", "/static/app.js"):
                assert client.get(removed).status_code == 404
            assert set(client.get("/openapi.json").json()["paths"]) == {
                "/health",
                "/api/auth/register",
                "/api/auth/login",
                "/api/auth/logout",
                "/api/me",
                "/api/questions",
                "/api/questions/{question_id}",
                "/api/students",
                "/api/quizzes",
                "/api/quizzes/assigned",
                "/api/quizzes/practice",
                "/api/quizzes/{quiz_id}",
                "/api/quizzes/{quiz_id}/publish",
                "/api/quizzes/{quiz_id}/assignments",
                "/api/quizzes/{quiz_id}/results",
                "/api/quizzes/{quiz_id}/analytics",
                "/api/quizzes/{quiz_id}/attempts",
                "/api/attempts/{attempt_id}",
                "/api/attempts/{attempt_id}/submit",
                "/api/bank/questions",
            }
    finally:
        main.app.dependency_overrides.clear()
        engine.dispose()
