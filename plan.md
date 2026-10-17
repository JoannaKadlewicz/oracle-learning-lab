# Plan: Make Oracle Learning Lab the Best Way to Pass 1Z0-071

## Where the app stands today

The engine is already good: practice and timed quizzes, Leitner flashcards, auto-graded SQL
exercises against a live Oracle 19c schema, a SQL lab with a careful SQL*Plus-style splitter,
a mistakes list, notes, and light and dark themes. No other study app grades your SQL against
a real database. That is the advantage to build on.

The weak spots are content depth, how mastery is measured, and how much proof the app shows you:

| Area | Today | Problem |
|---|---|---|
| Questions | 79 (71 single-answer, 8 "choose two") | Too few for repeated mocks. The real exam relies heavily on "choose two/three" items. |
| Mock exam | 63 questions drawn from 79 | Each mock repeats about 80% of the previous one, so scores go up from memory, not skill. |
| Exercises | 13, covering 7 of 14 topics | No graded labs for basic SELECT, DML, DDL, views, dictionary, privileges or time zones. The grader only accepts SELECT. |
| Hints | `lab.hint` is rendered by the UI | Only 2 exercises define a hint. |
| Mistakes | One correct answer clears a mistake | A lucky guess hides a real gap. |
| Progress | Last-answer correctness per question | No sense of "am I ready?", no trend, no confidence calibration. |
| Objectives | 14 home-made topics | Not yet checked against Oracle's official 1Z0-071 objective list. |
| Notes | 1 topic of 14 | The Notes page is mostly empty. |
| Quality | No tests | The splitter and grader are subtle code with no safety net. |

## Guiding principles

1. **The database is the source of truth.** Every answer that can be computed by running SQL is
   computed by running SQL, so content can never silently drift from Oracle's behavior.
2. **Measure skill, not memory.** No repeated mocks, confidence ratings, spaced re-testing of mistakes.
3. **Every claim of readiness is backed by evidence** the app can show.
4. **Original material only.** No exam dumps.

---

## Phase 0: Foundations (do first, small)

Goal: make large content growth safe.

- [x] **Verify objectives.** Mapped to the 16 official sections and 60 objectives in
      `app/content/objectives.py`. Oracle's own page did not load, so the list comes from a
      third-party restatement of Oracle's exam guide; re-check against Oracle when possible.
      Same source: 63 questions, 120 minutes, 63% to pass, no published section weights.
      The front end now reads this format from the server instead of hard-coding it.
- [x] **Objective IDs.** Every question, card and lab has an `objective` (for example `"6.2"`).
      Flashcards are now dicts with explicit, stable IDs (`c000`…), so progress survives reordering.
- [x] **Content validator** (`app/validate_content.py`): unique IDs, valid topic and objective,
      answer indexes, "which two/three" matching the answer count, unknown fields; every `try_sql`
      runs or raises exactly its declared `try_error`; every lab solution runs, returns rows and
      returns the named columns. `--coverage` prints items per objective, `--reset` resets the data first.
- [x] **Tests** (`app/tests`, 36 tests): `split_statements`, grading (`compare_results`, pulled out
      of `grade`), value formatting, content validity and validator fault detection, plus a
      database run of the validator that skips when Oracle is down.
- [x] **Split `content.py`** into `app/content/`, one module per topic.

**Found by the validator, to fix in Phase 1:** objectives 1.1–1.3 (relational concepts),
3.4 (DEFINE and VERIFY) and 5.4 (nesting functions) have no material at all, and 50 of 60
objectives have no graded lab.

## Phase 1: Content depth (the biggest single lever)

Goal: enough material that a passing mock score means something.

**Done:**
- [x] **Questions: 79 → 453**, 27–39 per topic, 39% "choose two/three". 254 of them are checked
      against the database on every validator run (`answer_sql`, `equivalent_sql`, `try_error`).
- [x] **New question types**, database-verified where possible: predict the output (`answer_sql`),
      which error (`try_error`), which statements are true, and which queries are equivalent
      (`equivalent_sql`: the validator runs every option).
- [x] **Exercises: 13 → 116**, covering all 14 topics: 79 query, 14 DML and 23 DDL labs, all with
      `hint` and `hint2`. DML labs run in a rolled-back transaction and reject COMMIT and DDL; DDL labs
      are graded over the data dictionary and drop their `LAB_` objects afterwards.
- [x] **Richer seed data**: `events` (time zones with regions, LOCAL TIME ZONE, both INTERVAL types,
      a DST and a 29 February case) and `promotions` (always empty). Existing rows unchanged, so no
      existing answer changed. NULLs in join keys, ties, a hierarchy and month-end dates already existed.
- [x] **Notes for all 14 topics**, each with "Common traps" and "Oracle vs. standard SQL".
      Each note says which examples were executed and which come from documentation only.
- [x] **Fetching fix**: time zone columns are converted to text on the server, because thin-mode
      python-oracledb cannot fetch region-based TIMESTAMP WITH TIME ZONE values (DPY-3022).
- [x] **Safety**: the app, grader and validator block `ALTER USER` (an authoring agent changed the
      ORASTUDY password by accident and locked the account).

**Errors found by executing content** (all fixed): (+) inside an ANSI ON clause is accepted by 19c,
not ORA-25156; UPDATE on USER_TABLES is ORA-02030; TRUNCATE of a parent with an empty child succeeds;
a DDL rejected for a syntax error does not commit; several wrong ORA- codes in topic 10;
q07-all-empty asked for a row count of a COUNT(*) query; USER_ views can have an OWNER column;
DROP VIEW has CASCADE CONSTRAINTS.

**Still open:**
- [ ] Review the notes of topics 1–8 by execution, as was done for 9–14.
- [ ] Topic 13 (privileges) is mostly conceptual: ORASTUDY cannot create users or roles, so revoke
      cascading, roles and CREATE SESSION are stated from documentation. A second schema would make
      them executable.
- [ ] Topic weighting: Oracle publishes no section weights, so question counts per topic are even.

## Phase 2: A learning engine that finds your real gaps

The engine is `app/engine.py`: pure functions over the saved progress, covered by
`app/tests/test_engine.py`. The browser only displays what `/api/progress` returns.

- [x] **Confidence rating.** Practice answers are checked with Sure / Think so / Guessing
      (keys S, T, G); exam mode has an optional rating. The Progress page shows calibration:
      how often you are right per rating, with "Sure" expected at 90% or more.
- [x] **Mistakes need proof to clear.** Wrong answers and lucky guesses stay open until
      confident correct answers on 2 different days. Confident mistakes come first.
- [ ] **Misconception tracking.** Not started: it needs a content pass that tags the wrong
      options of all 453 questions with the misconception they represent.
- [x] **Mastery per objective.** Beta(1,1) estimate from quiz answers (weighted by confidence),
      flashcards and lab results, with a 30-day half-life. Levels: Not started, Weak, Learning, Strong.
- [x] **Better spacing.** SM-2 for flashcards (Again / Good / Easy) and for questions
      (a correct guess is a lapse, a confident miss resets hardest).
- [x] **Daily plan.** Exam date and minutes per day on the Overview; today's session holds due
      cards, a lab from the weakest objective and practice questions, plus pacing advice.
- [x] **Interleaving.** Practice questions are picked by the engine (open mistakes, due reviews,
      weakest objectives) and ordered so the same objective does not repeat back to back.
- Also: the server now scores answers itself instead of trusting the browser, and every answer
  records whether it was given in practice or exam mode (needed for Phase 3).

## Phase 3: Exam simulation you can trust

Mock exams live on the server (`state["mocks"]`), so the deadline is enforced there, a reload
resumes a running mock, and a mock left open past its deadline is submitted automatically.
Logic in `app/engine.py` (`build_mock`, `mock_report`, `readiness`), tests in `app/tests/test_mocks.py`.

- [x] **Exam-faithful mocks**: 63 questions in 120 minutes, one question per official objective
      first (Oracle publishes no section weights), flag for review, optional confidence rating,
      a review screen listing unanswered and flagged questions, and no feedback until the end.
      Timed sets on chosen topics use the same machinery.
- [x] **No question reuse across mocks**: never-seen questions first, then practice-only ones, then
      questions from the oldest mock. Each report states how many questions were new to you and
      your score on those; history shows the score on new questions next to the overall one.
- [x] **Separate exam history from practice history**: every answer records its mode, and the
      Progress page lists mock exams with their reports.
- [x] **Post-mock analytics**: score per exam section, single- vs. multi-answer accuracy, answers
      changed right to wrong / wrong to right (linked to the questions), time used, the slowest
      questions, and accuracy per confidence rating.
- [x] **Readiness estimate**: chance to pass and a 10th–90th percentile score range, from the
      first answer ever given to each question (mock answers count fully, practice 60%, 30-day
      half-life), as a beta-binomial over a 63-question exam. Repeated practice cannot inflate it.
      Shown on the Overview, the Progress page and after every mock, with weak objectives listed.

Decisions: unanswered questions score zero in the mock report but are not recorded as answers,
so submitting an unfinished mock does not flood the mistakes list or sink readiness. Abandoning
a mock is not scored, but its questions count as seen.

## Phase 4: An SQL lab that teaches

- [x] **Real editor**: CodeMirror 5 (not 6: version 5 is a few plain scripts on cdnjs, version 6 needs an
      ES module build) with Oracle SQL highlighting, line numbers, bracket matching and closing,
      autocomplete of tables and columns (Ctrl+Space, or after typing an alias and a dot), and
      Run selection. Used in the SQL lab and in exercises; falls back to a text area offline.
- [x] **Explain-the-error** (`app/errors.py`): 60 ORA- codes with an explanation and a link to the
      topic's notes, plus hints about *your* statement: an alias used in WHERE/GROUP BY, the closest
      real column or table name, the column missing from GROUP BY, the table an ambiguous column
      appears in, AS before a table alias, and the parent table, unique columns or CHECK condition
      behind a constraint error. Shown in the SQL lab and when an exercise answer fails to run.
- [x] **Visual result diffs**: a failed exercise shows one table with rows marked correct, not
      expected, missing, wrong position, or wrong value (yours → expected per cell). NULL is shown
      as null; leading and trailing spaces are made visible.
- [x] **DML before/after view**: inserted, deleted and updated rows (only the key and changed
      columns, old → new) for single-table DML, plus the transaction state after every statement:
      uncommitted row changes, savepoints, and a warning when DDL commits pending changes.
- [x] **Join and set-operator visualizer** (`app/sqlviz.py`): for a join of two tables, every row of
      each table marked matched (with its partner count), kept with NULLs, or dropped; hover a row
      to see its partners. For UNION / UNION ALL / INTERSECT / MINUS, each distinct row with its
      count in each query and in the result.
- [x] **Query history** (last 100 runs, saved with your progress) with one-click reload, and
      **Save as note**, which writes the SQL to `app/notes/personal/` and lists it on the Notes page.

## Phase 5: Show that you are the best

**Inside the app:**
- [x] **Readiness dashboard** (Progress page): a "ready to book the exam" checklist (the definition
      of done below), pass chance with a score range, study streak, estimated hours studied, how
      often "Sure" is right, the mock score trend (overall and on new questions) with a crosshair
      tooltip, a heatmap of the 60 objectives, a 12-week activity calendar. Chart colours were
      checked with the data-viz palette validator for both light and dark themes.
- [x] **Evidence-based badges** (`engine.badges`): 10 badges, each with visible progress, e.g.
      "Clean run" (25 correct, none guessed, over 3+ days), "Schema builder" (every DDL exercise
      passed without opening the solution; solution views are now recorded), "Exam ready"
      (3 full mocks at 80%+ on new questions, 3+ days apart).
- [x] **Readiness report** at `/report` (`app/report.py`): one self-contained page that prints to
      a two-page PDF in a light theme.

**As a portfolio project:**
- [x] **One-command setup**: `docker compose up -d --build` with Oracle XE 21c
      (`gvenzl/oracle-xe:21-slim-faststart`; Oracle Free 23ai differs more from 19c) and the app;
      `app/init_db.py` waits for the database and creates the schema once. Tested end to end:
      about 35 s to a working app after the image download, data survives restarts.
- [x] **CI** (`.github/workflows/ci.yml`): pytest and the content validator against XE 21c. Two
      items behave differently on 21c (ORA-30926 instead of ORA-01427 / ORA-01779); content can
      now state per-version errors (`try_error_since`), and the explanations mention the difference.
      The full suite passes on 19c and on 21c in Docker. Not yet run on GitHub: there is no
      repository yet.
- [x] **README with screenshots** (`docs/screenshots/`, from a simulated history made by
      `app/demo.py`). No animated GIF: no tool to assemble one is installed here.
- [x] **Write-ups**: `docs/articles/grading-sql-against-a-real-database.md` and
      `docs/articles/measuring-readiness-without-fooling-yourself.md`.

## Phase 6 (optional): AI tutor using the Claude API

`app/tutor.py`, default model `claude-opus-5-5` with server-side refusal fallbacks. Off unless the
`anthropic` package and credentials are present; everything else works without it.

- [x] **"Why was I wrong?"** on wrong or guessed practice answers: Claude gets the question, the
      verified answer and explanation, your choice and your confidence.
- [x] **Hint on failed exercises**: Claude gets your SQL, the real error with the app's own hint
      or the row diff, and the relevant schema, and is told never to show the solution.
- [x] **Question generator with a database check**: structured JSON drafts go through the same
      validator as hand-written content; drafts the database does not confirm are rejected with
      the reason, the rest wait in a review queue, and only accepted ones are added
      (`app/content/generated.json`).
- Tested with a fake client (prompts, API parameters, refusals, the generate–verify–accept
  pipeline against the real database). **Not tested against the live API**: no API key here.

**Still open across phases:** misconception tagging (Phase 2), reviewing the notes of topics 1–8
by execution, making privileges (topic 13) executable with a second schema, and running CI on GitHub.

---

## Suggested order and size

| Step | Phase | Effort | Why now |
|---|---|---|---|
| 1 | 0: validator, tests, objective IDs, content split | 1–2 days | Makes everything after it safe |
| 2 | 3: no reuse across mocks, separate exam history | 0.5 day | Today's mock scores are misleading |
| 3 | 2: confidence rating + stricter mistake clearing | 1 day | Cheap, big effect on honest measurement |
| 4 | 1: questions to 350+, DML/DDL graded labs, seed data | ongoing, 1–2 weeks | The biggest lever on actually passing |
| 5 | 4: CodeMirror, ORA- explanations, result diffs | 2–3 days | Makes daily practice faster and clearer |
| 6 | 2 + 3: mastery model, readiness estimate | 2 days | Needs the bigger content pool first |
| 7 | 5: dashboard, report, Docker, CI, README | 2–3 days | The showcase |
| 8 | 6: Claude tutor and generator | 2 days | Optional extra |

## Definition of done: "ready to book the exam"

- Every official objective is green in the mastery heatmap.
- Three uncontaminated mocks at or above 80%, at least 3 days apart.
- Calibration: when you say "Sure", you are right at least 90% of the time.
- Every lab passed, and the DML/DDL labs passed without the solution being shown.
