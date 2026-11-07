# Quiz API

A small FastAPI application for teachers to create and assign quizzes, and for
students to answer them and get automatic feedback. It uses SQLite and has one
interface: a JSON API, which you can try through FastAPI's interactive `/docs`.

## Run locally

Use Python 3.11 or newer. In PowerShell, from this folder:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

If you do not already have `.env`, copy the example:

```powershell
Copy-Item .env.example .env
.venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"
```

Put the generated value in `.env` as `SECRET_KEY=your-generated-value`.
Keep an existing secret if you already configured one. Then start the server:

```powershell
.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Open **http://127.0.0.1:8000/docs**. Expand an endpoint, click **Try it out**,
edit the JSON, and click **Execute**. `/health` checks that the app can query the
database. There is no separate home page or dashboard.

Startup calls SQLAlchemy's `create_all()` to create missing tables. Existing
records stay in place. It does **not** alter existing tables: an older database
can still have the old constraints and migration bookkeeping table. To try the
lighter schema without touching that data, set
`DATABASE_URL=sqlite:///./quizzer-simple.db` in `.env` and restart.

## Try a complete quiz

1. Use `POST /api/auth/register` twice, once for each role. Save the returned
   student ID. Example registration:

   ```json
   {"name":"Teacher","email":"teacher@example.test","password":"long-demo-password","role":"teacher"}
   ```

   For the student, change the name, email, and role to `student`.
2. Use `POST /api/auth/login` with the teacher email and password. Login sets a
   cookie, so subsequent calls from `/docs` are authenticated automatically.
3. Create a question with `POST /api/questions`:

   ```json
   {"type":"true_false","text":"Two is even.","topic":"Math","correct_answer":true,"explanation":"Two divides evenly by two.","is_public":true}
   ```

4. Create a draft with `POST /api/quizzes`, replacing `1` with the question ID:

   ```json
   {"title":"Math quiz","questions":[{"question_id":1,"points":2}]}
   ```

5. Publish it with `POST /api/quizzes/{quiz_id}/publish`. Assign it with
   `POST /api/quizzes/{quiz_id}/assignments`, using `{"student_ids":[1]}` with
   your actual student ID.
6. Log in as the student. List assignments with `GET /api/quizzes/assigned`,
   then call `POST /api/quizzes/{quiz_id}/attempts`. Save the attempt ID and the
   returned `questions[0].id` (the quiz question ID).
7. Call `POST /api/attempts/{attempt_id}/submit`:

   ```json
   {"answers":[{"quiz_question_id":1,"response":true}]}
   ```

   Replace `1` with the quiz question ID from the attempt. The response includes
   the score, correct answer, and explanation. `GET /api/attempts/{attempt_id}`
   shows that review again.
8. Log back in as the teacher. View `/api/quizzes/{quiz_id}/results` and
   `/api/quizzes/{quiz_id}/analytics`.

Teachers can also edit and delete their questions. Both roles can search
`GET /api/bank/questions`; students can build practice quizzes with
`POST /api/quizzes/practice` and `{"question_ids":[1]}`. Practice uses the same
attempt and grading endpoints. Multiple choice uses a choice ID as its response;
short answer uses a string. See `/docs` for the complete request formats.

For a separate API client, send the login response's `access_token` as
`Authorization: Bearer <token>`. Logout clears the cookie; a copied bearer token
remains valid until it expires.

## Check the code

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\ruff.exe check app tests
.venv\Scripts\ruff.exe format --check app tests
```

Tests use isolated databases. Read [ARCHITECTURE.md](ARCHITECTURE.md) for the code
map and behavior. This version is intended for local learning and demonstrations:
it has no custom concurrency coordination or CSRF protection. Registration allows
either role. Keep `.env`, `.venv`, and database files out of Git; `.gitignore`
already excludes them.
