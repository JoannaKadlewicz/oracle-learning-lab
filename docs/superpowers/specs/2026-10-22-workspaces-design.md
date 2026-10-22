# Workspaces, per-workspace subscriptions and the Stepwise brand

Date: 2026-10-22. Status: for the owner's review.

## Intent

The owner wants the app to stop being "an Oracle app" and become a general learning engine for data
languages: SQL first (today's two Oracle exams), maybe pandas and others later, with gamification and
user-vs-user challenges to come. Two things make that possible now:

1. **Workspaces.** Each certification or learning track (today: "Oracle SQL · 1Z0-071" and
   "Oracle SQL · 1Z0-171") is a workspace. A user belongs to 1..N workspaces. On the very first visit a
   user must pick a workspace from a grid of tiles; it becomes their default. They switch between the
   workspaces they may use from a drop-down; the others are visible but greyed out as needing a
   subscription.
2. **Access is per workspace, not per account.** In the owner's words:
   - A **free** user is assigned to exactly one workspace, the one they picked. In it they get a limited
     number of quiz questions and flashcards per day and only the first lessons. They still see the other
     workspaces, greyed out, "requires a subscription".
   - A user with a **subscription** to a workspace can do everything in it: SQL exercises, SQL lab, (later)
     gamification and rankings.
   - **For now an admin grants subscriptions** on the Admin page. Payments come later.

The product also gets a new name. The owner chose **Stepwise** (tagline "Master data, one step at a
time." / "Opanuj dane krok po kroku."). A web check found an existing edtech product called StepWise
(Querium, an AI math tutor), so **Stepwise is a working name**: it lives in one configuration value so the
final name is a one-line change before a public launch.

## Goals

- **G1. Workspace = today's exam registry entry.** `exams.EXAMS` is already the single source of
  exam facts and content packs; a workspace is that entry plus a display title
  ("Oracle SQL · 1Z0-071"), a short tile description and an icon. No second registry. The settings key
  `exam` keeps meaning "the current workspace".
- **G2. First-visit tile picker.** A signed-in non-admin user with no workspace access sees a full-page
  "Choose your workspace" screen instead of the app: one tile per workspace (title, engine/database,
  one-line description, number of questions). Picking a tile (with a confirmation that, on a free
  account, this is their one free workspace) grants free access to it and makes it the default. Until
  they pick, every study API answers 409 `{"error": "Choose a workspace first.", "workspace": "required"}`.
- **G3. Switching.** The existing sidebar drop-down ("Preparing for") becomes the workspace switcher.
  It lists every workspace; the ones the user cannot use are greyed with a lock and "Requires a
  subscription", focusable (so screen readers announce them) but not selectable. Selecting a usable one
  switches exactly as the exam switch does today. The server refuses (403) to switch to a workspace the
  user has no access to.
- **G4. Access model.** A user's access to a workspace is one of: `none`, `free`, `subscribed`.
  - A non-admin user holds `free` in at most one workspace, and never `free` and `subscribed` in the same
    one.
  - Admins (global role) have `subscribed`-level access to every workspace without rows.
  - Their default workspace is their saved `exam` if they may use it, else the first workspace they
    may use.
- **G5. What each level allows in a workspace.**

  | | free | subscribed |
  |---|---|---|
  | Quiz / practice questions | up to **20 answered per day** (setting) | unlimited |
  | Flashcards | up to **20 rated per day** (setting) | unlimited |
  | Today's session | yes, sized to the remaining allowance; exercise shown locked (as today) | full |
  | Notes / lessons | topic notes of the **first 2 topics** (setting) and the exam guide; the others listed, locked | all |
  | Mock exams | locked | yes |
  | Exercises, SQL lab, practice schema | locked (as today's free role) | yes |
  | Mistakes, progress, own notes | yes | yes |
  | Rankings, challenges (future) | no | yes |

  "Per day" is the user's local day as the engine already defines it. Limits are enforced on the server
  (`/api/attempt`, `/api/card`, `/api/note`, `/api/mock/*`, SQL endpoints); the UI shows what is left
  ("12 of 20 questions left today") and a friendly locked state when it runs out, never a raw error.
- **G6. Roles simplify.** The account role becomes `admin` or `user`. Today's `learner` and `free` roles
  stop existing; what they meant moves into workspace access. Migration on start-up, once:
  - `learner` → `user` + `subscribed` to every workspace (nobody loses anything);
  - `free` → `user` + `free` in their saved exam workspace (or the default one);
  - `admin` stays `admin`.
  New accounts are `user` with no workspace access (so they get the picker). The first account and
  `STUDY_ADMIN_EMAIL` still become admin.
- **G7. Admin page.**
  - The accounts table keeps the role picker (now Admin / User) and gets a **Workspaces** column: one
    chip per workspace the user can use, marked Free or Subscribed.
  - **Manage → "Workspaces"** opens a dialog listing every workspace with a three-way choice per row:
    No access / Free / Subscribed. The one-free-workspace rule is enforced (picking Free in a second
    workspace moves the free access there, after a confirmation). Each change is audited
    (`workspace_access_changed`).
  - The sign-up panel gets the **free plan limits**: questions per day, flashcards per day, free topics.
- **G8. Brand.** A setting `STUDY_APP_NAME` (default "Stepwise") and a tagline replace "Oracle Learning
  Lab" everywhere a user can see it: page titles, sidebar brand, sign-in pages, readiness report footer,
  CLI start-up log, README. The logo stays. Internal names (package `oracle_lab`, CLI `oracle-lab`,
  Docker image, env-var prefix `STUDY_`) do not change.
- **G9. Built for what comes next, without building it.** Engine-specific code stays behind the
  existing engine boundary, and exercise grading stays "compare the result with the reference result",
  so a pandas engine and duels (two users, same task, each picks a language, first correct result wins)
  can be added later without reshaping workspaces.
- **G10. Nothing breaks.** Existing users keep their progress, notes, mock history and practice schemas;
  all current tests pass, adjusted only where they pin the old roles.

## Non-goals

- Payments, plans, prices, trials, expiry dates. (Access rows carry `granted_by` and `granted_at`;
  nothing else.)
- Gamification, rankings, duels, a pandas engine, new content.
- Renaming the code package, CLI, image or env vars.
- Letting a free user change their own free workspace (an admin can).
- Separate progress per workspace beyond today's: the two Oracle workspaces share the "oracle-sql"
  pack, so their answers count in both, as now.

## Anti-goals

- A free user hitting a limit and seeing an error or a blank page instead of a clear, kind "come back
  tomorrow, or ask for a subscription".
- Any limit enforced only in the browser.
- An existing learner losing access to something they had yesterday.
- The picker blocking admins (they never see it) or trapping a user who has access somewhere.

## Constraints

- Python stdlib web app, vanilla ES modules, strict CSP, SQLite and Oracle stores. The new access table
  goes into both stores (`workspace_access(user_id, workspace, level, granted_by, granted_at)`, primary
  key `(user_id, workspace)`), with the same repository-interface pattern as the other stores, and is
  deleted with the account.
- Every user-visible string goes through the i18n catalogs (en + pl) and their tests.
- `pytest` and `ruff` clean; behaviour changes covered by tests, server-side limits especially.

## Decided by the owner

- Workspace = certification/track; 1:N users to workspaces; tile picker on first visit; the picked tile
  becomes the default; switch by a drop-down; other workspaces visible but greyed, needing a subscription.
- Free = exactly one workspace, daily-limited quizzes and flashcards, first lessons only.
- Subscription per workspace = everything, including SQL exercises, SQL lab and (future) gamification.
- Subscriptions granted by an admin for now; payments later.
- Gamification and duels are future work; duels let each player pick a language, first correct result
  wins.
- Name: Stepwise, as a working name pending a trademark check.

## Calls made in this design (the owner can override)

- Workspace reuses the exam registry; no new registry.
- Roles collapse to admin/user; migration grants existing learners every workspace.
- Free limits default to 20 questions, 20 flashcards a day and the first 2 topics' notes plus the exam
  guide, editable by an admin.
- Mock exams are subscription-only (a full mock is 60+ questions, over the free daily limit).
- Locked workspaces in the drop-down are visible and announced but not selectable; there is no "request
  access" button yet (the locked text says to ask an admin).
- The free-workspace choice is final for the user; an admin can move it.
- A user whose last access an admin removes sees the picker again on the next load (to stop someone
  using the app at all, the admin locks the account).
- Free limits count every answer and every card rating in the workspace, whichever page they come from
  (Today, Quiz, Mistakes, Flashcards). The flashcard limit caps the user's own "new cards per day"
  setting, never raises it.
- The two Oracle workspaces stay separate subscriptions even though they share content; an admin grants
  each.

## Left to the builder

- Layout of the tile picker and of the workspace dialog, within the existing design system.
- Exact wording of locked states and limit counters (en + pl), kind and short.
- How the daily counters are computed (from state timestamps, as the plan already does, is expected).
- Order of the work, in reviewable steps: access store and migration → server enforcement → picker and
  switcher → admin UI → brand.
