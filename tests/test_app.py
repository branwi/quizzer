import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app import main
from app.database import create_tables, get_db, make_engine


def test_startup_creates_only_three_tables_and_serves_docs(tmp_path, auth_settings, monkeypatch):
    engine = make_engine("sqlite:///" + (tmp_path / "startup.db").as_posix())
    monkeypatch.setattr(main, "create_tables", lambda: create_tables(engine))
    monkeypatch.setattr(main, "get_settings", lambda: auth_settings)

    def database():
        with Session(engine) as db:
            yield db

    main.app.dependency_overrides[get_db] = database
    try:
        assert inspect(engine).get_table_names() == []
        with TestClient(main.app) as client:
            assert set(inspect(engine).get_table_names()) == {
                "profiles",
                "problems",
                "assigned_problems",
            }
            assert client.get("/health").json() == {"status": "ok"}
            assert client.get("/docs").status_code == 200
            paths = client.get("/openapi.json").json()["paths"]
            assert "/api/assignments" in paths and "/api/auth/login" in paths
            assert {path for path in paths if path.startswith("/api/auth/")} == {
                "/api/auth/login",
                "/api/auth/logout",
            }
            assert not any(
                "quiz" in path or "attempt" in path or "analytics" in path for path in paths
            )
            for removed in (
                "/api/quizzes",
                "/api/quizzes/assigned",
                "/api/attempts/1",
                "/dashboard",
            ):
                assert client.get(removed).status_code == 404
    finally:
        main.app.dependency_overrides.clear()
        engine.dispose()


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/me"),
        ("GET", "/api/students"),
        ("GET", "/api/questions"),
        ("GET", "/api/bank/questions"),
        ("POST", "/api/bank/questions/1/check"),
        ("GET", "/api/assignments"),
        ("POST", "/api/assignments"),
    ],
)
def test_private_routes_require_login(client, method, path):
    assert client.request(method, path).status_code == 401
