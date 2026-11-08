# How the problem bank works

The application is a FastAPI JSON API backed by SQLite. Pydantic validates JSON;
SQLAlchemy stores records. `/docs` lets you call the API without a separate frontend.

The flow is **request → router → service → database → response**.

## Three tables

| Model/table | Stored information |
| --- | --- |
| `User` / `profiles` | ID, first name, grade, and role |
| `Question` / `problems` | Type, text, topic, choices, correct answer, explanation |
| `AssignedProblem` / `assigned_problems` | A student ID and a bank question ID |

Both roles use first name and grade. There are no emails or passwords. IDs and
roles are assigned by the server. Each name/grade pair is unique across both
roles. Foreign keys prevent assignments to missing records, and the pair of
student/question IDs prevents duplicate assignments.

Assignments reference the original bank questions. There are no quiz containers,
publication steps, snapshots, deadlines, points, attempts, or stored responses.
Editing a bank question changes what assigned students see. Deleting a question
also deletes its assignment links through the foreign key's `ON DELETE CASCADE`.

`database.py` creates the engine and one session per request. Services call
`db.commit()` when writing. Closing the session rolls back unfinished changes.
Startup runs `Base.metadata.create_all()`; there is no migration framework.

## Login and permissions

`POST /api/auth/login` is the only login endpoint for both roles. It accepts
`first_name` and `grade`, looks up that pair ignoring capitalization, and creates
a profile if needed. Names and grade labels are trimmed. An integer grade becomes
its string label. Python's `casefold()` is also registered as a SQLite function so
the lookup handles Unicode names consistently. Stored spelling stays unchanged.

`TEACHER_PROFILE = ("brian", "12")` in `services/auth.py` defines the teacher pair.
That pair gets the stored teacher role; all other pairs get the student role.
The login response includes `user.role`, so a future website needs only one login
form and can show the appropriate controls afterward. There is no role selector
or separate registration. Anyone entering the teacher pair gets teacher access;
this local profile selector does not prove identity.

Login returns an expiring signed JWT and sets an HTTP-only cookie. Requests
can use the cookie or a bearer header; a nonempty cookie takes priority. Tokens
contain the user ID, expiry, and an audience marking this version of the app.
Older quiz app tokens are rejected. SQLite assigns profile IDs without reusing
deleted IDs, so an old token cannot select a replacement profile.

`dependencies.py` loads the user from the token. `get_teacher` and `get_student`
check the stored role. Login assigns the role from the configured name/grade pair;
it rejects a supplied `role` field.
Logout clears the cookie; there is no token revocation list.

| Action | Access |
| --- | --- |
| Browse bank | Any logged-in user |
| Create, edit, delete questions; view answer keys | Teachers |
| List students, assign/unassign problems, inspect student lists | Teachers |
| View own assigned problems, check individual answers | Students |

The bank is shared among all teachers. There are no private questions or author
ownership rules. Student response schemas omit correct answers and explanations
until they explicitly check an answer.

## Follow an assignment

1. A teacher posts `student_ids` and `question_ids` to `/api/assignments`.
2. The service verifies that every selected profile is a student and every
   selected question exists before adding any assignment links.
3. It adds each missing student/question pair and commits. Repeating the request
   leaves existing pairs alone.
4. A student calls `GET /api/assignments`. The service joins their links to bank
   questions and returns a flat array, ordered by question ID.

The teacher can inspect `/api/assignments/{student_id}` and remove individual
links. There is no attempt to start, quiz to submit, or completion state to track.

## Follow an answer check

1. A student posts `{"response":true}` to `/api/bank/questions/{question_id}/check`.
2. The service loads that bank question and validates the response type.
3. `grading.py` compares the response against the stored accepted answer.
4. The response includes `is_correct`, `correct_answer`, and `explanation`.
   No database write occurs.

Multiple choice compares choice IDs exactly. True/false requires JSON booleans.
Short answer folds case and collapses whitespace before comparing against its
accepted strings. Missing or null responses are incorrect. The student can check
any bank question repeatedly; assignments and feedback have no saved score or history.

## Reading order

| File | Purpose |
| --- | --- |
| `app/main.py` | Startup, router registration, JSON errors, health check |
| `app/config.py` | Database URL, signing secret, token lifetime, cookie setting |
| `app/models.py` | The three tables and their links |
| `app/schemas.py` | Login, question, assignment, and feedback JSON shapes |
| `app/database.py` | Engine, table creation, request sessions |
| `app/security.py` | Signed login tokens |
| `app/dependencies.py` | Current user and role checks |
| `app/routers/auth.py`, `users.py` | Shared login/logout, current user, student list |
| `app/routers/questions.py`, `bank.py` | Teacher CRUD and student bank/check endpoints |
| `app/routers/assignments.py` | Assign, list, and remove bank problems |
| `app/services/auth.py` | Profile lookup/creation and the teacher name/grade rule |
| `app/services/questions.py` | Bank queries, CRUD, response validation |
| `app/services/assignments.py` | Validate selected IDs and store links |
| `app/services/grading.py` | Pure answer comparison functions |
| `app/services/errors.py` | Expected not-found, conflict, and invalid-input errors |

The tests cover the complete teacher/student flow, role boundaries, hidden answer
keys, input validation, repeatable answer checks without writes, assignment
updates/deletions, token expiry, and database persistence. They use isolated databases.

The default database is `problems.db`. Older database files are left intact for
reference. `create_all()` does not transform their former user or quiz schemas;
old student accounts lack grades, so students log in anew and teachers reassign
problems. There are no concurrency locks, CSRF checks, or deployment components.
