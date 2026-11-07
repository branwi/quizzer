import re
from datetime import timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import main
from app.config import Settings
from app.database import utc_now
from app.models import User
from app.schemas import RegisterRequest
from app.security import COOKIE_NAME, create_access_token, decode_access_token, signing_key
from app.services import auth


def token_for_user(db, user_id, settings):
    return create_access_token(
        user_id, settings, hashed_password=db.get(User, user_id).password_hash
    )


@pytest.mark.parametrize("role", ["student", "teacher"])
def test_register_normalizes_identity_and_hashes_password(client, db, credentials, role):
    response = client.post(
        "/api/auth/register",
        json={
            **credentials,
            "email": "  STUDENT@Example.test  ",
            "name": "  Test User  ",
            "role": role,
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert set(data) == {"id", "name", "email", "role", "created_at"}
    assert data["name"] == "Test User"
    assert data["email"] == credentials["email"]
    assert data["role"] == role
    assert data["created_at"].endswith("Z")
    user = db.get(User, data["id"])
    assert user.password_hash.startswith("$argon2id$")
    assert credentials["password"] not in response.text
    assert credentials["password"] not in user.password_hash
    assert COOKIE_NAME not in client.cookies  # Registration doesn't implicitly log in.
    assert client.get("/api/me").status_code == 401


def test_duplicate_normalized_email_returns_conflict(client, db, credentials, registered):
    response = client.post(
        "/api/auth/register",
        json={
            **credentials,
            "email": " STUDENT@EXAMPLE.TEST ",
            "name": "Other",
            "role": "teacher",
        },
    )
    assert response.status_code == 409
    assert db.scalar(select(func.count()).select_from(User)) == 1


def test_registration_unique_email_race_rolls_back(db, registered, credentials, monkeypatch):
    actual_scalar = db.scalar
    calls = 0

    def simulate_precheck_race(statement):
        nonlocal calls
        calls += 1
        return None if calls == 1 else actual_scalar(statement)

    monkeypatch.setattr(db, "scalar", simulate_precheck_race)
    with pytest.raises(auth.EmailAlreadyRegistered):
        auth.register(db, RegisterRequest(**credentials, name="Racer", role="student"))
    assert db.scalar(select(func.count()).select_from(User)) == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"name": "   "},
        {"name": "x" * 121},
        {"email": "invalid"},
        {"password": "s3cret!"},
        {"password": "x" * 129},
        {"role": "admin"},
        {"password_hash": "injected"},
    ],
)
def test_registration_validation_never_echoes_password(client, db, credentials, changes):
    payload = {**credentials, "name": "Test", "role": "student", **changes}
    response = client.post("/api/auth/register", json=payload)
    assert response.status_code == 422
    assert payload["password"] not in response.text
    assert all("input" not in error for error in response.json()["detail"])
    assert db.scalar(select(func.count()).select_from(User)) == 0


def test_login_cookie_and_current_user(client, credentials, registered, auth_settings):
    response = client.post("/api/auth/login", json=credentials)
    assert response.status_code == 200
    data = response.json()
    assert data["user"] == registered
    assert data["token_type"] == "bearer"
    assert data["expires_in"] == 3600
    assert decode_access_token(data["access_token"], auth_settings).user_id == registered["id"]
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "Max-Age=3600" in cookie
    assert "Path=/" in cookie
    assert "Secure" not in cookie
    assert response.headers["cache-control"] == "no-store"
    me = client.get("/api/me")
    assert me.status_code == 200
    assert me.json() == registered
    assert me.headers["cache-control"] == "no-store"
    assert "password" not in me.text
    assert "password_hash" not in response.text


def test_login_validation_does_not_echo_password(client, credentials):
    password = "private-password-" * 10
    response = client.post("/api/auth/login", json={**credentials, "password": password})
    assert response.status_code == 422
    assert password not in response.text
    assert all("input" not in error for error in response.json()["detail"])


def test_configured_lifetime_and_secure_cookie(client, credentials, registered, auth_settings):
    auth_settings.access_token_minutes = 15
    auth_settings.cookie_secure = True
    response = client.post("/api/auth/login", json=credentials)
    assert response.json()["expires_in"] == 900
    assert "Max-Age=900" in response.headers["set-cookie"]
    assert "Secure" in response.headers["set-cookie"]
    payload = jwt.decode(
        response.json()["access_token"], signing_key(auth_settings), algorithms=["HS256"]
    )
    assert payload["exp"] - payload["iat"] == 900


def test_secure_cookie_logout_over_https(client, credentials, registered, auth_settings):
    auth_settings.cookie_secure = True
    client.base_url = "https://testserver"
    assert client.post("/api/auth/login", json=credentials).status_code == 200
    assert client.get("/api/me").status_code == 200
    logout = client.post("/api/auth/logout")
    assert logout.status_code == 204
    assert "Secure" in logout.headers["set-cookie"]
    assert client.get("/api/me").status_code == 401


def test_login_normalizes_email_but_preserves_password_whitespace(client, credentials):
    password = " exact password "
    client.post(
        "/api/auth/register",
        json={
            **credentials,
            "password": password,
            "name": "Whitespace",
            "role": "student",
        },
    )
    response = client.post(
        "/api/auth/login",
        json={
            "email": " STUDENT@EXAMPLE.TEST ",
            "password": password,
        },
    )
    assert response.status_code == 200
    assert (
        client.post(
            "/api/auth/login",
            json={
                **credentials,
                "password": password.strip(),
            },
        ).status_code
        == 401
    )


def test_unknown_account_and_wrong_password_share_error(client, credentials, registered):
    wrong = client.post("/api/auth/login", json={**credentials, "password": "wrong-password"})
    unknown = client.post("/api/auth/login", json={**credentials, "email": "unknown@example.test"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json() == {"detail": "Invalid email or password"}
    assert wrong.headers["www-authenticate"] == "Bearer"
    assert COOKIE_NAME not in client.cookies


@pytest.mark.parametrize("method,path", [("GET", "/api/me"), ("POST", "/api/auth/logout")])
def test_private_routes_require_login(client, method, path):
    response = client.request(method, path)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("header", ["Bearer invalid-token", "Bearer", "Basic abc", "invalid"])
def test_malformed_authorization_rejected(client, header):
    assert client.get("/api/me", headers={"Authorization": header}).status_code == 401


def test_bearer_fallback_and_cookie_precedence(client, db, registered, auth_settings):
    first_token = token_for_user(db, registered["id"], auth_settings)
    second = client.post(
        "/api/auth/register",
        json={
            "email": "other@example.test",
            "password": "another-password",
            "name": "Other",
            "role": "teacher",
        },
    ).json()
    second_token = token_for_user(db, second["id"], auth_settings)
    headers = {"Authorization": f"Bearer {second_token}"}
    assert client.get("/api/me", headers=headers).json()["id"] == second["id"]
    client.cookies.set(COOKIE_NAME, first_token)
    assert client.get("/api/me", headers=headers).json()["id"] == registered["id"]
    client.cookies.set(COOKIE_NAME, "invalid-cookie")
    assert client.get("/api/me", headers=headers).status_code == 401


@pytest.mark.parametrize(
    "variation",
    [
        "expired",
        "wrong_signature",
        "wrong_algorithm",
        "missing_exp",
        "missing_sub",
        "missing_iat",
        "future_iat",
        "invalid_subject",
        "integer_subject",
        "overflow_subject",
        "missing_user",
        "null_exp",
        "object_iat",
        "missing_ver",
        "invalid_ver",
        "wrong_ver",
    ],
)
def test_invalid_tokens_return_401(client, db, registered, auth_settings, variation):
    now = utc_now()
    claims = jwt.decode(
        token_for_user(db, registered["id"], auth_settings),
        signing_key(auth_settings),
        algorithms=["HS256"],
    )
    key, algorithm = signing_key(auth_settings), "HS256"
    if variation == "expired":
        claims.update(iat=now - timedelta(hours=2), exp=now - timedelta(hours=1))
    elif variation == "wrong_signature":
        key = "different-test-secret-" + "x" * 40
    elif variation == "wrong_algorithm":
        algorithm = "HS384"
    elif variation.startswith("missing_") and variation != "missing_user":
        del claims[variation.removeprefix("missing_")]
    elif variation == "future_iat":
        claims["iat"] = now + timedelta(minutes=10)
    elif variation == "invalid_subject":
        claims["sub"] = "not-an-integer"
    elif variation == "integer_subject":
        claims["sub"] = registered["id"]
    elif variation == "overflow_subject":
        claims["sub"] = str(2**63)
    elif variation == "missing_user":
        claims["sub"] = "99999"
    elif variation == "null_exp":
        claims["exp"] = None
    elif variation == "object_iat":
        claims["iat"] = {}
    elif variation == "invalid_ver":
        claims["ver"] = []
    elif variation == "wrong_ver":
        claims["ver"] = "0" * 64
    token = jwt.encode(claims, key, algorithm=algorithm)
    response = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


def test_deleted_user_cannot_authenticate(client, db, registered, auth_settings):
    token = token_for_user(db, registered["id"], auth_settings)
    db.delete(db.get(User, registered["id"]))
    db.commit()
    assert client.get("/api/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_old_token_cannot_access_replacement_with_reused_sqlite_id(
    client, db, registered, auth_settings, credentials
):
    token = token_for_user(db, registered["id"], auth_settings)
    db.delete(db.get(User, registered["id"]))
    db.commit()
    replacement = client.post(
        "/api/auth/register",
        json={
            **credentials,
            "email": "replacement@example.test",
            "name": "Replacement",
            "role": "teacher",
        },
    ).json()
    assert replacement["id"] == registered["id"]  # Exercise SQLite's actual ID reuse.
    assert client.get("/api/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    assert (
        client.post(
            "/api/auth/login",
            json={
                **credentials,
                "email": "replacement@example.test",
            },
        ).status_code
        == 200
    )
    assert client.get("/api/me").json()["id"] == replacement["id"]


def test_logout_clears_cookie_without_revoking_copied_bearer(client, credentials, registered):
    token = client.post("/api/auth/login", json=credentials).json()["access_token"]
    response = client.post("/api/auth/logout")
    assert response.status_code == 204
    assert response.content == b""
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert COOKIE_NAME not in client.cookies
    assert client.get("/api/me").status_code == 401
    assert client.get("/api/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200


def test_openapi_exposes_bearer_authorize_and_protected_operations(client):
    schema = client.get("/openapi.json").json()
    assert schema["components"]["securitySchemes"]["HTTPBearer"] == {
        "type": "http",
        "scheme": "bearer",
    }
    for path, method in [("/api/me", "get"), ("/api/auth/logout", "post")]:
        assert schema["paths"][path][method]["security"] == [{"HTTPBearer": []}]
    for path in ("/api/auth/register", "/api/auth/login"):
        assert "security" not in schema["paths"][path]["post"]
    for path in ("/health", "/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 200


def test_every_private_api_operation_rejects_missing_invalid_and_expired_credentials(
    client, db, registered, auth_settings
):
    valid = token_for_user(db, registered["id"], auth_settings)
    claims = jwt.decode(valid, signing_key(auth_settings), algorithms=["HS256"])
    now = utc_now()
    claims.update(iat=now - timedelta(hours=2), exp=now - timedelta(hours=1))
    expired = jwt.encode(claims, signing_key(auth_settings), algorithm="HS256")
    paths = client.get("/openapi.json").json()["paths"]
    public = {"/api/auth/register", "/api/auth/login"}
    for path, operations in paths.items():
        if not path.startswith("/api/") or path in public:
            continue
        for method, operation in operations.items():
            assert operation["security"] == [{"HTTPBearer": []}]
            url = re.sub(r"\{[^}]+\}", "1", path)
            for token in (None, "invalid-token", expired):
                client.cookies.clear()
                headers = {"Authorization": f"Bearer {token}"} if token else {}
                assert client.request(method, url, headers=headers, json={}).status_code == 401
                if token:
                    client.cookies.set(COOKIE_NAME, token)
                    assert client.request(method, url, json={}).status_code == 401
    client.cookies.clear()


@pytest.mark.parametrize("secret", [None, "too-short"])
def test_application_refuses_missing_or_short_secret(monkeypatch, secret):
    settings = Settings(_env_file=None, secret_key=secret)
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    with pytest.raises(RuntimeError, match="Set SECRET_KEY"):
        with TestClient(main.app):
            pass
