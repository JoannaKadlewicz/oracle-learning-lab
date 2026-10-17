# Oracle Learning Lab (1Z0-071)

A local web app for the **Oracle Database SQL Certified Associate (1Z0-071)** exam that grades your
SQL against a real Oracle database and measures your readiness without letting you fool yourself.

![Overview with today's study plan](docs/screenshots/overview.png)

## What makes it different

- **Answers are checked by Oracle, not by memory.** 453 original practice questions, 254 of them
  verified on every run by executing SQL: the correct option must equal the query result, the
  error a statement raises must be the stated ORA- code, and the options of "which queries are
  equivalent" questions are executed and compared. Running the content this way caught real
  factual errors that had been written with confidence (listed in [plan.md](plan.md)).
- **116 graded SQL exercises**: queries graded on their rows, DML graded on the resulting table
  state inside a rolled-back transaction, and DDL graded over the data dictionary.
- **Honest readiness**: the pass estimate uses only the *first* answer you ever gave to each
  question, mock exams prefer questions you have never seen and report your score on those,
  and a correct guess counts as a gap until you prove it on two different days.
- **An SQL lab that teaches**: plain-language explanations of 61 Oracle errors with a hint about
  *your* statement, before/after views of DML with transaction state and savepoints, and a
  visualizer that shows which rows a join matched, kept with NULLs, or dropped.

| | |
|---|---|
| ![Readiness dashboard](docs/screenshots/dashboard.png) | ![Mock exam report](docs/screenshots/mock-report.png) |
| Readiness dashboard: checklist, pass chance, trend, objective map, badges | Mock exam report: sections, answer changes, timing, confidence |
| ![Exercise diff](docs/screenshots/exercise-diff.png) | ![Join visualizer](docs/screenshots/join-visualizer.png) |
| A failed exercise compared row by row with the expected result | Which rows an outer join matched, kept with NULLs, or dropped |
| ![Error explained](docs/screenshots/error-explained.png) | ![Quiz with confidence](docs/screenshots/quiz.png) |
| An Oracle error explained, with a hint about the statement | Checking an answer by saying how sure you are |

Screenshots use a simulated study history (`app/demo.py`). The printable readiness report is
shown in [docs/screenshots/readiness-report.png](docs/screenshots/readiness-report.png).

## Quick start with Docker

Needs Docker with Compose v2; no local Oracle installation.

    docker compose up -d --build        # first run downloads about 1.3 GB (Oracle XE 21c)

Open http://127.0.0.1:8071 when `docker compose logs app` shows `Oracle Learning Lab: ...`
(usually under a minute). Details, settings and data persistence: [docs/docker.md](docs/docker.md).

## Run against your own Oracle database

Requirements: Python 3 (tested with 3.14), Oracle Database 19c (the content targets 19c; XE 21c also passes all
checks), and a learning user with CREATE SESSION, TABLE, VIEW, SEQUENCE and SYNONYM.

    python -m venv .venv
    .venv/bin/pip install -r app/requirements.txt
    .venv/bin/python app/init_db.py     # once: creates the sample tables if they are missing
    .venv/bin/python app/server.py      # then open http://127.0.0.1:8071

The server listens on 127.0.0.1 only: the SQL lab runs any SQL you type. Settings:

| Variable | Default | Meaning |
|---|---|---|
| `STUDY_DSN` | `localhost:1521/ORAPDB1` | Database to connect to |
| `STUDY_USER` | `orastudy` | Learning user |
| `STUDY_PASSWORD` | – | Its password (otherwise read from `STUDY_PASSWORD_FILE`) |
| `STUDY_PASSWORD_FILE` | `~/.orastudy_pwd` | File holding the password |
| `STUDY_HOST`, `STUDY_PORT` | `127.0.0.1`, `8071` | Where the app listens |
| `STUDY_STATE_FILE` | `app/state/progress.json` | Where your progress is saved |

## Features

- **Quiz**: practice with immediate explanations, or timed mock exams (63 questions, 120 minutes,
  one question per official objective first, review screen before submitting).
- **Confidence and calibration**: rate each answer Sure / Think so / Guessing (keys S, T, G);
  the app tracks how often you are right when you are sure.
- **Learning engine** (`app/engine.py`): SM-2 spacing for flashcards and questions, mistakes that
  need confident correct answers on two days, mastery per official objective, interleaved
  practice, and a daily plan sized to your exam date and study time.
- **Readiness**: pass probability with a score range, a "ready to book" checklist, mock trend,
  objective heatmap, study streak and hours, evidence-based badges, and a printable
  readiness report at `/report`.
- **Exercises**: query, DML and DDL exercises with two levels of hints and a row-by-row diff.
- **SQL lab**: CodeMirror editor with Oracle SQL highlighting and table/column autocomplete,
  run selection, error explanations, DML before/after, join and set-operator visualizer,
  query history, and "save as note".
- **Notes** for all 14 topics, with common traps and Oracle vs. standard SQL.
- **Optional AI tutor** (Claude), see below.

## Optional AI tutor

With the Claude API configured, the app can explain why a quiz answer was wrong, give a hint
(never the solution) for a failed exercise, and draft new questions. Drafts are run against your
database like all other content: only drafts whose answer Oracle confirms reach a review queue,
and only questions you accept join the question bank (`app/content/generated.json`).

    .venv/bin/pip install -r app/requirements-ai.txt
    export ANTHROPIC_API_KEY=...        # or run `ant auth login`
    .venv/bin/python app/server.py

It uses `claude-opus-5-5` (`STUDY_TUTOR_MODEL` to change it, `STUDY_TUTOR=off` to disable it).
Everything else works without it.

## Develop

    .venv/bin/pip install -r app/requirements-dev.txt
    .venv/bin/python -m pytest app/tests                   # database tests skip if Oracle is down
    .venv/bin/python app/validate_content.py --coverage    # check all content against the database
    .venv/bin/python app/demo.py /tmp/demo.json            # simulated progress for screenshots
    STUDY_STATE_FILE=/tmp/demo.json .venv/bin/python app/server.py

How to write questions, flashcards and exercises: [app/content/AUTHORING.md](app/content/AUTHORING.md).
CI ([.github/workflows/ci.yml](.github/workflows/ci.yml)) runs the tests and the content checks
against Oracle XE 21c.

    app/
    ├── server.py           HTTP server, SQL execution, grading
    ├── engine.py           spacing, mistakes, mastery, readiness, mock exams, badges
    ├── errors.py           explanations and hints for Oracle errors
    ├── sqlviz.py           join and set-operator visualizer
    ├── sqltext.py          light SQL text analysis used by both
    ├── report.py           printable readiness report
    ├── tutor.py            optional Claude tutor
    ├── validate_content.py checks content structure and runs it against the database
    ├── init_db.py          waits for the database and creates the sample schema once
    ├── demo.py             simulated study history
    ├── content/            questions, flashcards, exercises (one module per topic), objectives
    ├── sql/                sample schema create, seed and cleanup scripts
    ├── notes/              study notes; notes/personal holds your saved SQL notes
    ├── static/             front end (index.html, app.js, app.css)
    ├── state/              your progress (progress.json)
    └── tests/              pytest suite

## Articles

- [Grading SQL against a real database](docs/articles/grading-sql-against-a-real-database.md)
- [Measuring exam readiness without fooling yourself](docs/articles/measuring-readiness-without-fooling-yourself.md)

The roadmap and what is still open are in [plan.md](plan.md). All questions are original
practice material written for this project, not real exam questions.
