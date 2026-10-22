# Workspaces Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn exams into workspaces with per-workspace access (none / free / subscribed) granted by admins, a first-visit tile picker, a locked-aware switcher, server-enforced free limits, admin tools, and the "Stepwise" working brand.

**Architecture:** A new `access` package holds the access record, the pure policy (who may use what, free limits, daily usage) and the workspace service; a `WorkspaceAccessRepository` joins `AppStores` with memory, SQLite and Oracle implementations. `UserContexts` resolves the request's workspace and access level once, and every controller enforces from `UserContext`. The front end reads one `/api/workspaces` overview and the `access` block of the progress snapshot.

**Tech Stack:** Python 3.14 stdlib web app, pytest, ruff; vanilla ES modules, strict CSP; SQLite and Oracle stores; i18n catalogs `src/oracle_lab/i18n/pl.json` (server) and `src/oracle_lab/resources/static/i18n/pl.json` (front).

**Spec:** `docs/superpowers/specs/2026-10-22-workspaces-design.md`

## Global Constraints

- Tests: `.venv/bin/python -m pytest -q`; lint: `.venv/bin/python -m ruff check src tests`. Both clean after every task.
- Every user-visible string goes through `t()`/`tn()` (front) or `Msg.of`/HttpError messages (server) and gets a Polish entry; gender-neutral Polish (content/AUTHORING.md rule).
- Access levels are exactly `"free"` and `"subscribed"` (stored); `"none"` exists only in API payloads and admin requests.
- Roles become exactly `"user"` and `"admin"`.
- Free limit defaults: 20 questions per day, 20 flashcards per day, the first 2 topics' notes plus the exam guide. Settings keys: `free_questions_per_day`, `free_cards_per_day`, `free_topics`.
- Workspace-required answer: HTTP 409 `{"error": "Choose a workspace first.", "workspace": "required"}`.
- Limit answer: HTTP 403 `{"error": <message>, "limit": "questions" | "cards"}`.
- Audit event for admin changes: `workspace_access_changed` (target user, workspace, level); for a user's own pick: `workspace_chosen`.
- Brand: env `STUDY_APP_NAME`, default `Stepwise`; tagline "Master data, one step at a time." / "Opanuj dane krok po kroku.". Internal names (`oracle_lab`, `oracle-lab`, `STUDY_` vars, image) do not change.
- Never touch ports 8080/8071 except the final redeploy; never `pkill -f`; never print secrets. Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. A pre-migration `learner` must keep SQL lab, exercises, mocks and unlimited quizzes in both Oracle workspaces after the first start — pinned in Task 3.
2. Free limits must count answers and ratings from every page (Today, Quiz, Mistakes, Flashcards), and the 21st answer of the day is refused even if sent directly to the API — pinned in Task 4.
3. An admin with no access rows must never get 409 or the picker — pinned in Tasks 4 and 6.
4. Moving a free user's workspace (admin picks Free elsewhere) must leave exactly one free row — pinned in Task 5.
5. A user whose saved `exam` is a workspace they lost access to must land in a workspace they may use, not on a 403 loop — pinned in Task 4.

---

### Task 1: Workspace access store

**Files:**
- Create: `src/oracle_lab/access/__init__.py`, `src/oracle_lab/access/models.py`
- Modify: `src/oracle_lab/accounts/repositories.py` (Protocol + `AppStores.access`), `src/oracle_lab/accounts/memory.py`, `src/oracle_lab/accounts/sqlite_store.py` (new `MIGRATIONS` entry), `src/oracle_lab/accounts/oracle_store.py` (new `MIGRATIONS` entry + class), `src/oracle_lab/accounts/deletion.py` (delete rows with the account)
- Test: `tests/test_access_store.py`

**Interfaces:**
- Produces:
  - `access.models.Level = Literal["free", "subscribed"]`
  - `@dataclass(frozen=True) class WorkspaceAccess: user_id: str; workspace: str; level: Level; granted_by: str; granted_at: float`
  - `WorkspaceAccessRepository` Protocol: `for_user(user_id) -> list[WorkspaceAccess]`, `put(rec) -> None` (upsert on `(user_id, workspace)`), `delete(user_id, workspace) -> None`, `delete_for_user(user_id) -> None`, `all() -> list[WorkspaceAccess]`
  - `AppStores.access: WorkspaceAccessRepository`

- [ ] **Step 1: Write the failing tests** — parametrized over memory and SQLite (`sqlite_stores(tmp_path / "app.db")`), same style as the existing store tests:
  - `test_put_upserts_by_user_and_workspace`: put free then subscribed for ("u1", "1Z0-071") → `for_user("u1")` has one row, level `"subscribed"`.
  - `test_delete_and_delete_for_user`.
  - `test_deleting_the_account_drops_its_access` via `AccountDeletion` (existing fixtures in `tests/test_admin.py` show how to build it).
- [ ] **Step 2: Run** `.venv/bin/python -m pytest -q tests/test_access_store.py` — FAIL (no module).
- [ ] **Step 3: Implement.** SQLite table `workspace_access(user_id TEXT REFERENCES users(id) ON DELETE CASCADE, workspace TEXT NOT NULL, level TEXT NOT NULL, granted_by TEXT NOT NULL, granted_at REAL NOT NULL, PRIMARY KEY (user_id, workspace))`; Oracle `app_workspace_access` with `VARCHAR2(40 CHAR)` workspace/level, `BINARY_DOUBLE` time, upsert via `MERGE`. Memory store cascades through `MemoryUsers.on_delete` like the others.
- [ ] **Step 4: Run** the new tests and the full suite — PASS.
- [ ] **Step 5: Commit** `feat(access): workspace access store`.

### Task 2: Access policy and free limits

**Files:**
- Create: `src/oracle_lab/access/policy.py`, `src/oracle_lab/access/limits.py`
- Modify: `src/oracle_lab/exams.py` (add `title: str`, `tile: str` to `Exam` and `public()`), `src/oracle_lab/i18n/pl.json`
- Test: `tests/test_access_policy.py`

**Interfaces:**
- Consumes: Task 1 `WorkspaceAccess`.
- Produces:
  - `policy.level_in(role: str, rows: list[WorkspaceAccess], workspace: str) -> Literal["none", "free", "subscribed"]` (admin → `"subscribed"` everywhere)
  - `policy.usable(role, rows) -> list[str]` — codes in `exams.EXAMS` order
  - `policy.current_workspace(role, rows, saved: str | None) -> str | None` — `saved` if usable, else first usable, else `None`
  - `limits.FreeLimits(questions_per_day: int = 20, cards_per_day: int = 20, free_topics: int = 2)` with `FreeLimits.load(settings_repo) -> FreeLimits` and `save(settings_repo) -> None` (keys from Global Constraints; values validated 0..1000 / 0..15, ValueError otherwise)
  - `limits.used_today(state: State, now: float) -> dict[str, int]` → `{"questions": n, "cards": n}`, counting attempts and card reviews with time ≥ `engine.day_start(now)`
  - `limits.note_allowed(path: str, level: str, free_topics: int) -> bool` — subscribed: always; free: `topics/NN-*` with NN ≤ free_topics, or `docs/exam-guide-*`
- Exam titles: `"Oracle SQL · 1Z0-071"`, `"Oracle SQL · 1Z0-171"`; `tile` is a one-line description (translated in pl.json).

- [ ] **Step 1: Write the failing tests:**
  - `test_admin_is_subscribed_everywhere_without_rows`
  - `test_current_workspace_falls_back_to_a_usable_one` (saved "1Z0-171", rows only free 071 → "1Z0-071"; no rows, role user → None)
  - `test_used_today_counts_only_today` (attempt yesterday + 2 today; reviews likewise)
  - `test_free_limits_round_trip_and_validation` (`free_questions_per_day="-1"` raises ValueError)
  - `test_note_allowed_for_free_users` (`topics/02-restricting-and-sorting/...` True, `topics/03-...` False, `docs/exam-guide-2026.md` True, `docs/cheat-sheet.md` False)
- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement** the functions above (pure; no I/O except the settings repo).
- [ ] **Step 4: Run** the tests and full suite — PASS.
- [ ] **Step 5: Commit** `feat(access): workspace policy and free limits`.

### Task 3: Roles become user/admin, with migration

**Files:**
- Create: `src/oracle_lab/access/migration.py`
- Modify: `src/oracle_lab/auth/models.py` (`Role = Literal["user", "admin"]`), `src/oracle_lab/services/admin.py` (`ROLES = ("user", "admin")`), `src/oracle_lab/auth/registration.py` (default `"user"`), `src/oracle_lab/provisioning/practice.py` (provision at sign-up only for admins; others on first SQL use), `src/oracle_lab/bootstrap.py` (run migration after `ensure_first_admin`), tests that pin `"free"`/`"learner"` roles
- Test: `tests/test_access_migration.py`

**Interfaces:**
- Consumes: Tasks 1–2.
- Produces: `migration.migrate_roles(stores: AppStores, clock: Clock, audit: AuditLog) -> int` — returns accounts migrated; idempotent.

- [ ] **Step 1: Write the failing tests:**
  - `test_learner_becomes_user_subscribed_everywhere` (rows for every `exams.EXAMS` code, `granted_by="migration"`)
  - `test_free_becomes_user_free_in_saved_exam` (state settings exam "1Z0-171" → free row there; no saved exam → `exams.DEFAULT_EXAM`)
  - `test_admin_untouched_and_second_run_changes_nothing`
- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement**; update the role literal and every caller; fix existing tests that assert `"free"`/`"learner"` to the new model.
- [ ] **Step 4: Run** full suite — PASS.
- [ ] **Step 5: Commit** `feat(access): roles collapse to user/admin; migrate learners and free users`.

### Task 4: Server enforcement

**Files:**
- Modify: `src/oracle_lab/services/context.py` (`UserContext.workspace: str | None`, `level: str`, `limits: FreeLimits`; `UserContexts(..., require_workspace: bool = True)` raises `WorkspaceRequired`), `src/oracle_lab/services/__init__.py` (`WorkspaceRequired`, `LimitReached(kind)`, `AccessDenied`), `src/oracle_lab/web/controllers/__init__.py` (`respond` maps them to 409 / 403 with `limit` / 403), `src/oracle_lab/web/middleware.py` `error_boundary` (same mapping for exceptions raised outside `respond`), `src/oracle_lab/services/study.py` (limits on `record_attempt`/`record_card`; `update_settings` refuses an unusable `exam`; `track` uses `ctx.workspace`), `src/oracle_lab/study/progress.py` (`snapshot` adds `"access": {"workspace", "level", "limits", "used"}`), `src/oracle_lab/web/controllers/sql_lab.py` (403 unless `level == "subscribed"`; drop the old `role == "free"` check), `src/oracle_lab/web/controllers/mock_exams.py` (`start` 403 for free; `get`/`abandon` stay allowed), `src/oracle_lab/web/controllers/notes.py` (list marks `locked: true`; `read` 403 for a locked note), server pl.json
- Test: `tests/test_access_enforcement.py`

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces: `UserContext.workspace`, `UserContext.level`, `UserContext.limits`; `sql_available = level == "subscribed" and (learners_get_sql or role == "admin")`; snapshot `access` block (shape above; `limits` is `{"questions": 20, "cards": 20, "topics": 2}` or `null` when subscribed).

- [ ] **Step 1: Write the failing tests** (HTTP, `serve` fixture as in `tests/test_admin.py`):
  - `test_user_without_access_gets_409_on_study_routes` (`/api/progress`, `/api/content`)
  - `test_admin_without_rows_gets_no_409`
  - `test_free_user_21st_answer_is_refused` (20 posts to `/api/attempt` OK, 21st → 403 `limit == "questions"`; same for `/api/card` with `"cards"`)
  - `test_free_user_cannot_run_sql_or_start_a_mock_or_read_topic_3`
  - `test_switching_to_an_unusable_workspace_is_403`
  - `test_saved_exam_without_access_falls_back` (state exam 171, only free 071 → `/api/progress` reports workspace "1Z0-071")
  - `test_subscribed_user_has_no_limits`
  - `test_free_plan_session_fits_the_daily_allowance` (free user: `plan.questions` ≤ 20 and `plan.cards` ≤ 20; implement by passing `limits` into `engine.todays_plan` → `daily_plan(..., max_questions=None, max_cards=None)`, keeping the 5-question / 3-card minimums only when the allowance allows)
- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement.** Messages (en, add pl): "Choose a workspace first.", "You have used today's {n} free questions. Come back tomorrow, or ask an admin for a subscription.", "You have used today's {n} free flashcards. Come back tomorrow, or ask an admin for a subscription.", "This needs a subscription to the workspace."
- [ ] **Step 4: Run** full suite — PASS.
- [ ] **Step 5: Commit** `feat(access): enforce workspaces and free limits on the server`.

### Task 5: Workspace API and admin endpoints

**Files:**
- Create: `src/oracle_lab/access/service.py`, `src/oracle_lab/web/controllers/workspaces.py`
- Modify: `src/oracle_lab/services/admin.py` (`users()` rows gain `"workspaces": [{"code", "level"}]`; settings get/update include free limits), `src/oracle_lab/web/controllers/admin.py` (route `POST /api/admin/workspace-access`), `src/oracle_lab/web/middleware.py` (`PUBLIC_PATHS` untouched; private list in `tests/test_isolation.py` updated), `src/oracle_lab/bootstrap.py` (wire), server pl.json
- Test: `tests/test_workspaces_api.py`

**Interfaces:**
- Consumes: Tasks 1–4.
- Produces:
  - `WorkspaceService(stores, audit, clock)`:
    - `overview(principal, saved: str | None) -> dict` → `{"current": code | None, "workspaces": [{"code", "title", "tile", "engine", "questions", "level"}]}`
    - `choose(principal, workspace, *, ip="", user_agent="") -> None` — only when the user has no rows; grants free, sets state `settings.exam`; ValueError unknown code; `AccessDenied` if rows exist; audit `workspace_chosen`
    - `set_access(actor, user_id, workspace, level: "none" | "free" | "subscribed", *, ip="", user_agent="") -> None` — admin only (controller uses `require_admin`); `"free"` deletes the user's other free row; `"none"` deletes the row; refuses admins as targets (ValueError "Admins already have every workspace."); audit `workspace_access_changed`
  - Routes: `GET /api/workspaces` (with `require_workspace=False` context), `POST /api/workspaces/choose {workspace}`, `POST /api/admin/workspace-access {user_id, workspace, level}`.

- [ ] **Step 1: Write the failing tests:**
  - `test_overview_marks_levels_and_current`
  - `test_choose_once_grants_free_and_sets_default` (second choose → 403)
  - `test_admin_moves_free_access_keeps_one_free_row`
  - `test_admin_subscribes_and_revokes` (revoking all → overview `current` None)
  - `test_admin_settings_round_trip_free_limits`
  - `test_access_changes_are_audited`
- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** full suite — PASS.
- [ ] **Step 5: Commit** `feat(access): workspace overview, first pick and admin access endpoints`.

### Task 6: Tile picker and locked-aware switcher (front)

**Files:**
- Create: `src/oracle_lab/resources/static/js/views/workspace-picker.js`, `src/oracle_lab/resources/static/css/workspaces.css` (linked from `index.html`)
- Modify: `js/main.js` (boot: after `loadSession`, `GET /api/workspaces`; non-admin with `current === null` → render picker, stop boot), `js/ui/exam-picker.js` + `js/shell.js` (locked items: lock icon, "Requires a subscription", `aria-disabled="true"`, skipped on select), `js/core/roles.js` (labels Admin/User; `canRunSql` reads `P.access.level === "subscribed"`), front pl.json
- Test: front catalog tests (`tests/test_i18n_frontend.py`) and a manual browser check

**Interfaces:**
- Consumes: Task 5 routes and overview shape; Task 4 snapshot `access`.
- Produces: `workspacePicker(overview) -> void` renders into `main`; on a tile click → confirm dialog ("{title} becomes your free workspace. Other workspaces need a subscription.") → `POST /api/workspaces/choose` → `location.reload()`.

- [ ] **Step 1:** Implement the picker: heading "Choose your workspace", subtitle, a responsive tile grid (title, engine/database line, tile text, questions count); tiles the user may not pick are greyed with the Premium lock style from `premiumTag()`.
- [ ] **Step 2:** Locked items in the sidebar drop-down; keyboard skips them on Enter/Space, screen readers announce "Requires a subscription".
- [ ] **Step 3:** Run `.venv/bin/python -m pytest -q tests/test_i18n_frontend.py` — PASS; drive a fresh account in a headless browser (`$CLAUDE_JOB_DIR/tmp/pw`, server on :8098): picker shows, pick 071, app loads, 171 greyed in the drop-down; admin account never sees the picker.
- [ ] **Step 4: Commit** `feat(workspaces): first-visit tile picker and locked workspaces in the switcher`.

### Task 7: Free-plan experience (front)

**Files:**
- Modify: `js/views/home.js` (quiz and flashcard steps show "{left} of {n} left today" for free users; at 0 the step reads as done for today with the subscription hint), `js/views/quiz.js` and `js/views/cards.js` (on an API error with `limit`, replace the question/card with a friendly limit panel: what was used, "Come back tomorrow", "Ask an admin for a subscription"), `js/core/api.js` (`ApiError.limit` from payload), `js/views/notes.js` (locked notes listed with the lock, opening shows the subscription callout), mock exam entry points (`js/views/quiz.js` mock setup, home "Take a mock exam") show the lock, front pl.json
- Test: `tests/test_i18n_frontend.py` + browser check

**Interfaces:**
- Consumes: Task 4 `access` block and 403 `limit` payloads; `premiumTag()`, `premiumCallout()` from `js/ui/widgets.js`.

- [ ] **Step 1:** Implement the counters and panels; the panel never shows a raw error.
- [ ] **Step 2:** Browser check as a free user: answer until the limit, see the panel; locked note; locked mock.
- [ ] **Step 3: Commit** `feat(workspaces): free plan counters, limit panels and locked lessons`.

### Task 8: Admin UI for access

**Files:**
- Modify: `js/views/admin.js` (role picker Admin/User; "Workspaces" column of chips `{title}: Free|Subscribed`; Manage → "Workspaces" dialog with a three-way segmented choice per workspace calling `/api/admin/workspace-access`, confirming before moving a free workspace; sign-up panel fields for the three free limits), `css/admin.css`, front pl.json
- Test: `tests/test_i18n_frontend.py` + browser check

**Interfaces:**
- Consumes: Task 5 endpoints and `users()` row shape.

- [ ] **Step 1:** Implement; admins' rows show "All workspaces" instead of chips and no Workspaces action.
- [ ] **Step 2:** Browser check: subscribe a free user to 171, move their free workspace, revoke all → user sees the picker on reload.
- [ ] **Step 3: Commit** `feat(admin): manage workspace access and free plan limits`.

### Task 9: Stepwise brand

**Files:**
- Modify: `src/oracle_lab/config.py` (`Settings.app_name` from `STUDY_APP_NAME`, default "Stepwise"), `src/oracle_lab/web/static.py` + `src/oracle_lab/web/pages.py` (replace `{{APP_NAME}}` in served `.html`, outside inline scripts so CSP hashes hold), all `*.html` (title, sidebar brand, sign-in headers, `<html data-app-name>`), `js/core/router.js` (title from `document.documentElement.dataset.appName`), `src/oracle_lab/web/report.py` footer, `src/oracle_lab/cli.py` log + description, `src/oracle_lab/__init__.py` docstring, both pl.json catalogs (`{app}` placeholders), `README.md`, `docs/docker.md` (env var)
- Test: `tests/test_brand.py`

- [ ] **Step 1: Write the failing tests:** `test_pages_show_the_configured_name` (`STUDY_APP_NAME=Acme` → `/login` contains `<title>` with "Acme", no "{{APP_NAME}}"); `test_default_name_is_stepwise`; `test_no_oracle_learning_lab_left` (grep of `resources/static` and server catalogs finds no "Oracle Learning Lab").
- [ ] **Step 2: Run** — FAIL. **Step 3: Implement.** **Step 4: Run** full suite — PASS.
- [ ] **Step 5: Commit** `feat(brand): Stepwise working name from STUDY_APP_NAME`.

### Task 10: Docs, full check, redeploy

- [ ] **Step 1:** README: workspaces, access levels, free limits table, admin how-to; replace the roles table from the previous feature.
- [ ] **Step 2:** Full suite + ruff clean; `oracle-lab validate --complete` for pl/en (as in the i18n work) shows 0 problems.
- [ ] **Step 3:** `docker compose build lab && docker compose up -d lab`; wait for healthy; confirm on :8071 that existing accounts migrated (admin page shows Workspaces column).
- [ ] **Step 4: Commit** `docs: workspaces and free plan`.
