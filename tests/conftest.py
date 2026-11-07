import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import main
from app.config import Settings, get_settings
from app.database import create_tables, get_db, make_engine
from scripts.seed import seed


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
def seeded(db):
    with db.begin():
        seed(db)
    return db


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
        "/api/auth/register",
        json={
            **credentials,
            "name": "Test Student",
            "role": "student",
        },
    )
    assert response.status_code == 201
    return response.json()
