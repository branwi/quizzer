# How the Quiz API works

The application has one JSON API, built with FastAPI. SQLAlchemy reads and writes
a SQLite file. Pydantic checks request data and defines response shapes. There is
no separate frontend, template system, migration tool, or deployment framework.
FastAPI's `/docs` page is an interactive client for that same API.

## Follow one request

For `POST /api/attempts/{attempt_id}/submit`:

1. FastAPI reads JSON into `AttemptSubmit` in `app/schemas.py`.
2. Dependencies in `app/dependencies.py` load the logged-in student and open a
   database session. The router in `app/routers/attempts.py` calls the service.
3. `app/services/attempts.py` checks ownership, deadline, submission state, and
   question IDs. It calls `grade()` for each published question.
4. The service creates answer rows, totals the points, marks the attempt submitted,
   and calls `db.commit()`. Its response contains the completed review.

Routers handle HTTP; services handle quiz rules; models describe stored data;
schemas describe incoming and outgoing JSON. Closing a session rolls back any
unfinished changes after an error. There is no custom transaction manager or
locking layer.

## Code map and reading order

| File | What to explain |
| --- | --- |
| `app/main.py` | Startup, router registration, and JSON error responses |
| `app/config.py` | Settings from `.env` and environment variables |
| `app/database.py` | Engine, sessions, `create_all()`, and UTC timestamps |
| `app/models.py` | Seven database tables and enum values |
| `app/schemas.py` | Request validation and response fields |
| `app/security.py` | Password hashing and signed login tokens |
| `app/dependencies.py` | Current user and teacher/student checks |
| `app/routers/` | URLs and calls into services |
| `app/services/auth.py` | Registration, login, and public user fields |
| `app/services/questions.py` | Question CRUD and ownership |
| `app/services/quizzes.py` | Drafts, snapshots, assignments, practice, results |
| `app/services/attempts.py` | Starting, submitting, and reviewing attempts |
| `app/services/grading.py` | Pure answer comparison functions |
| `app/services/bank.py` | Public question search |
| `app/services/analytics.py` | Counts, percentages, and score distribution |
| `app/services/access.py`, `errors.py` | Shared permission checks and service errors |

The matching files under `tests/` demonstrate each feature with small examples.

## Seven tables

| Table | Purpose |
| --- | --- |
| `users` | Name, normalized email, password hash, teacher/student role |
| `questions` | Reusable question content, answers, topic, visibility, author |
| `quizzes` | Owner, title, kind, draft/published state, deadline, attempt limit |
| `quiz_assignments` | Connects an assigned quiz to each student |
| `quiz_questions` | Ordered question links, points, and published snapshots |
| `attempts` | Student, quiz, start/submission timestamps, score and maximum |
| `answers` | Response, correctness, and points for one attempt question |

`answers.quiz_id` also records the quiz; keeping it makes existing local databases
usable. Services ensure each answer belongs to its attempt's quiz.

The database keeps primary keys, foreign keys, unique user emails, a unique answer
per attempt/question, the assignment's composite primary key, and one check that
question points are positive. Other validation lives in schemas and services.
SQLite foreign keys are enabled when a connection opens. If a source question is
deleted, its quiz links become null while published snapshots remain available.

Startup uses `Base.metadata.create_all()`. It creates missing tables and leaves
existing tables and records alone. Schema changes during development require a
new database or a deliberate manual update; there is no migration history in the
code. Older database files may retain their previous constraints.

## Authentication and permissions

Registration accepts either role. Emails are normalized and passwords are hashed
with Argon2. Login verifies the password and returns a signed JWT with an expiry.
The same token is also set in an HTTP-only, SameSite=Lax cookie. Clients can send
the cookie or an `Authorization: Bearer` header; a nonempty cookie takes priority.

Every authenticated request verifies the signature and expiry, then loads the
user. A token also contains an HMAC derived from the account's password hash; this
prevents a token for a deleted account from working if SQLite reuses its ID.
Password hashes never appear in API responses. Logout clears the cookie; there
is no server-side token revocation list.

Teachers manage their own questions and assigned quizzes. They can use their own
private questions or any public question in a quiz. Students can access assigned
published quizzes and their own practice quizzes and attempts. Teachers can view
results and analytics only for their own assigned quizzes.

Students receive response schemas that omit correct answers and explanations
until an attempt is submitted. The server always grades its stored content.

## Quiz lifecycle

1. A teacher creates a draft with question IDs, order, and point values. A draft
   can be replaced with `PUT`; it can be empty while being assembled.
2. Publishing requires available questions. The service copies each question's
   content, correct answer, and explanation into the link's JSON `snapshot`.
3. Published quizzes cannot be edited. Editing or deleting a source question does
   not change their content or previous results.
4. The teacher assigns the published quiz to registered students. Repeating an
   assignment keeps the existing assignment.

A student can search public questions and create a practice quiz. It is published
immediately with snapshots, one point per question, no deadline, and unlimited
attempts. It uses the same attempt flow as an assigned quiz.

## Attempts and grading

Starting an attempt resumes an unfinished attempt if one exists. Otherwise it
checks the deadline and attempt limit and creates a new attempt. Assigned quizzes
default to one attempt; `max_attempts: null` means unlimited.

Submitting checks the deadline again. An already submitted attempt is rejected.
Duplicate answer IDs, unrelated question IDs, and responses of the wrong type are
rejected. Omitted answers are stored as unanswered and receive zero points.

* Multiple choice: compare the submitted choice ID with the correct choice ID.
* True/false: compare JSON booleans strictly.
* Short answer: normalize case and whitespace, then compare with the
  list of accepted answers. There is no fuzzy matching or partial credit.

A correct answer earns its question's full points. The score is the sum of those
points. The submitted review includes each response, correct answer, explanation,
and awarded points. Teacher analytics aggregate submitted attempts into average,
minimum, maximum, per-question accuracy, and score buckets; unfinished attempts
are counted separately.

Timestamps use UTC. `UTCDateTime` converts timezone-aware input to UTC and restores
the timezone when SQLite returns a naive timestamp, so deadline comparisons work.

## Deliberate limits

This is a local learning application. Requests use ordinary SQLAlchemy sessions
and commits. Sequential attempt limits and repeat-submission checks remain, but
there is no coordination for simultaneous starts, submissions, or registrations.
There are no CSRF checks or custom cache-control headers. Keep these limits in
mind before exposing it to multiple users on the internet.
