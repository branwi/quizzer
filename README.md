# Quiz Platform — foundations

Milestone 1 from [ARCHITECTURE.md](ARCHITECTURE.md) is runnable. It includes all
seven database tables, a repeatable demo fixture, and a small FastAPI application.
See [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) for architecture gaps,
behavior decisions, and the remaining plan.

## Run on Windows

From this folder in PowerShell, using Python 3.11+ and `uv`:

```powershell
uv venv .venv --python python
uv pip install --python .venv\Scripts\python.exe -r requirements-dev.txt
.venv\Scripts\python.exe -m scripts.seed
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1
```

For a machine without `uv`, create the environment with `python -m venv .venv`
and install with `.venv\Scripts\python.exe -m pip install -r requirements-dev.txt`;
the remaining commands are the same. No environment activation is required.
For runtime dependencies alone, install `requirements.txt` instead.

Open [the API docs](http://127.0.0.1:8000/docs), expand `GET /health`, and click
**Try it out → Execute**. Or open [the health endpoint](http://127.0.0.1:8000/health)
directly; expect `{"status":"ok","milestone":"foundations"}`.
Stop the server with Ctrl+C.

This milestone has no login or quiz UI yet. The health endpoint only verifies
database connectivity; it does not expose seeded accounts, questions, or answers.

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
as an Argon2 hash. These accounts become usable through login in milestone 2.
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
`SECRET_KEY`, and `ACCESS_TOKEN_MINUTES` (default 60). `.env.example` shows the
format. No signing secret is needed or generated in this milestone because
tokens are not issued yet. The login milestone must require a configured secret.

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
file persistence, environment settings, and HTTP startup/health/docs.

The pinned Starlette TestClient currently emits an upstream deprecation warning
about its `httpx` integration; requests and assertions still pass.

Dependency inputs are `requirements.in` and `requirements-dev.in`. To update pins:

```powershell
uv pip compile requirements.in -o requirements.txt
uv pip compile requirements-dev.in -o requirements-dev.txt
```
