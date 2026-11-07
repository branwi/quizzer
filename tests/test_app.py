from fastapi.testclient import TestClient
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app import main
from app.database import create_tables, get_db, make_engine


def test_startup_health_and_docs(tmp_path, monkeypatch):
    engine = make_engine(f"sqlite:///{(tmp_path / 'startup.db').as_posix()}")
    monkeypatch.setattr(main, "create_tables", lambda: create_tables(engine))

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
            assert response.json() == {"status": "ok", "milestone": "foundations"}
            assert client.get("/docs").status_code == 200
            assert set(client.get("/openapi.json").json()["paths"]) == {"/health"}
    finally:
        main.app.dependency_overrides.clear()
        engine.dispose()
