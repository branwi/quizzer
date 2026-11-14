# Problem Room

A small website for a teacher and a few students. Everyone uses one first-name
and grade login. Students see their current assigned problems and the problem
bank; the teacher chooses a different problem list for each student.

The frontend is three files of plain HTML, CSS, and JavaScript. FastAPI serves
them and the JSON API from the same server. SQLite stores the bank and assignments.
There is no frontend build step, separate frontend server, or extra dependency.

```text
backend/       Python API, models, routers, and services
frontend/      index.html, styles.css, and app.js
tests/         Backend and API tests
```

Run commands from the project root. The backend serves the frontend from its
sibling folder; both still use the same server and URL.

## Run locally

Use Python 3.11 or newer. In PowerShell, from this folder:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

If `.env` does not exist, copy `.env.example` to `.env`. Generate a signing secret:

```powershell
.venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"
```

Put it in `.env` as `SECRET_KEY=your-generated-value`. Keep your existing secret
if one is already configured. The default database is `problems.db`.

```powershell
.venv\Scripts\python.exe -m uvicorn backend.main:app --reload
```

Open **http://127.0.0.1:8000/** for the website. `/docs` is still available for
exploring the underlying API. Stop an older server with Ctrl+C before restarting.

## Use the website

1. Each student logs in with their first name and grade. Their first login creates
   a profile. Use the same name and grade afterward; capitalization does not matter.
2. Log in as **brian**, grade **12**, to open the teacher page.
3. Select a student from the dropdown. Students appear after their first login;
   use **Refresh** to reload the roster.
4. Check the bank questions you want that student to see, then click
   **Save assigned problems**. Unchecking a question removes it from their list
   when saved. Saving no checked questions clears their list.
5. Choose another student and save their own selection.
6. Students log in to see their assigned list. They can use **Refresh** to see
   changes, switch to **Problem bank**, filter by topic, and check answers.

The student and teacher problem banks show 20 problems per page. Use **Previous**
and **Next** above or below the list. Teacher selections stay checked across pages;
**Save assigned problems** saves all selected questions, including those on other
pages. Changing the student topic filter starts at the first page of matching results.

Use **Add a problem** on the teacher page to create a short-answer problem.
Enter accepted answers one per line. Every problem uses a text answer, compared
against those accepted answers while ignoring capitalization and extra spaces.
Existing bank questions have **Edit** and **Delete** actions. Edits appear in
assigned lists; deleting a question removes its assignments as well.

Feedback shows correctness and an explanation. There are no quizzes, saved answers,
attempts, scores, or completion tracking. A checked problem stays assigned until
the teacher changes the list. Page reloads restore the login through its cookie.

## Import competition problems

Fetch hundreds of problems directly from the online MathNet dataset API:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-import.txt
.venv\Scripts\python.exe -m backend.import_online --limit 500
```

This discovers bulk dataset files through Hugging Face's public API and saves
new problems directly to the configured SQLite database. No hand-maintained
JSON file or API key is needed. PyArrow is only needed when running the importer;
the website's dependencies stay the same. Running it again imports more problems,
skipping MathNet IDs already in the bank. Existing questions and assignments are preserved.
If a download fails, nothing from that run is saved; rerun the same command.

The importer selects English questions with a single integer answer and no
required diagram. It retains source credits and available text solutions.
Imported answer keys come from the dataset and have not all been independently
verified. The app checks final answers; it does not grade competition proofs.
KaTeX displays formulas in questions and explanations, loading from jsDelivr.
If the CDN is unavailable, the original formula text remains visible.

[MathNet](https://huggingface.co/datasets/ShadenA/MathNet) is released under
CC BY 4.0 subject to any original competition copyrights identified in its
license. Attribution and the license link are included in each imported question.

You can also import the included 12 NZMOC problems:

```powershell
.venv\Scripts\python.exe -m backend.import_problems
```

Refresh the website to see them in the problem bank. Existing questions and
assignments are preserved; running the command again skips identical questions.
The command also accepts a path to another JSON list. Each entry contains `text`,
`topic`, `correct_answer` (a nonempty list of accepted strings), and an optional
`explanation`. There are no `type` or `choices` fields. All entries are validated
before any are saved.

Existing databases containing short-answer questions upgrade on startup: the
unused type and choices columns are removed while question IDs and assignments
stay intact. SQLite 3.35 or newer is required for that upgrade. Databases with
other question formats stop with a conversion error rather than discarding data.

The included questions come from the [NZMOC resources](https://www.mathsolympiad.org.nz/resources/),
licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
Sample questions are by Ross Atkins. Each question includes its source credit;
its explanation includes the original URL and license. Notation is transcribed
into plain text for final-answer practice, and explanations are added for this
app. The original competitions also require written justifications.

## Put it online later

This repository has not been deployed. One option is a Render Python web service
with a persistent disk. Render's [FastAPI guide](https://render.com/docs/deploy-fastapi)
describes the web service setup. Its [disk documentation](https://render.com/docs/disks)
explains why the database needs persistent storage; disks require a paid service.

1. Push the source to your GitHub repository. Keep `.env`, `.venv`, and database
   files out of Git; `.gitignore` already excludes them.
2. Create a **Python web service** connected to that repository. Set:

   | Setting | Value |
   | --- | --- |
   | Build command | `pip install -r requirements.txt` |
   | Start command | `python -m uvicorn backend.main:app --host 0.0.0.0 --port $PORT` |
   | Health check | `/health` |

3. Attach a persistent disk mounted at `/var/data`, then set these environment
   variables in the hosting dashboard:

   | Variable | Value |
   | --- | --- |
   | `DATABASE_URL` | `sqlite:////var/data/problems.db` |
   | `SECRET_KEY` | A newly generated random secret, at least 32 bytes |
   | `COOKIE_SECURE` | `true` |

4. Deploy a single service instance. Startup creates missing tables on the mounted
   disk. The website and API will share the service's HTTPS URL; no CORS setup or
   separate frontend hosting is needed.
5. Open that URL, log in as brian / 12, and add your bank problems. The online
   database starts empty; your ignored local database is not uploaded by Git.
   Add the questions through the teacher page before sharing the link.
6. Share the HTTPS URL with your students. Have them log in once, then assign
   their questions from your teacher page.

Only files under `/var/data` persist on that host. A database left in the source
directory would be lost when the service restarts or redeploys. Keep database
backups. The persistent disk is available at runtime, so create tables on startup,
not during the build command.

The current login deliberately uses names and grades rather than verified
identities. Anyone entering brian / 12 gets teacher access, and students sharing
a name and grade share a profile. This remains a demo login when hosted online;
it does not become secure simply because the site has HTTPS.

## Code and checks

* `frontend/index.html`: shared login, student view, teacher view.
* `frontend/styles.css`: responsive layout and styling.
* `frontend/app.js`: form handlers and requests to `/api`.
* `backend/routers/` and `backend/services/`: API endpoints and database operations.

```powershell
.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider
node --check frontend/app.js
node --test tests/frontend-pagination.test.cjs
```

Node is optional and only used for JavaScript checks; the website runs
with Python alone. Read [ARCHITECTURE.md](ARCHITECTURE.md) for the full code map.
