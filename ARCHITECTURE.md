# How the problem bank works

The application is a small website and a FastAPI JSON API backed by SQLite.
Pydantic validates JSON; SQLAlchemy stores records. FastAPI serves the frontend at
`/`, its three assets under `/static`, and the API under `/api`. `/docs` still
lets you explore API requests directly.

Python code lives in `backend/`, and the HTML, CSS, and JavaScript live in the
sibling `frontend/` folder. Run `uvicorn backend.main:app` from the project root.
Settings, dependency files, tests, and local database files stay at the root.

The flow is **request → router → service → database → response**.

## The frontend

`frontend/index.html` contains three sections: a shared login, the student view, and
the teacher view. `frontend/styles.css` provides the layout, including narrow screens.
`frontend/app.js` handles browser interactions using `fetch()` with relative `/api`
URLs. There is no JavaScript framework, templating engine, or frontend build step.

On page load, JavaScript calls `/api/me`. A valid cookie opens the appropriate
view; otherwise the shared login appears. Login returns the user's role, and the
page shows student or teacher controls. The API independently enforces that role.
Tokens are kept in the existing HTTP-only cookie, not browser local storage.

Students switch between their assignments and the bank. Each problem has an
answer form which calls the existing answer-check endpoint. Feedback lives only
on that page. Refresh reloads the current questions from the server.

The teacher chooses a student, loads their current assignments, and selects bank
questions with checkboxes. Saving calls `PUT /api/assignments/{student_id}` with
the complete selection. The bank editor calls the existing question CRUD API.
Server-provided text is inserted using DOM `textContent`, not interpreted as HTML.
KaTeX (loaded from jsDelivr) then renders math delimiters in question text and
feedback. Teacher solutions are rendered when expanded to keep large banks responsive.

Both bank views request 20 questions per page. `GET /api/questions` and
`GET /api/bank/questions` accept `page` and `page_size` (default 20, maximum 100).
They retain their array responses and return `X-Total-Count` and `X-Page` headers.
Filtering and counting happen before SQL `LIMIT`/`OFFSET`; out-of-range pages
clamp to the last available page. Only that page is fetched and rendered.
Students can filter the bank by topic. All questions are short answer, so there
is no question type filter. Free-text search and the `q` parameter are not supported.
The teacher's selected question IDs live separately from the current page, so
paging preserves selections and saving includes questions on other pages.

`python -m backend.import_online --limit 500` discovers MathNet's bulk files
through the Hugging Face API, selects English questions with integer answers
and no required diagrams, and writes them to the existing bank. PyArrow is an
optional import-only dependency in `requirements-import.txt`. No hand-maintained
JSON is needed. Source IDs in question credits prevent duplicate imports; writes
are committed once after downloads succeed. Existing questions and assignments
are preserved. `backend/import_problems.py` also supports the small local JSON list.

## Three tables

| Model/table | Stored information |
| --- | --- |
| `User` / `profiles` | ID, first name, grade, and role |
| `Question` / `problems` | Text, topic, accepted answer strings, explanation |
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
Startup runs `Base.metadata.create_all()` and removes the legacy type and choices
columns from existing short-answer databases. IDs and assignment links are kept.
It refuses to drop those columns if other formats or choices remain, so existing
data is never silently discarded. There is no general migration framework.

## Login and permissions

`POST /api/auth/login` is the only login endpoint for both roles. It accepts
`first_name` and `grade`, looks up that pair ignoring capitalization, and creates
a profile if needed. Names and grade labels are trimmed. An integer grade becomes
its string label. Python's `casefold()` is also registered as a SQLite function so
the lookup handles Unicode names consistently. Stored spelling stays unchanged.

`TEACHER_PROFILE = ("brian", "12")` in `services/auth.py` defines the teacher pair.
That pair gets the stored teacher role; all other pairs get the student role.
The login response includes `user.role`, so the website uses one login form and
shows the appropriate controls afterward. There is no role selector
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

The frontend saves a complete current list using `PUT /api/assignments/{student_id}`.
The service checks all selected IDs before replacing links, then commits once.
An empty selection clears the student's list. Invalid requests leave it intact.
This avoids making separate add/remove requests for every checkbox change.

## Follow an answer check

1. A student posts `{"response":true}` to `/api/bank/questions/{question_id}/check`.
2. Pydantic accepts a text response or null, and the service loads the bank question.
3. `grading.py` compares the response against the stored accepted answer.
4. The response includes `is_correct`, `correct_answer`, and `explanation`.
   No database write occurs.

Every question uses short answers. Grading folds case and collapses whitespace
before comparing against its accepted strings. Missing or null responses are
incorrect. The student can check
any bank question repeatedly; assignments and feedback have no saved score or history.

## Reading order

| File | Purpose |
| --- | --- |
| `backend/main.py` | Startup, router registration, JSON errors, health check |
| `frontend/index.html` | Shared login and student/teacher page sections |
| `frontend/styles.css` | Responsive visual layout |
| `frontend/app.js` | Browser events, rendering, API calls, answer feedback |
| `backend/config.py` | Database URL, signing secret, token lifetime, cookie setting |
| `backend/models.py` | The three tables and their links |
| `backend/schemas.py` | Login, question, assignment, and feedback JSON shapes |
| `backend/database.py` | Engine, table creation, request sessions |
| `backend/security.py` | Signed login tokens |
| `backend/dependencies.py` | Current user and role checks |
| `backend/routers/auth.py`, `users.py` | Shared login/logout, current user, student list |
| `backend/routers/questions.py`, `bank.py` | Teacher CRUD and student bank/check endpoints |
| `backend/routers/assignments.py` | Assign, list, and remove bank problems |
| `backend/services/auth.py` | Profile lookup/creation and the teacher name/grade rule |
| `backend/services/questions.py` | Bank queries, CRUD, response validation |
| `backend/services/assignments.py` | Validate selected IDs and store links |
| `backend/services/grading.py` | Pure answer comparison functions |
| `backend/services/errors.py` | Expected not-found, conflict, and invalid-input errors |

The tests cover the complete teacher/student flow, role boundaries, hidden answer
keys, input validation, repeatable answer checks without writes, assignment
updates/deletions, token expiry, and database persistence. They use isolated databases.

The default database is `problems.db`. Older database files are left intact for
reference. `create_all()` does not transform their former user or quiz schemas;
old student accounts lack grades, so students log in anew and teachers reassign
problems. There are no concurrency locks or CSRF checks. Hosting uses the same
Python server for the frontend and API. SQLite must live on persistent storage;
the README describes a later deployment with an HTTPS URL and a mounted disk.
