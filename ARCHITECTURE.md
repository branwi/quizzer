# Quiz Platform: Technical Design Document

_Status: Draft v1 · November 7, 2026 · Stack: FastAPI, SQLAlchemy 2.0, SQLite, Jinja2 + HTMX_

## 1. Overview

A web application where teachers write questions and assign quizzes to their students, and students take quizzes, see graded results, and browse a shared question bank to build their own practice quizzes.

The design goal is a codebase small enough for one person to understand end to end, while still showing real engineering: a relational data model, user accounts with login, a testable grading engine, and clear layering.

### Goals

- Teachers create questions, build quizzes, assign them to individual students, and view results.
- Students take assigned quizzes and receive automatic grading with a review screen.
- A public question bank that any logged-in user can search, filter, and select from to create practice quizzes.
- Login-based access: users register and log in, and their teacher or student role decides which features they see. Students never see answer keys before submitting.
- Automated tests for the grading logic and the login flow.

### Non-goals (v1)

- Timed quizzes, proctoring, or anti-cheating measures.
- Student-authored questions, essay questions, or manual grading.
- Real-time features, notifications, or email.
- School-level administration or single sign-on.
- Horizontal scaling.

## 2. Users and Use Cases

| Role    | Capabilities                                                                                                                                                                                                                                                     |
| ------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Teacher | Register and log in. Create, edit, and delete their own questions. Mark questions public to share them in the bank. Build a quiz from their own and public questions, publish it, and assign it to individual students. View results and per-question analytics. |
| Student | Register and log in. See and take assigned quizzes, then review the graded attempt. Browse, search, and filter the question bank, select questions, and create a practice quiz from them.                                                                        |

### Key flows

1. **Assignment:** teacher creates questions, creates a quiz, adds questions, publishes it, and assigns it to chosen students, who then see it.
2. **Taking a quiz:** student starts an attempt, answers, submits, is graded automatically, and reviews results.
3. **Practice:** student browses the bank, selects questions, creates a practice quiz, and takes it exactly like flow 2.

Flow 3 reuses flow 2 entirely. This is intentional and is explained in the data model section.

## 3. Architecture

The system is a layered monolith: one deployable application, one database file.

```
Browser (Jinja2 pages + HTMX, or Swagger UI at /docs)
        │ HTTP
        ▼
Routers      parse requests, resolve dependencies (db, user), return responses
        │
Services     business rules: grading, quiz building, attempt lifecycle, search
        │
ORM models   SQLAlchemy 2.0 sessions and models
        │
SQLite       single file database
```

### Layering rules

- Routers contain no business logic. They validate input, call a service, and shape the output.
- Services take plain arguments (a database session plus data), never request objects, so they can be tested without HTTP.
- Grading is pure functions with no database access.
- Pydantic schemas define every request and response. ORM objects never leave the service layer unfiltered.

### Request lifecycle

1. FastAPI validates the request body against a Pydantic schema.
2. Dependencies resolve the database session and the current user.
3. The router calls a service function.
4. The service reads and writes through the ORM.
5. The router returns the result, and `response_model` filters it down to the allowed fields.

## 4. Technology Choices

| Concern          | Choice                  | Rationale                                                                            | Alternative considered                                |
| ---------------- | ----------------------- | ------------------------------------------------------------------------------------ | ----------------------------------------------------- |
| Web framework    | FastAPI + Uvicorn       | Type hints, Pydantic validation, dependency injection, automatic API docs            | Flask (less structure), Django (more hidden behavior) |
| ORM              | SQLAlchemy 2.0          | Explicit, widely used, keeps ORM models separate from API schemas                    | SQLModel (merges the two, less explicit)              |
| Database         | SQLite                  | Zero setup, single file, enough for a demo                                           | PostgreSQL (swap through `DATABASE_URL`)              |
| Endpoints        | Sync `def`              | FastAPI runs them in a threadpool, and the code stays simple                         | `async def` with async drivers                        |
| Frontend         | Jinja2 + HTMX           | One codebase, no JavaScript build step, live search with little code                 | React single-page app                                 |
| Auth             | JWT in HTTP-only cookie | Stateless, works with server-rendered pages, bearer header also accepted for Swagger | Server-side sessions                                  |
| Password hashing | Argon2 (pwdlib)         | Current best practice                                                                | bcrypt                                                |
| Testing          | pytest + TestClient     | Fast, supports dependency overrides                                                  | None                                                  |
| Migrations       | Alembic (optional)      | Schema changes without data loss                                                     | `create_all` at startup                               |

## 5. Data Model

### Relationships

```
users 1 ── * questions        (author)
users 1 ── * quizzes          (owner)
quizzes * ── * users          (assigned students, through quiz_assignments)
quizzes * ── * questions      (through quiz_questions)
quizzes 1 ── * attempts * ── 1 users (student)
attempts 1 ── * answers
```

### users

| Column        | Type        | Notes                                  |
| ------------- | ----------- | -------------------------------------- |
| id            | integer, PK |                                        |
| name          | string      |                                        |
| email         | string      | Unique, indexed                        |
| password_hash | string      | Argon2 hash, never returned by the API |
| role          | enum        | teacher or student                     |
| created_at    | datetime    |                                        |

### questions

| Column                 | Type           | Notes                                         |
| ---------------------- | -------------- | --------------------------------------------- |
| id                     | integer, PK    |                                               |
| author_id              | FK to users    |                                               |
| type                   | enum           | mcq, true_false, short_answer                 |
| text                   | text           | The prompt                                    |
| choices                | JSON, nullable | MCQ only: list of objects with an id and text |
| correct_answer         | JSON           | Format depends on type (see below)            |
| explanation            | text, nullable | Shown in review after submission              |
| topic                  | string         | Indexed                                       |
| is_public              | boolean        | Default false. True means visible in the bank |
| created_at, updated_at | datetime       |                                               |

**Content formats by type:**

- `mcq`: choices is a list such as `[{'id': 'a', 'text': 'Paris'}, ...]` with 2 to 6 entries, and correct_answer is the id, for example `'a'`.
- `true_false`: no choices, and correct_answer is a boolean.
- `short_answer`: no choices, and correct_answer is a list of accepted strings.

### quiz_assignments

| Column      | Type          | Notes                                                                                          |
| ----------- | ------------- | ---------------------------------------------------------------------------------------------- |
| quiz_id     | FK to quizzes | Part of the composite primary key                                                              |
| student_id  | FK to users   | Part of the composite primary key. A row makes the quiz appear in that student's assigned list |
| assigned_at | datetime      |                                                                                                |

### quizzes

| Column       | Type               | Notes                                                            |
| ------------ | ------------------ | ---------------------------------------------------------------- |
| id           | integer, PK        |                                                                  |
| owner_id     | FK to users        | Teacher for assigned quizzes, student for self-made ones         |
| title        | string             |                                                                  |
| kind         | enum               | assigned or self_made                                            |
| due_at       | datetime, nullable |                                                                  |
| max_attempts | integer, nullable  | Null means unlimited. Default 1 for assigned, null for self-made |
| status       | enum               | draft or published                                               |
| created_at   | datetime           |                                                                  |

### quiz_questions

| Column      | Type                      | Notes                                                                                                 |
| ----------- | ------------------------- | ----------------------------------------------------------------------------------------------------- |
| id          | integer, PK               |                                                                                                       |
| quiz_id     | FK to quizzes             |                                                                                                       |
| question_id | FK to questions, nullable | Set to null if the source question is deleted                                                         |
| position    | integer                   | Display order                                                                                         |
| points      | integer                   | Default 1                                                                                             |
| snapshot    | JSON                      | Frozen copy of type, text, choices, correct_answer, and explanation, taken when the quiz is published |

### attempts and answers

| Table    | Columns                                                                                                                                          |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| attempts | id (PK), quiz_id (FK), student_id (FK), started_at, submitted_at (nullable), score (nullable), max_score                                         |
| answers  | id (PK), attempt_id (FK), quiz_question_id (FK), response (JSON), is_correct (boolean), points_awarded. Unique on (attempt_id, quiz_question_id) |

Answers are written only when an attempt is submitted, so every answer row belongs to a submitted attempt.

### Indexes

- `questions(is_public, topic)` for bank filtering
- `questions(author_id)` for a teacher's own list
- `quiz_assignments(student_id)` for a student's assigned quizzes
- `attempts(student_id)` and `attempts(quiz_id, student_id)` for history and attempt counting

### Key design decisions

1. **One quiz model for two features.** Assigned quizzes and student practice quizzes are both rows in `quizzes`, distinguished by `kind`. The attempt, grading, and review code is written once.
2. **Snapshots at publish time.** Grading and review use `quiz_questions.snapshot`, not the live question. A teacher can edit or delete a question later without changing past grades.
3. **The bank is a filter, not a table.** It is a query over `questions` where `is_public` is true.
4. **Foreign keys are enforced explicitly.** SQLite ignores foreign keys unless `PRAGMA foreign_keys=ON` is set on every connection, so `database.py` sets it through a connection event listener.

## 6. API Design

All JSON routes live under `/api`. The static route `/api/quizzes/assigned` must be declared before `/api/quizzes/{id}` so it is not captured as an id.

| Method           | Path                          | Used by | Purpose                                                              |
| ---------------- | ----------------------------- | ------- | -------------------------------------------------------------------- |
| POST             | /api/auth/register            | public  | Create an account (name, email, password, role)                      |
| POST             | /api/auth/login               | public  | Verify credentials and set the cookie                                |
| POST             | /api/auth/logout              | any     | Clear the cookie                                                     |
| GET              | /api/me                       | any     | Current user                                                         |
| GET              | /api/students                 | teacher | List students, for the assignment picker                             |
| POST             | /api/questions                | teacher | Create a question                                                    |
| GET              | /api/questions                | teacher | List own questions, with filters and pagination                      |
| GET, PUT, DELETE | /api/questions/{id}           | teacher | Read, update, or delete an own question                              |
| GET              | /api/bank/questions           | any     | Search public questions (q, topic, page, page_size)                  |
| POST             | /api/quizzes                  | teacher | Create a draft quiz with question ids and points                     |
| PUT              | /api/quizzes/{id}             | teacher | Edit a draft quiz                                                    |
| POST             | /api/quizzes/{id}/publish     | teacher | Snapshot the questions and freeze the quiz                           |
| POST             | /api/quizzes/{id}/assignments | teacher | Assign a published quiz to individual students (list of student ids) |
| GET              | /api/quizzes/{id}/results     | teacher | Attempts and scores                                                  |
| GET              | /api/quizzes/{id}/analytics   | teacher | Per-question accuracy and score distribution                         |
| GET              | /api/quizzes/assigned         | student | Published quizzes assigned to the logged-in student                  |
| POST             | /api/quizzes/practice         | student | Create a self-made quiz from bank question ids                       |
| POST             | /api/quizzes/{id}/attempts    | student | Start an attempt                                                     |
| GET              | /api/attempts/{id}            | student | In progress: questions without answers. Submitted: graded review     |
| POST             | /api/attempts/{id}/submit     | student | Submit answers, grade, and return the result                         |

### Schemas that matter

- `QuestionCreate` is a discriminated union on `type`. MCQ requires 2 to 6 choices with unique ids and a correct_answer matching one of them. True/false requires a boolean. Short answer requires at least one accepted string.
- `QuestionForTeacher` includes `correct_answer` and `explanation`.
- `QuestionForStudent` omits both. Routes that return questions to students set `response_model=QuestionForStudent`, so FastAPI strips the answer key even if the underlying object contains it.
- The bank endpoint picks the schema by role: teachers get the full version, students get the safe one.

## 7. Authentication

### Authentication

- Passwords are hashed with Argon2 and never stored or logged in plain text.
- Login issues a JWT with the user id as subject and a 60 minute expiry. It is set as an HTTP-only, SameSite=Lax cookie.
- `get_current_user` reads the cookie first and falls back to the `Authorization: Bearer` header, so the Swagger UI Authorize button works.
- Secrets and settings come from environment variables through a settings class.

Every route except register and login requires a logged-in user, so an anonymous request gets 401. A user's role decides which pages and features the UI shows, and the Used by column in the API table says which role each route is built for. The server does not check roles in v1.

### Dependencies (sketch)

```python
def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get('access_token') or read_bearer_header(request)
    user_id = decode_token(token)  # raises 401 if missing, invalid, or expired
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401)
    return user

@router.post('/questions')
def create_question(
    data: QuestionCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return questions_service.create(db, user, data)
```

Login is enforced by one dependency in the route signature, and tests can override it.

## 8. Core Logic

### Grading engine

Grading is a registry of pure functions keyed by question type. Adding a new question type means adding one function and one schema.

```python
def normalize(text: str) -> str:
    return ' '.join(text.split()).casefold()

def grade_short_answer(snapshot: dict, response: str) -> bool:
    accepted = {normalize(a) for a in snapshot['correct_answer']}
    return normalize(response) in accepted

GRADERS = {
    'mcq': lambda snap, resp: resp == snap['correct_answer'],
    'true_false': lambda snap, resp: resp == snap['correct_answer'],
    'short_answer': grade_short_answer,
}

def grade(snapshot: dict, response) -> bool:
    return GRADERS[snapshot['type']](snapshot, response)
```

Points are all or nothing per question in v1.

### Quiz publishing

1. Verify the quiz is a draft with at least one question.
2. For each linked question, copy its current content into `quiz_questions.snapshot`.
3. Set `status` to published. After this, the quiz content is immutable.

Self-made practice quizzes are created and published in one step, with `kind` set to self_made and unlimited attempts.

### Assigning a quiz

After publishing, the teacher picks individual students from the student list and posts their ids to the assignments endpoint. The service creates one `quiz_assignments` row for each student who does not already have one, so a quiz can also be assigned to more students later.

### Attempt lifecycle

**Start:** verify the quiz is published, the due date has not passed, and the attempt count is below `max_attempts`. Create an attempt row with `submitted_at` null and return the questions through the student schema.

**Submit:** inside one transaction, verify the attempt has not been submitted. Grade each answer against its snapshot, write the answer rows, and set `score`, `max_score`, and `submitted_at`. A second submit returns 409.

**Review:** available only after submission. It returns the snapshot's correct answers and explanations alongside the student's responses.

### Question bank search

- Filters: free text on question text and topic. Only rows with `is_public` true are searched.
- Offset pagination with `page` and `page_size`, capped at 50.
- Text search uses `LIKE` in v1. SQLite's FTS5 is the planned upgrade.
- Students select questions in the UI and post the ids to the practice endpoint, which validates that every id is public.

### Analytics

Per-question accuracy is one aggregate query:

```sql
SELECT qq.id, qq.position,
       COUNT(a.id)    AS responses,
       AVG(a.is_correct) AS accuracy
FROM quiz_questions qq
LEFT JOIN answers a ON a.quiz_question_id = qq.id
WHERE qq.quiz_id = :quiz_id
GROUP BY qq.id, qq.position
ORDER BY accuracy ASC;
```

The score distribution is a second query that buckets `attempts.score / attempts.max_score` for submitted attempts.

## 9. Frontend

Pages are server-rendered with Jinja2 using a base layout and partial templates. HTMX handles the interactive parts without a JavaScript framework. The `web/` routers call the same service functions as the JSON API, so no business logic is duplicated.

| Page               | Behavior                                                                                                                   |
| ------------------ | -------------------------------------------------------------------------------------------------------------------------- |
| Login and register | Standard forms, sets the cookie                                                                                            |
| Teacher dashboard  | Own questions, quizzes, and results                                                                                        |
| Question editor    | Form that adapts to question type                                                                                          |
| Quiz builder       | Pick questions from own list and the bank, set points, publish, then pick the students to assign it to                     |
| Question bank      | Live search and filters through `hx-get` with a keyup delay, checkboxes to select questions, a Create practice quiz button |
| Take quiz          | One form, submit posts all answers                                                                                         |
| Attempt review     | Graded results with correct answers and explanations                                                                       |

The Swagger UI at `/docs` is kept enabled and doubles as a live API demo.

## 10. Project Structure

```
quizapp/
├── app/
│   ├── main.py             # app creation, router registration
│   ├── config.py           # settings from environment variables
│   ├── database.py         # engine, SessionLocal, get_db, SQLite FK pragma
│   ├── models.py           # SQLAlchemy ORM models
│   ├── schemas.py          # Pydantic request and response models
│   ├── security.py         # password hashing, JWT encode and decode
│   ├── dependencies.py     # get_current_user, require_role
│   ├── routers/            # JSON API: auth, users, questions, bank, quizzes, attempts
│   ├── web/                # HTML views (Jinja2 + HTMX) calling the same services
│   ├── services/
│   │   ├── grading.py      # pure functions, no DB, no FastAPI
│   │   ├── quizzes.py      # build, publish, snapshot
│   │   ├── attempts.py     # start, submit, review
│   │   └── bank.py         # search, filter, paginate
│   └── templates/          # base layout and partials
├── tests/
│   ├── conftest.py         # in-memory DB, TestClient, user fixtures
│   ├── test_grading.py
│   ├── test_services.py
│   └── test_auth.py
├── scripts/seed.py         # demo teacher, students, and sample questions
├── alembic/                # optional migrations
├── Dockerfile
├── requirements.txt
└── README.md
```

### Configuration and running

- Settings: `SECRET_KEY`, `DATABASE_URL`, and `ACCESS_TOKEN_MINUTES`, read from the environment.
- Local: `uvicorn app.main:app --reload`.
- The Dockerfile runs the same command, so the demo works on any machine.

## 11. Testing Strategy

| Level         | What is tested                                                                                                                        |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| Unit: grading | Every question type with correct, incorrect, empty, and whitespace or case variants                                                   |
| Service       | Publishing freezes snapshots. Attempts respect max_attempts and due dates. Double submit is rejected                                  |
| API           | `TestClient` against in-memory SQLite, with `get_db` overridden per test                                                              |
| Login         | Registration and login work, passwords are stored hashed, and every route except register and login returns 401 without a valid token |
| Contract      | Student-facing responses never contain `correct_answer` or `explanation` before submission                                            |

The goal is not a coverage number. The goal is that the two riskiest areas, grading correctness and login, are fully pinned down.

## 12. Security

| Area      | v1 decision                                                               |
| --------- | ------------------------------------------------------------------------- |
| Passwords | Argon2 hashes, and generic login error messages                           |
| Sessions  | JWT with a 60 minute expiry in an HTTP-only, SameSite=Lax cookie          |
| Access    | Login required on every route except register and login                   |
| Secrets   | Environment variables, never committed                                    |
| Not in v1 | Server-side role checks, ownership checks, CSRF tokens, and rate limiting |

Login is the only security control in v1. The role stored on each user decides which pages and features the UI shows, but the server does not enforce it, so a logged-in student could call teacher endpoints directly. That is acceptable for a local demo, and the hardening steps are listed under future work.

## 13. Milestones

| #   | Milestone              | Done when                                                                                                                |
| --- | ---------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| 1   | Foundations            | Models, `database.py`, and the seed script exist, and every table can be created and queried from a Python shell         |
| 2   | Login                  | Register and login work, and every route except register and login returns 401 without a valid cookie                    |
| 3   | Question CRUD          | Teachers can create every question type, and malformed questions are rejected by validation                              |
| 4   | Grading engine         | `grade()` is covered by unit tests for every type and edge case                                                          |
| 5   | Quizzes and assignment | A teacher can build, publish, and assign a quiz to individual students, and editing a source question does not change it |
| 6   | Attempt flow           | Start, submit, and review work, with max_attempts, due dates, and double-submit protection                               |
| 7   | Question bank          | Search, filters, pagination, and practice quiz creation work                                                             |
| 8   | Web UI                 | Jinja2 and HTMX pages cover every flow                                                                                   |
| 9   | Analytics and polish   | Analytics endpoint, Docker, and a README with the architecture diagram are done                                          |

## 14. Tradeoffs and Future Work

### Tradeoffs

| Decision                                  | Alternative              | Reasoning                                                                         |
| ----------------------------------------- | ------------------------ | --------------------------------------------------------------------------------- |
| Snapshot questions at publish             | Reference live questions | Protects grade integrity, at the cost of duplicated data                          |
| One quiz model for assigned and self-made | Separate tables          | One grading and attempt path, with a few kind-specific rules in the service layer |
| JSON columns for choices and answers      | Normalized choices table | Flexible per question type, but contents are not queryable in a portable way      |
| Sync endpoints                            | async                    | Simpler code, and SQLite gains little from async                                  |
| Server-rendered UI                        | Single-page app          | One codebase and far less to explain                                              |
| Offset pagination                         | Keyset pagination        | Simple, and fine at this data size                                                |
| SQLite                                    | PostgreSQL               | No setup now, and only the connection string changes later                        |

### Future work

- Classes or groups, so a teacher can assign a quiz to many students at once.
- Server-side role and ownership checks, CSRF protection, and login rate limiting.
- Tags as a many-to-many relationship instead of a single topic column.
- Timed quizzes and per-question time limits.
- Multi-select questions and partial credit.
- CSV import and export of questions.
- Student-submitted questions with teacher moderation.
- PostgreSQL and Alembic-managed migrations for a real deployment.
- SQLite FTS5 for ranked question search.

## 15. Open Questions

1. Can teachers include other teachers' public questions in their quizzes? This document assumes yes.
2. Should students see correct answers immediately after submitting, or only after the due date? This document assumes immediately.
3. Can a teacher unpublish a quiz that already has attempts? This document assumes no.
4. Can students retake assigned quizzes? This document assumes one attempt by default, configurable per quiz through `max_attempts`.
5. Does the assignment picker list every registered student? This document assumes yes.
