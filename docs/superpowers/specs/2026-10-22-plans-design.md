# Plans: guest, user, pro and admin; coming-soon workspaces

Date: 2026-10-22. Status: approved in chat by the owner. Supersedes the access levels (free / subscribed per
workspace) of `2026-10-22-workspaces-design.md`; workspaces, the tile picker, the switcher, server enforcement and
the Stepwise brand from that design stay.

## Intent

The owner wants anyone to try the app without an account, a generous free account, and a paid tier. In their
words: anonymous visitors see what "free" users see today (no compute, no exercises, 20 quiz questions, some
flashcards, some notes); registering makes you a user with unlimited quizzes, notes and flashcards and 10 SQL
exercises a day, but no unlimited exercises and no SQL lab, which need a paid "user-pro" (no payment gateway yet);
a user has one workspace chosen at the start, two or more need the paid plan; the admin sees everything, sets
limits per account and grants or takes rights. The first-visit tiles show technology logos and a few "coming
soon" tiles without content (MySQL, PostgreSQL, pandas and similar) as a teaser.

## Goals

- **G1. The plan is a property of the account** (`role`): `guest`, `user`, `pro`, `admin`. Workspace access rows
  now only mean "is a member of this workspace" (their `level` column is kept for compatibility and written as
  `"member"`).

  | | guest (no account) | user (free account) | pro (paid; granted by an admin for now) | admin |
  |---|---|---|---|---|
  | Quiz questions | 20 a day | unlimited | unlimited | unlimited |
  | Flashcard ratings | 20 a day | unlimited | unlimited | unlimited |
  | Lessons (built-in notes) | first 2 topics + exam guide | all | all | all |
  | SQL exercises (graded) | none | 10 a day | unlimited | unlimited |
  | SQL lab, "Run without checking", flashcard "Try it" | no | no | yes | yes |
  | Mock exams | no | yes | yes | yes |
  | Workspaces | 1, picked at the start | 1, picked at the start | any number (an admin adds them) | all |
  | Practice schema | never | created on the first graded exercise | as user | as today |

  Defaults live in app settings (editable on the Admin page per plan); an admin can override any of the numbers
  for one account ("custom limits"), which wins over the plan's.
- **G2. Guest access.** The sign-in page gets "Try it without an account". It creates a guest account (role
  `guest`, no e-mail, display name "Guest", identity provider `guest`) and its session cookie, then opens the app,
  which shows the tile picker. Guests are rate-limited at creation (per IP, like sign-up throttling) and purged by
  the maintenance job after 30 days without activity. The app shows a persistent "You're browsing as a guest —
  create a free account to keep your progress and unlock more" bar with a Register button.
- **G3. Registering from a guest session keeps the progress.** Registering (password or Google) while a guest
  session is active moves the guest's state, personal notes and workspace membership to the new account, then
  deletes the guest. Signing in to an existing account from a guest session does not merge (the guest is simply
  left to expire).
- **G4. One workspace for guests and users.** The picker grants membership of the picked workspace. A guest or
  user with a membership cannot pick another (the switcher shows the others locked: "Pro plan"). Pro and admin
  see all their workspaces; an admin adds or removes a pro's workspaces.
- **G5. Server enforcement** extends today's: guests get 403 on every SQL endpoint and on `/api/grade`; users get
  403 on `/api/run`, `/api/visualize`, `/api/schema`, `/api/reset-data` and a daily limit on `/api/grade` (counted
  like questions, surviving a progress reset); mock start is refused for guests; notes for guests as today's free
  plan. A user's practice schema is provisioned on demand by the first graded exercise.
- **G6. Admin page.**
  - Role picker: Guest is shown read-only; User / Pro / Admin selectable.
  - Workspaces column and Manage → Workspaces: membership checkboxes for pro accounts; for guest/user a single
    choice (moving their one workspace).
  - Manage → Limits: per-account overrides (questions, cards, exercises per day, free topics; empty = plan
    default), audited.
  - Sign-up panel: plan defaults for guest (questions, cards, topics) and user (exercises per day).
  - Accounts table can hide guests (a "Show guests" toggle, off by default).
- **G7. Picker tiles with logos and coming-soon tiles.** Every tile shows a monochrome technology logo (inline
  SVG from Simple Icons, CC0; brand names are trademarks of their owners and are shown only to name the
  technology). Coming-soon tiles (disabled, "Coming soon" ribbon, not selectable, not in the switcher):
  PostgreSQL, MySQL, SQLite, pandas, Apache Spark (PySpark), DuckDB, Snowflake, Google BigQuery. Real workspaces
  carry the Oracle logo.
- **G8. Migration (one-time, at start-up, per account, idempotent).** `user` with any `subscribed` row → `pro`
  (memberships kept); `user` with only `free` rows → `user` (membership kept); old `learner`/`free` roles go
  through the existing migration first. Rows are rewritten with level `"member"`.

## Non-goals

- Payments, prices, trials, pro expiry.
- Content for the coming-soon workspaces, or any non-Oracle engine.
- Merging a guest into an existing account on sign-in.

## Anti-goals

- A guest triggering any database work (schemas, SQL runs).
- Losing a guest's progress when they register in the same browser.
- An existing pro-level (subscribed) user losing SQL lab or a workspace after the migration.
- Bots filling the accounts table with guests (creation is throttled; guests are purged; admin hides them).

## Calls made (the owner can override)

- Guest flashcards 20/day and lessons = first 2 topics + exam guide (today's free plan numbers); guests have no
  mock exams; users have mock exams.
- Guest sessions last like normal sessions (idle 7 days, absolute 30 days); guests purge after 30 days inactive.
- Flashcard "Try it" and exercises' "Run without checking" count as SQL lab (pro).
- Coming-soon list as above; logos from Simple Icons, inlined.
