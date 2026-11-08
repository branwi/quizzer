# Problem Bank API

Everyone uses the same login: first name and grade. `brian` with grade `12` gets
teacher access; all other name/grade pairs get student access. Students browse a
problem bank, see assigned problems, and check answers immediately. The teacher
manages the bank and assignments.

There are no quizzes, attempts, saved answers, scores, or analytics. The interface
is a JSON API with an interactive client at `/docs`.

## Run

Use Python 3.11 or newer. In PowerShell, from this folder:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

If `.env` does not exist, copy `.env.example` to `.env`. Generate a secret:

```powershell
.venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"
```

Put it in `.env` as `SECRET_KEY=your-generated-value`. Keep an existing secret
if one is already configured. The database setting should be
`DATABASE_URL=sqlite:///./problems.db`.

Start the server:

```powershell
.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Open **http://127.0.0.1:8000/docs**. Expand an endpoint, click **Try it out**,
edit the JSON, then click **Execute**. Login sets a cookie, so later requests from
that page use the selected account. A separate client can use the returned
`access_token` in an `Authorization: Bearer <token>` header instead.

## Try the complete flow

1. Log in as the teacher using `POST /api/auth/login`:

   ```json
   {"first_name":"brian","grade":12}
   ```

   The response includes `user.role: "teacher"`. There is no separate registration
   or teacher login. A website can use this role to show the appropriate controls
   after a single shared login form.
2. Log in as a student with `POST /api/auth/login`:

   ```json
   {"first_name":"Maya","grade":6}
   ```

   Save the returned `user.id`. The first login creates a profile; later logins
   with the same name and grade reopen it. `GET /api/me` shows the current profile.
3. Switch back to the teacher using the same `POST /api/auth/login`:

   ```json
   {"first_name":"brian","grade":12}
   ```

4. Create a bank question with `POST /api/questions`:

   ```json
   {"type":"true_false","text":"Two is even.","topic":"Math","correct_answer":true,"explanation":"Two divides evenly by two."}
   ```

5. Assign bank questions directly using `POST /api/assignments`:

   ```json
   {"student_ids":[1],"question_ids":[1]}
   ```

   Replace the IDs with the actual student and question IDs. Every selected
   student gets every selected question. Repeating an assignment adds no duplicates.
   `GET /api/students` lists student profiles.
6. Log back in as Maya. `GET /api/assignments` returns her flat list of questions.
   `GET /api/bank/questions` returns the whole bank. Neither includes answer keys.
7. Use `POST /api/bank/questions/{question_id}/check`:

   ```json
   {"response":true}
   ```

   It returns correctness, the accepted answer, and explanation. Nothing is saved;
   the student can try again. Multiple choice uses a choice ID string, short answer
   uses a string, and true/false uses a JSON boolean.

Teachers use `/api/questions` to list, edit, and delete shared bank questions.
They can inspect a student's list with `GET /api/assignments/{student_id}` and
remove a problem with `DELETE /api/assignments/{student_id}/{question_id}`.
Bank search supports `q`, `topic`, and `type` query parameters.

## Behavior to know

* First name and grade select a profile; they do not verify identity.
  People sharing the same name and grade share a profile. Matching ignores
  capitalization and surrounding spaces. A different grade selects a different
  profile. Grades are labels such as `"6"`, `"K"`, or `"college"`; `6` also works.
* The pair `brian` / `12` gets teacher access regardless of capitalization:
  `Brian` and `BRIAN` work too. `brian` / `11` gets student access. Change `TEACHER_PROFILE` in
  `app/services/auth.py` to change this rule. Anyone entering the teacher pair
  gets teacher access; this is intended for the local demo.
* All bank questions are shared. All teachers can manage them. Editing a question
  updates it in assigned lists; deleting it removes its assignments.
* Checking an answer does not mark a problem complete or remove it from the list.
* Logout clears the cookie. A copied bearer token lasts until its expiry.
* Startup uses `create_all()` to create missing tables. It does not convert older
  schemas. The former `quizapp.db` is retained separately; old quiz/attempt history
  is not used. Student profiles need a name and grade and must be assigned anew.

This is a local learning application. Keep `.env`, `.venv`, and database files out
of Git; `.gitignore` excludes them.

## Checks

```powershell
.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider
.venv\Scripts\ruff.exe check --no-cache app tests
.venv\Scripts\ruff.exe format --check --no-cache app tests
```

Read [ARCHITECTURE.md](ARCHITECTURE.md) for the code map.
