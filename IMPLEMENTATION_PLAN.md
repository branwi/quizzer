# Architecture review and implementation plan

Reviewed November 7, 2026 against `ARCHITECTURE.md`. The initial project contained
only that document: no application, dependency manifest, database, or tests.
The supplied AGENTS instructions reference `RTK.md`, but that file was absent
from the workspace and the checked ancestor locations.

## Gaps and contradictions

| Finding | Consequence and recommendation |
| --- | --- |
| The original draft described role-specific/owned resources while explicitly omitting server access checks. | Resolved: roles, ownership, assignment eligibility, and attempt ownership are enforced. The architecture now reflects the implemented access policy. |
| Every route supposedly requires login except register/login, but login/register pages, `/docs`, OpenAPI, and operational endpoints must be reachable. | Explicitly exempt these routes. Milestone 1 exposes only `/health`, `/docs`, `/redoc`, and `/openapi.json`; no user/question data is available over HTTP. |
| Services must return filtered data, but the lifecycle also relies on `response_model` to strip ORM fields. The bank has role-dependent schemas. | Use explicit safe service DTOs plus API response schemas. Never pass complete snapshots to an in-progress template. Define separate in-progress and review responses; test nested answer-key leakage. |
| Snapshot content is frozen at publication, but draft links already exist and the table does not specify whether `snapshot` can be null. | Adopt SQL NULL for draft snapshots. Publishing must fill all snapshots in one transaction. Deleting a source question sets its link to NULL; publishing a draft with such a link must fail clearly. |
| The draft omitted eligibility and details of abandoned/resumed/late attempts and omitted/invalid answers. | Resolved using the proposed defaults: assignment or practice ownership, starts consume attempts, one open attempt is resumed, starts/submissions close at the deadline, missing answers score zero, and duplicate/foreign ids fail. |
| Checking an attempt count or `submitted_at` and then writing is not sufficient under concurrent requests. | Use an atomic start limit and conditional submission transition, with concurrency tests on file-backed SQLite. A second submission should return 409 even when requests overlap. |
| `True == 1` in Python, and the sketch short-answer grader assumes a string. | Use strict per-type response validation; explicitly handle blank/missing responses. Do not reuse the sketch unchanged. |
| There is no UTC convention, and SQLite does not preserve timezone offsets through ordinary datetime columns. | Adopt aware UTC at the Python boundary and reject naive datetimes. Implemented in milestone 1, including SQLite round-trip tests. |
| An answer's two independent foreign keys allow it to refer to a question in another quiz. | Add `answers.quiz_id` and composite foreign keys tying both sides to the same quiz. Implemented; this is a deliberate schema extension. |
| A database URL alone is presented as enough to switch to PostgreSQL. | A driver, migrations, and integration tests are also needed. SQLite is the only verified database for this milestone. |

Self-selected teacher registration is retained for the authentication milestone,
matching the draft. HTML forms now use signed CSRF tokens; JSON API CSRF hardening
and login rate limiting remain future deployment work.

## Short implementation plan

1. **Foundations (implemented):** configuration, all seven ORM tables, SQLite
   foreign-key enforcement, UTC handling, repeatable seed data, a minimal FastAPI
   startup/health endpoint, and persistence/constraint tests.
2. **Identity and questions (complete; architecture milestones 2–4):**
   register/login/logout/current user, cookie and bearer JWTs, teacher-only question
   CRUD with author ownership, strict schemas for all three question types, and a
   pure grading engine. Tests cover permissions, validation, and safe projections.
3. **Quiz workflow (complete; milestones 5–7):** draft editing, transactional
   publication, idempotent assignment, atomic start/submit/review, weighted scores,
   teacher results, and a role-safe bank with practice reuse. The attempt/deadline
   defaults above are adopted and tested.
4. **Browser experience and delivery (implemented; milestones 8–9):** Jinja2/HTMX
   pages reuse services; owner-only analytics, migrations, Docker, and run docs
   are included. HTTP and container checks pass; visual browser QA is blocked by
   the tooling limitation documented below.

## Milestone 1 conventions and boundaries

- Application files live directly under `app/` in this repository; an additional
  `quizapp/` wrapper directory would serve no purpose.
- Python 3.11+, synchronous SQLAlchemy 2.0, and SQLite match the requested stack.
  Dependencies are pinned in the generated requirements files.
- `create_all` runs at app startup and before seeding. It creates missing tables,
  but does not migrate existing schemas. Add Alembic before changing persistent
  schemas that contain valuable data.
- Positions are zero-based; points and attempt limits are positive. Assigned
  quizzes default to one attempt, practice to unlimited; explicit NULL means
  unlimited for either kind.
- Foreign keys restrict deletion of users, quizzes, and quiz links that other
  records still reference. Only source-question deletion uses `SET NULL`, keeping
  published snapshots and history intact.
- ORM queries are explicit; no automatic relationship loading is needed yet.
  JSON shape, role-specific ownership, published immutability, and the rule that
  answers are written only during submission belong to future services. Database
  constraints do not claim to enforce all these business rules today.
- The seed is one transaction and populates every table. An existing demo teacher
  makes reruns a no-op; it does not repair manually edited/deleted demo records.
  It refuses a pre-existing demo student email rather than overwriting it.
- Seeded score/history is a fixed illustrative fixture. At the milestone 1
  checkpoint, no grading, authentication, authoring, or quiz-taking HTTP endpoint
  or browser page existed.

## Authentication milestone (implemented)

- Milestone 1 was saved as Git checkpoint `88e5fad` before authentication changes.
  The project now has its own repository; virtual environments, `.env` variants,
  secret/key files, and local SQLite files are excluded.
- Public `POST /api/auth/register` returns a safe user DTO (201) without logging
  in; public `POST /api/auth/login` returns a token and sets the cookie. Private
  `GET /api/me` and `POST /api/auth/logout` inherit authentication from the private
  API router. Health and documentation remain public.
- Services accept sessions and validated data, return explicit DTOs, and never
  depend on request objects. Passwords use the existing Argon2 helper. Login
  errors are generic, and unknown accounts still perform password verification.
- Names are trimmed; email is validated and case folded. `.test` email domains
  remain accepted to support the existing demo. Passwords preserve whitespace,
  with 8–128 characters for registration. Teacher registration stays self-selected.
- JWTs use only HS256, with a user-id subject, issue time, expiry, and an account
  version bound to the salted password hash. Defaults
  remain 60 minutes. Every authenticated request reloads the user from the DB;
  missing/deleted accounts and invalid/expired tokens return 401.
- A nonempty cookie takes precedence over a bearer header. Invalid cookies do
  not fall back to a valid header. Swagger exposes HTTP bearer authorization.
- Cookies are HTTP-only, SameSite=Lax, path `/`, with matching JWT/cookie lifetimes.
  `COOKIE_SECURE` enables HTTPS-only cookies. Successful auth responses use no-store headers;
  request-validation errors omit raw inputs to avoid echoing passwords.
- App startup requires a random `SECRET_KEY` of at least 32 bytes. No secret is
  committed; seed/shell commands can still run without one. No schema changes or
  migration of the existing milestone 1 database were needed.
- Logout clears the cookie and returns 204. Stateless bearer tokens cannot be
  revoked by this endpoint and remain valid until expiry while the account and
  credentials exist. HTML forms and their CSRF protection are now implemented;
  rate limiting and JSON API CSRF hardening remain future work.

## Identity and questions milestone (complete)

The user clarified that “milestone 2” means step 2 of this plan, including
architecture milestones 3 (question CRUD) and 4 (grading), as well as login.

- Added `POST/GET /api/questions` and `GET/PUT/DELETE /api/questions/{question_id}`.
  Routers use the shared services; services enforce teacher roles and author
  ownership independently of HTTP. Students receive 403 and other teachers'
  questions receive 404. This deliberately replaces the draft's login-only access
  policy for these new endpoints. Public bank access was added in milestone 7.
- MCQ, true/false, and short-answer inputs form a discriminated union. MCQ choice
  ids are unique and answers must match; booleans are strict; accepted short-answer
  strings are nonblank. Extra fields, such as a caller-provided author id, fail
  validation. Common fields are bounded and trimmed; questions default to private.
- PUT is a full replacement and may change the question type. Omitted optional
  content resets to its defaults; id/author/creation time are preserved. Published
  snapshots and existing grades survive edits and source deletion.
- Own-question lists support prompt/topic search, exact topic, question type,
  visibility, and pagination. Results are newest first with id as a tie breaker.
  Page size is 1–50 (20 by default); invalid bounds return 422. LIKE metacharacters
  are escaped. Student DTOs explicitly omit answer keys and explanations.
- `app/services/grading.py` is pure and snapshot based. MCQ ids match exactly;
  true/false responses must be actual booleans; short answers use Unicode case
  folding and collapsed whitespace. Wrong types/blank responses are incorrect.
  Unknown question types raise `ValueError`; milestone 6 now applies weighted totals.
- Verification found that deleting the highest-id SQLite user could let an old
  token authenticate a newly registered user reusing that id. Tokens now require
  a keyed account fingerprint, checked against the current salted password hash.
  No schema migration is needed; existing accounts/data remain usable, but tokens
  issued before this fix require a new login. Regression tests exercise actual
  SQLite id reuse and every private API operation's authentication requirements.

Verification at the completion of step 2: 180 tests passed, plus Ruff lint/format checks and `git diff --check`.
A live Uvicorn check against a disposable file-backed database verified register,
login, CRUD for all question types, filtering, student access denial, grading,
data/session persistence across a server restart, and logout. The local demo seed
was rerun without changing its data. One upstream Starlette/httpx TestClient
deprecation warning remains; it does not affect the checks.

## Quiz workflow (milestones 5–7 complete)

- **Quiz building and assignment:** teacher-owned draft creation and full PUT
  replacement; own-quiz listing/details; publish-time snapshots; paginated student
  picker; idempotent assignments; owner-only paginated attempt/score results.
  Teachers may include their own private questions and other teachers' public
  ones. All sources are rechecked at publish, so missing/withdrawn sources prevent
  publication without partial writes. Published metadata/content are frozen.
- **Attempts:** assignment or practice ownership is required. New starts return
  201 and consume one attempt; repeated starts return the existing open attempt
  with 200. All starts count toward the limit. At/after a due date, start/resume
  and submit return 409; an owned attempt can still be read. Review reveals keys
  immediately after successful submission. Other students' attempts return 404.
- **Submission:** request `answers` uses quiz-question link ids from the attempt,
  not source question ids. Duplicate/foreign ids and malformed responses return
  422. MCQs use actual choice ids (or blank/null); booleans are strict; short
  answers are strings. Missing/null answers are wrong. Every question gets one
  answer row and all-or-nothing points, with scores/submission time written in
  the same transaction. Repeated submissions return 409.
- **Concurrency:** workflow writes own a fresh transaction and take SQLite's
  `BEGIN IMMEDIATE` lock before checking state/counts. Authentication's read
  transaction is ended first. Submission also conditionally updates an open
  attempt. Independent connections in file-backed race tests verify one attempt
  for simultaneous starts, one grade for simultaneous submits, and idempotent
  assignments. A simulated answer-write failure restores the unsubmitted state.
- **Bank and practice:** public-only text/topic/type filtering and pagination,
  with explicit teacher/student DTOs. A role discriminator prevents accidental
  serialization through the wrong response schema. Students create a published
  self-made quiz from 1–100 unique public ids in one transaction; it has no due
  date, one point per question, and unlimited attempts through the same service.
  Draft/published quizzes contain at most 100 unique questions; point weights
  are positive integers. JSON contracts live in `app/workflow_schemas.py`.
- **Compatibility:** no schema changes, dependency changes, or migrations were
  required; the existing SQLite data and auth configuration remain usable.
  PostgreSQL concurrency is not claimed as verified. Browser pages and analytics
  were added in the subsequent milestones below.
- **Verification:** all 220 tests pass, as do lint, formatting, and diff checks.
  A live Uvicorn demo exercised both flows and verified stored reviews, teacher
  results, attempt limits, and login cookies after restart. It used a disposable
  database. The original local seed can be rerun without changing existing data.
  The existing upstream TestClient deprecation warning remains.
- **Try it:** start Uvicorn, then run `python -m scripts.demo_workflow` against it.
  This adds fresh demo questions/quizzes/attempts with seeded teacher/Bob accounts.
  It verifies a 10/10 frozen assigned quiz and a 2/2 practice quiz from the updated
  bank. See the README for commands and manual Swagger request examples.

## Browser experience and delivery (milestones 8–9 implemented)

- **Browser workflows:** a responsive Jinja2 layout, teacher/student dashboards,
  login/register/logout, all question editors, quiz builder, draft editing,
  publication, paginated student assignment, assigned/practice lists, attempts,
  review, history, and teacher results/insights. History shows quiz titles, not
  technical ids. HTML routes only adapt forms/DTOs and call existing services.
- **Interaction:** locally vendored HTMX 2.0.8 provides debounced question-bank
  and builder filtering/pagination. Selection state remains outside swapped
  partials; weights and selected question titles are retained across pages.
  Plain browser forms perform mutations with redirects; a small local script
  switches editor fields and manages selection state. No build tool/CDN is needed.
- **Form security:** signed double-submit tokens are bound to the current JWT,
  with an anonymous binding for login/register. Every HTML mutation validates the
  token. Auth changes invalidate earlier forms. Templates escape user text,
  private pages/partials use no-store headers, and HTMX history caching is disabled.
  Safe student DTOs remain the only input to in-progress templates.
- **Analytics:** `GET /api/quizzes/{quiz_id}/analytics` and teacher results pages
  show submitted/open counts, score summaries, per-question accuracy, and fixed
  percentage buckets with inclusive 100% handling. Unsubmitted attempts are
  excluded from averages. Empty aggregates remain null/zero as appropriate;
  published snapshots preserve labels when sources are edited/deleted.
- **Migrations:** a frozen Alembic baseline defines all seven domain tables.
  `scripts.migrate` upgrades fresh/tracked databases and only adopts an unchanged
  untracked baseline after schema comparison and a consistent SQLite backup.
  Unknown schemas are refused. Domain data is not reset; Alembic adds only its
  revision bookkeeping. The local bootstrap `create_all` remains for demo/tests.
- **Packaging:** Docker uses Python 3.11, pinned runtime dependencies, a non-root
  user, migration-before-start, and a health check. Compose binds loopback and
  persists SQLite in a named volume. Secrets, virtual environments, local DBs,
  and backups are excluded. Demo accounts are seeded explicitly, not at startup.
- **Verification:** 240 tests pass, plus Ruff lint/format, JavaScript syntax, and
  Compose validation. Tests exercise rendered forms, CSRF, escaping, all question
  types, builder/assign/submit/review/practice, HTMX privacy, analytics boundaries,
  and migration adoption/backup. The image was built and run; live HTTP tests
  verified the API demo and HTML workflows, analytics, static assets, non-root
  execution, container health, and data/session persistence after recreation.
- **Verification limit:** the browser access host was unavailable. The Windows
  fallback explicitly stopped because browser URL-policy enforcement is not
  supported. UI automation ended without bypassing that restriction. Interactive
  clicking, screenshots, and visual/responsive appearance remain unverified;
  rendered HTTP/form tests and JavaScript syntax checks passed. The existing
  upstream Starlette/httpx TestClient deprecation warning remains.
  QA servers and temporary containers were stopped. Automatic tool review blocked
  deletion of the disposable UI test directory with “blocked by policy”; that
  directory remains under the system temporary folder (`quizzer-ui-93167728db8042b4b4a4621da469ea56`).
- **Run:** install updated requirements, run `python -m scripts.migrate`, seed if
  desired, and start Uvicorn. Open `/` for the browser interface or `/docs` for
  JSON APIs. Docker Compose commands, an architecture diagram, and demo account
  details are documented in `README.md`.

