from datetime import timedelta

import jwt
import pytest
from fastapi.testclient import TestClient

from app import main
from app.config import Settings
from app.database import utc_now
from app.models import User
from app.security import signing_key, verify_password


@pytest.mark.parametrize("role", ["teacher", "student"])
def test_register_normalizes_email_and_hashes_password(client, db, credentials, role):
    response = client.post(
        "/api/auth/register",
        json={
            **credentials,
            "name": " Test User ",
            "email": " STUDENT@EXAMPLE.TEST ",
            "role": role,
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test User"
    assert data["email"] == "student@example.test"
    assert "password_hash" not in data
    assert "password" not in data
    assert verify_password(credentials["password"], db.get(User, data["id"]).password_hash)


def test_duplicate_registration_and_validation(client, credentials, registered):
    payload = {**credentials, "name": "Other", "role": "student"}
    assert client.post("/api/auth/register", json=payload).status_code == 409
    response = client.post("/api/auth/register", json={**payload, "password": "s3cret!"})
    assert response.status_code == 422
    assert "s3cret!" not in response.text


def test_login_works_with_cookie_and_bearer_header(client, credentials, registered):
    login = client.post("/api/auth/login", json=credentials)
    assert login.status_code == 200
    assert "HttpOnly" in login.headers["set-cookie"]
    assert client.get("/api/me").json() == registered
    assert "cache-control" not in login.headers
    token = login.json()["access_token"]
    client.cookies.clear()
    assert client.get("/api/me", headers={"Authorization": f"Bearer {token}"}).json() == registered


def test_login_errors_are_generic(client, credentials, registered):
    wrong = client.post("/api/auth/login", json={**credentials, "password": "wrong-password"})
    unknown = client.post("/api/auth/login", json={**credentials, "email": "unknown@example.test"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json() == {"detail": "Invalid email or password"}


def test_missing_invalid_and_expired_tokens_return_401(
    client, credentials, registered, auth_settings
):
    assert client.get("/api/me").status_code == 401
    assert client.get("/api/me", headers={"Authorization": "Bearer invalid"}).status_code == 401
    token = client.post("/api/auth/login", json=credentials).json()["access_token"]
    claims = jwt.decode(token, signing_key(auth_settings), algorithms=["HS256"])
    claims.update(iat=utc_now() - timedelta(hours=2), exp=utc_now() - timedelta(hours=1))
    expired = jwt.encode(claims, signing_key(auth_settings), algorithm="HS256")
    client.cookies.clear()
    assert client.get("/api/me", headers={"Authorization": f"Bearer {expired}"}).status_code == 401


def test_logout_clears_cookie(client, credentials, registered):
    client.post("/api/auth/login", json=credentials)
    response = client.post("/api/auth/logout")
    assert response.status_code == 204
    assert response.content == b""
    assert client.get("/api/me").status_code == 401


def test_deleted_account_token_cannot_log_in_as_replacement(client, db, credentials, registered):
    token = client.post("/api/auth/login", json=credentials).json()["access_token"]
    client.cookies.clear()
    db.delete(db.get(User, registered["id"]))
    db.commit()
    client.post(
        "/api/auth/register", json={**credentials, "name": "Replacement", "role": "teacher"}
    )
    assert client.get("/api/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_missing_secret_prevents_startup(monkeypatch):
    monkeypatch.setattr(main, "get_settings", lambda: Settings(_env_file=None, secret_key=None))
    with pytest.raises(RuntimeError, match="Set SECRET_KEY"):
        with TestClient(main.app):
            pass
