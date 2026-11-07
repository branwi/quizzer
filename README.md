# Quiz Platform — authentication

Milestone 1 and the authentication portion of milestone 2 from
[ARCHITECTURE.md](ARCHITECTURE.md) are runnable. They include all seven database
tables, repeatable demo data, registration, login, logout, and the current-user API.
See [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) for architecture gaps,
behavior decisions, and the remaining plan.

## Run on Windows

From this folder in PowerShell, using Python 3.11+ and `uv`:

```powershell
uv venv .venv --python python
uv pip install --python .venv\Scripts\python.exe -r requirements-dev.txt
# First run: generate a signing key for this terminal (or configure an ignored .env).
$env:SECRET_KEY = & .venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"
.venv\Scripts\python.exe -m scripts.seed
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1
```

For a machine without `uv`, create the environment with `python -m venv .venv`
and install with `.venv\Scripts\python.exe -m pip install -r requirements-dev.txt`;
the remaining commands are the same. No environment activation is required.
For runtime dependencies alone, install `requirements.txt` instead.

Open [the API docs](http://127.0.0.1:8000/docs), expand `GET /health`, and click
**Try it out → Execute**. Or open [the health endpoint](http://127.0.0.1:8000/health)
directly; expect `{"status":"ok","milestone":"authentication"}`.
Stop the server with Ctrl+C.

This milestone provides JSON authentication endpoints and Swagger UI; HTML login
pages and quiz-taking arrive later. The health endpoint only verifies database
connectivity; it does not expose seeded accounts, questions, or answers.

## Try authentication

In [the API docs](http://127.0.0.1:8000/docs):

1. Execute `GET /api/me` before logging in; it returns 401.
2. Execute `POST /api/auth/login` with:

   ```json
   {"email": "teacher@example.test", "password": "quiz-demo-password"}
   ```

3. Execute `GET /api/me` again. The browser sends the HTTP-only cookie and the
   response contains your id, name, email, role, and creation time.
4. Execute `POST /api/auth/logout` (204), then `/api/me` again (401).

To create an account, use `POST /api/auth/register`:

```json
{
  "name": "New Student",
  "email": "student@example.test",
  "password": "choose-a-long-password",
  "role": "student"
}
```

Registration returns 201 and does not log in automatically. Names are trimmed;
email addresses are trimmed, validated, and case folded before storage and login.
Passwords preserve whitespace and must be 8–128 characters at registration.
Existing normalized email addresses return 409; bad login credentials return the
same generic 401 for an unknown account and an incorrect password.

For bearer authentication, copy `access_token` from a login response, click
**Authorize**, and paste the token alone. A nonempty cookie takes precedence over
the header; an invalid cookie is rejected rather than falling back to the header.
In Swagger, clear **Authorize** before testing cookie-only logout behavior.

All private API routes are mounted through the authenticated router in
`app/main.py`. `/api/me` and `/api/auth/logout` require login. Register, login,
health, docs, ReDoc, and OpenAPI remain public.

Behavior limits: users may select `teacher` when registering, as the draft
specifies. Logout clears the cookie; it does not revoke copied bearer tokens,
which remain usable until their expiry. Role/ownership enforcement belongs to
the upcoming resource routes. CSRF tokens and login rate limiting are still
deferred as described in the architecture.

## Inspect the database

The default database is `quizapp.db` in the current working directory. Run the
seed command again to see unchanged table counts. Its initial fixture contains:

| Table | Rows |
| --- | ---: |
| users | 3 |
| questions | 3 |
| quizzes | 1 |
| quiz_questions | 3 |
| quiz_assignments | 2 |
| attempts | 1 |
| answers | 3 |

The teacher is `teacher@example.test`, with students `alice@example.test` and
`bob@example.test`. Each has the local demo password `quiz-demo-password`, stored
as an Argon2 hash. These accounts work with the login endpoint.
Alice has a fixed sample result of 2/3; Bob has not attempted the assigned quiz.

To query the ORM yourself:

```powershell
.venv\Scripts\python.exe
```

```python
from sqlalchemy import select
from app.database import SessionLocal, create_tables
from app.models import User, Quiz, Attempt

create_tables()
with SessionLocal() as db:
    print([(user.name, user.role.value) for user in db.scalars(select(User))])
    print([(quiz.title, quiz.max_attempts) for quiz in db.scalars(select(Quiz))])
    print([(attempt.score, attempt.max_score) for attempt in db.scalars(select(Attempt))])
```

## Configuration

Environment variables or an optional `.env` file configure `DATABASE_URL`,
`SECRET_KEY`, `ACCESS_TOKEN_MINUTES` (default 60), and `COOKIE_SECURE` (default
false). `.env.example` shows the format. Startup fails if the signing secret is
missing or shorter than 32 bytes. Use a random value, such as the command above;
keep it in the environment or in an ignored `.env`. A persistent key preserves
sessions across server restarts; generating a new key invalidates existing tokens.
Seeding and database shell queries still work without a signing key.

JWTs use HS256 with required subject, issue time, and expiry claims. Login sets
`access_token` as an HTTP-only, SameSite=Lax cookie with path `/` and a lifetime
matching the JWT. Set `COOKIE_SECURE=true` when serving over HTTPS; local HTTP
development needs false. Successful auth responses prevent caching, and validation errors
omit raw input so invalid passwords are not echoed. The implementation follows
the [FastAPI JWT example](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/)
and [PyJWT validation documentation](https://pyjwt.readthedocs.io/en/stable/usage.html).

SQLite foreign keys are enabled on every connection, following the
[SQLAlchemy SQLite guidance](https://docs.sqlalchemy.org/en/20/dialects/sqlite.html#foreign-key-support).
Startup table creation uses FastAPI's
[lifespan mechanism](https://fastapi.tiangolo.com/advanced/events/).
`create_all` does not alter existing tables; migrations remain future work.

## Checks

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\ruff.exe check app scripts tests
.venv\Scripts\ruff.exe format --check app scripts tests
```

Tests use isolated temporary/in-memory databases and never seed the local demo
database. They exercise schema creation, every table, foreign-key enforcement,
snapshot preservation after source deletion, duplicate/cross-quiz answer rejection,
attempt-limit defaults, UTC round trips, hashed demo passwords, seed repeatability,
file persistence, environment settings, and HTTP startup/health/docs. Authentication
tests cover registration validation and duplicate-email races, cookie and bearer
login, generic failures, cookie flags, expiry, tampered/malformed tokens, deleted
users, logout behavior, response privacy, and missing-secret startup failures.

The pinned Starlette TestClient currently emits an upstream deprecation warning
about its `httpx` integration; requests and assertions still pass.

Dependency inputs are `requirements.in` and `requirements-dev.in`. To update pins:

```powershell
uv pip compile requirements.in -o requirements.txt
uv pip compile requirements-dev.in -o requirements-dev.txt
```
