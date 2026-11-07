# Architecture review and implementation plan

Reviewed November 7, 2026 against `ARCHITECTURE.md`. The initial project contained
only that document: no application, dependency manifest, database, or tests.
The supplied AGENTS instructions reference `RTK.md`, but that file was absent
from the workspace and the checked ancestor locations.

## Gaps and contradictions

| Finding | Consequence and recommendation |
| --- | --- |
| Sections 2 and 6 describe role-specific features and resources belonging to a user, while sections 7 and 12 explicitly omit server role and ownership checks. The structure even mentions `require_role`. | Hiding UI controls cannot enforce these promises. Recommend role, ownership, assignment, and attempt-owner checks before exposing quiz routes. This materially changes the stated local-demo access policy; it is a proposed revision, not an implemented login feature. |
| Every route supposedly requires login except register/login, but login/register pages, `/docs`, OpenAPI, and operational endpoints must be reachable. | Explicitly exempt these routes. Milestone 1 exposes only `/health`, `/docs`, `/redoc`, and `/openapi.json`; no user/question data is available over HTTP. |
| Services must return filtered data, but the lifecycle also relies on `response_model` to strip ORM fields. The bank has role-dependent schemas. | Use explicit safe service DTOs plus API response schemas. Never pass complete snapshots to an in-progress template. Define separate in-progress and review responses; test nested answer-key leakage. |
| Snapshot content is frozen at publication, but draft links already exist and the table does not specify whether `snapshot` can be null. | Adopt SQL NULL for draft snapshots. Publishing must fill all snapshots in one transaction. Deleting a source question sets its link to NULL; publishing a draft with such a link must fail clearly. |
| The start flow omits assignment/ownership eligibility. Abandoned attempts, resuming, late submission, unanswered questions, and foreign/duplicate question IDs are unspecified. | Decide these before milestone 6. Recommended: require assignment or practice ownership; count starts, resume an existing open attempt, reject starts/submissions after the deadline, treat missing responses as wrong, and reject foreign or duplicate IDs. Deadline behavior and attempt counting materially affect students. |
| Checking an attempt count or `submitted_at` and then writing is not sufficient under concurrent requests. | Use an atomic start limit and conditional submission transition, with concurrency tests on file-backed SQLite. A second submission should return 409 even when requests overlap. |
| `True == 1` in Python, and the sketch short-answer grader assumes a string. | Use strict per-type response validation; explicitly handle blank/missing responses. Do not reuse the sketch unchanged. |
| There is no UTC convention, and SQLite does not preserve timezone offsets through ordinary datetime columns. | Adopt aware UTC at the Python boundary and reject naive datetimes. Implemented in milestone 1, including SQLite round-trip tests. |
| An answer's two independent foreign keys allow it to refer to a question in another quiz. | Add `answers.quiz_id` and composite foreign keys tying both sides to the same quiz. Implemented; this is a deliberate schema extension. |
| A database URL alone is presented as enough to switch to PostgreSQL. | A driver, migrations, and integration tests are also needed. SQLite is the only verified database for this milestone. |

Other behavior to settle with login: whether self-selected teacher registration
is intentional (the draft implies yes), and how cookie-authenticated mutations
will be protected from CSRF. Neither blocks a database-only milestone.

## Short implementation plan

1. **Foundations (implemented):** configuration, all seven ORM tables, SQLite
   foreign-key enforcement, UTC handling, repeatable seed data, a minimal FastAPI
   startup/health endpoint, and persistence/constraint tests.
2. **Identity and questions (next; architecture milestones 2–4):** register/login/
   logout/current user, explicit access policy, strict question schemas and CRUD,
   and the pure grading engine. Test password hashing, expired tokens, permissions,
   validation, and answer-key isolation.
3. **Quiz workflow (milestones 5–7):** draft editing, transactional publication,
   assignment, atomic start/submit/review, and bank/practice reuse. Resolve the
   attempt/deadline decisions above before implementing this step.
4. **Browser experience and delivery (milestones 8–9):** Jinja2/HTMX pages calling
   the same services, analytics, migrations, and Docker. Run browser flow checks.

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
- Seeded score/history is a fixed illustrative fixture. No grading, authentication,
  authoring, or quiz-taking HTTP endpoint or browser page is implemented yet.

