# Multi-exam platform: exam drop-down and a database-engine boundary

Date: 2026-10-21. Status: for the owner's review (builder check done).

## Intent

The app prepares people for two Oracle SQL exams today: 1Z0-071 (Oracle Database 19c) and
1Z0-171 (Oracle AI Database 23ai). The owner sees it growing into a trainer for SQL
certification exams in general, MySQL or PostgreSQL ones among them. This work does two things:

1. **The exam picker becomes a drop-down.** The sidebar's two-button switch under "Preparing for"
   becomes one drop-down. It lists the exams grouped by database product (one group, "Oracle",
   for now). The owner chose this placement (mockup A) over a top bar and over making the app name
   the switcher.
2. **Adding an exam becomes cheap.** In the owner's words, a future PostgreSQL exam should mean
   "question bank, notes, flashcards and probably a new PostgreSQL database to connect with". So
   exams become data (a registry entry). Everything that runs learner SQL goes behind a
   database-engine boundary, so a PostgreSQL engine can be plugged in later without touching the
   rest of the app.

Only Oracle 19c and Oracle 23ai exist after this work. Nothing in the product changes for a learner
except the picker.

## Goals

- G1. **The drop-down.** It sits in the sidebar under "Preparing for", where the switch is now,
  including in the mobile drawer.
  - It shows the current exam's code and its database ("1Z0-071", "Oracle Database 19c").
  - Opened, it lists the exams grouped by product. Each item shows its code, name and database,
    plus a short line with the number of questions and minutes. The current exam is ticked.
  - It is fully usable with the keyboard and with a screen reader, and it works on phones.
- G2. **Picking an exam switches everything exam-related, exactly as the switch does today.** That
  covers questions, flashcards, exercises, mock exams, the Today plan, progress and readiness, and
  the database the SQL runs on. The mock-exam confirmation also stays: a running mock stays open
  and resumes when the learner switches back.
- G3. **The default exam stays 1Z0-071 (Oracle 19c).** It applies to new users and to any user
  whose saved exam is unknown.
- G4. **Exams are data.** One registry entry per exam holds:
  - its code, name and product group;
  - its database engine and which configured database it runs on;
  - its numbers (questions, minutes, pass mark);
  - which content pack it uses;
  - the notes it links to (exam guide, cheat sheet);
  - its short "about" text.

  No code outside the registry names an exam code, "19c" or "23ai".
- G5. **Learner SQL goes through a database-engine boundary.** An engine interface covers:
  - connecting;
  - splitting and running scripts;
  - formatting and explaining errors;
  - describing the schema;
  - loading the sample tables;
  - creating and dropping per-user practice schemas;
  - lab cleanup and grading hooks;
  - optional extras (the join/set visualizer);
  - the SQL editor's highlighting mode.

  Oracle is the one implementation and wraps today's code with no change in behaviour.
- G6. **Content is grouped in packs.** Today's topics, questions, flashcards, exercises, notes and
  sample tables form the "Oracle SQL" pack, which both Oracle exams use. Items tagged for one exam
  keep that tag. An untagged item belongs to every exam of its own pack, never to another pack's
  exams. The content validator checks each exam against that exam's own database.
- G7. **Nothing breaks.**
  - Existing users keep their progress, chosen exam, mock history and practice schemas.
  - Existing deployments (Render, docker-compose, local dev) keep working with their current
    environment variables.
  - All current tests pass, adjusted only where they pin internals that this work replaces.

## Non-goals

- A PostgreSQL, MySQL or any second engine. Only the interface and the Oracle implementation get
  built.
- Moving the app's own storage (accounts, progress, notes, audit). It stays in Oracle or SQLite as
  today; the owner said "the app state can stay on oracle".
- Renaming the product. "Oracle Learning Lab" stays.
- New content, or rewording existing content.
- Separate progress per exam beyond what exists today. Progress is already filtered by exam.

## Anti-goals (a failure even if it technically works)

- A learner loses progress, their practice schema, or a half-done mock.
- An Oracle learner sees any change other than the picker: different questions, missing cards,
  different SQL results or error explanations.
- A deployment needs new or renamed environment variables to keep running.
- Adding an exam still means hunting for "1Z0-171" and "23ai" across the code.

## Constraints

- Same stack:
  - Python 3.12 standard library on the server, python-oracledb thin mode;
  - a vanilla-JS ES-module single-page app;
  - a strict Content Security Policy (no inline handlers, inline scripts only through the existing
    hash mechanism).
- The app's look and copy rules: plain sentence-case English, the existing design tokens, light
  and dark themes (dark is the default).
- Stored data stays readable without a migration:
  - `settings.exam` keeps the exam codes;
  - mocks keep their `exam` code;
  - practice-schema records keep their database keys "default" and "23ai".
- Environment variables keep their names: `STUDY_DSN`, `STUDY_DSN_23AI`, the `_23AI` suffix on
  the provisioner, gateway, tablespace and quota variables, and so on.

## The how, as decided

- **Placement:** the sidebar, where the switch is now (the owner picked mockup A).
- **Grouping:** by database product, for example "Oracle". A later "PostgreSQL" group appears
  without any front-end change.
- **Default:** 1Z0-071.
- **Engine scope:** the boundary covers learner-facing SQL only. App storage is out of scope.
- **What adding a PostgreSQL exam should mean later:** a content pack (question bank, flashcards,
  exercises, notes, sample tables), a registry entry, a PostgreSQL engine module and that
  database's connection settings. The engine module is new code; everything else is content and
  configuration.

## Builder's calls (made by me, not by the owner; flagged for review)

- **The drop-down is a custom listbox, not a native `<select>`.** A native select can't show the
  two-line items of mockup A.
  - It follows the ARIA "select-only combobox" pattern: arrow keys, Home/End, type-ahead,
    Enter/Space, Escape, and closing on an outside click.
  - The page's single-key shortcuts must not fire while it has focus.
  - The open list must not be clipped by the scrolling sidebar.
  - On narrow screens it works inside the drawer.
- **The registry keeps today's database keys.**
  - The registry maps 1Z0-071 to the database key "default" and 1Z0-171 to "23ai", so stored
    practice schemas and environment variables need no change.
  - Config reads one set of settings per database key named in the registry. The key "default" has
    no suffix; any other key uses its upper-cased name as the suffix ("23ai" gives `STUDY_DSN_23AI`).
    That derives today's variable names exactly, and a future key "pg16" gives `STUDY_DSN_PG16`.
- **A missing database falls back only within the same engine, and only where the registry says
  so.**
  - An exam may name a fallback database key; 1Z0-171 names "default", which reproduces today's
    behaviour (19c runs the 1Z0-171 SQL when no 23ai database is set).
  - A fallback to a database of another engine is refused when the app starts.
  - An exam with neither its own database nor a fallback stays selectable, and its SQL shows the
    existing "not set up" message. Admins fall back to the shared database of the same engine, as
    today.
- **The validator still picks exams by the database it's connected to.**
  - Each registry entry names the database versions its content is checked on: 1Z0-071 on Oracle
    below 23, 1Z0-171 on Oracle 23 and up.
  - `oracle-lab validate` checks every exam whose engine and version range match the connected
    database. That is exactly today's rule, so the CI 19c, 21c and 23ai jobs and the README's
    "point `STUDY_DSN` at 23ai to validate 1Z0-171" keep working unchanged.
  - An optional `--exam CODE` restricts the run to one exam.
- **Items that need a newer database than the learner has are derived from data.** Today the
  front end hard-codes "topic 15 needs Oracle 23". Instead, the server says per item which database
  version it needs, and the front end words it with the exam's database name.
- **Copy that names exams comes from the registry.** That covers the settings "About" text, the
  home links to the exam guide and cheat sheet, the database label, and the one-line description on
  the sign-in pages.
- **Notes belong to a content pack.** The notes list shows the current exam's pack. Today that is
  every note.
- **A test-only fake engine proves the boundary.** Tests register a second, fake engine and a fake
  exam to check that the registry, routing, picker data and validator handle more than Oracle.
  Nothing fake ships.
- **The sign-in pages' one-line description is filled in from the server's exam list.** The
  server exam list is the existing `/api/auth/config`. The static text stays as a fallback, so no
  inline script and no CSP change are needed.

## What's left to the builder

- Module and class names, and the exact shape of the engine interface, within G5.
- How the Oracle code is wrapped: thin adapters over today's modules are preferred to moving code
  around.
- The drop-down's exact visual details, within the app's style and mockup A.
- How the docs (README, docs/docker.md, AUTHORING.md) explain adding an exam. A short "Adding an
  exam" section is expected.

## How we'll know it worked

- In both themes and at phone, laptop and 23" widths, the drop-down shows both Oracle exams under
  "Oracle". Switching from 1Z0-071 to 1Z0-171 and back changes questions, cards, exercises, mocks,
  Today and the SQL database exactly as the switch did before. The same learner's progress is
  unchanged afterwards.
- The full test suite passes, including the Oracle 19c and 23ai validation runs.
- A test adds a fake engine and exam through the registry alone and sees them in the exam list, the
  routing and the validator.
- A search of the application code finds no "1Z0-071", "1Z0-171", "19c" or "23ai" outside these:
  - the registry, the Oracle engine and the Oracle content pack;
  - static fallback copy in the HTML.

  Tests, docs and deployment files are excluded; they may name the exams.
