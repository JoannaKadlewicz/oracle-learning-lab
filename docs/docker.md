## Run with Docker (no local Oracle needed)

Requires Docker with Compose v2. From the repository root:

    docker compose up -d --build        # first run downloads about 1.3 GB (Oracle XE 21c)
    docker compose logs -f app          # optional: watch it start

Open http://127.0.0.1:8071 when the log shows `Oracle Learning Lab: ...` (usually under a minute).

What it starts:

- `oracle`: Oracle Database XE 21c (`gvenzl/oracle-xe:21-slim-faststart`) with the learning
  user `ORASTUDY` in the PDB `XEPDB1`. Its port is not published, so it does not clash with
  another Oracle on port 1521; only the app container can reach it.
- `app`: Oracle Learning Lab. On start it waits for the database, creates the sample tables the
  first time (when `EMPLOYEES` does not exist yet), then serves on `127.0.0.1` only.

Your data survives `docker compose down` and restarts: the database, your progress
(`app/state`) and your saved notes (`app/notes/personal`) live in Docker volumes.
`docker compose down -v` deletes them and starts you from scratch.

Settings (environment variables or a `.env` file next to `docker-compose.yml`):

| Variable             | Default        | Meaning                                         |
|----------------------|----------------|-------------------------------------------------|
| `STUDY_PUBLISH_PORT` | `8071`         | Host port of the app (always bound to 127.0.0.1) |
| `STUDY_PASSWORD`     | `orastudy`     | Password of `ORASTUDY`, set on the first start   |
| `ORACLE_PASSWORD`    | `orastudy_sys` | Password of `SYS`/`SYSTEM`, set on the first start |

The passwords are applied only when the database volume is created; to change them later,
run `docker compose down -v` (this deletes your data) and start again.

Useful commands:

    docker compose ps                                  # status (oracle shows "healthy" when ready)
    docker compose down                                # stop, keep data
    docker compose up -d --build                       # update after pulling new code
    docker compose exec oracle sqlplus orastudy/orastudy@//localhost/XEPDB1   # SQL*Plus as ORASTUDY

"Reset sample data" in the app rebuilds the sample tables as usual.

## Oracle 23ai for the 1Z0-171 track

The app prepares for 1Z0-071 (19c) and 1Z0-171 (23ai); switch at the top of the menu. Topic 15
(SQL features new in 23ai) only runs on Oracle 23ai. To get a second database for it:

    STUDY_DSN_23AI=oracle23:1521/FREEPDB1 docker compose --profile 23ai up -d --build

This adds `oracle23` (`gvenzl/oracle-free:23-slim-faststart`, about 1 GB more) and the app then
switches the SQL lab, the exercises and the grader to it whenever the 1Z0-171 track is chosen.
Without the profile both tracks use XE 21c: quizzes and flashcards work, 23ai SQL does not run.

Without Docker, start any Oracle 23ai database and set `STUDY_DSN_23AI` (plus
`STUDY_USER_23AI` and `STUDY_PASSWORD_23AI` if they differ from the 19c user) before
`app/init_db.py` and `app/server.py`. The learning user needs CREATE SESSION, TABLE, VIEW,
SEQUENCE, SYNONYM and DOMAIN (see `docker/23ai-grants.sql`). A small `oracle-free` container
needs `processes` raised (for example `ALTER SYSTEM SET processes=600 SCOPE=SPFILE` and a
restart) before the content validator, which opens many short sessions, runs against it.

Oracle version note: the content was written and verified on Oracle 19c; Docker runs XE 21c.
A few things behave differently on 21c: `INTERSECT ALL`, `EXCEPT` and `EXCEPT ALL` / `MINUS ALL`
work (19c rejects them), and updating a non key-preserved table through a join can succeed or
raise ORA-30926 instead of ORA-01779. The exam targets 19c behaviour; trust the explanations.
The content checks know these differences (`try_error_since` in the content), so the validator
and the tests pass on both 19c and XE 21c.

## Continuous integration

`.github/workflows/ci.yml` runs on every push and pull request: it starts Oracle XE 21c as a
service container, installs `app/requirements-dev.txt`, runs the structure checks, creates the
sample schema with `app/init_db.py`, then runs `pytest` and the database content checks.
