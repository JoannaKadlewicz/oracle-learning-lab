# Running with Docker

One container runs **Oracle Database 19c Enterprise Edition** and the **Oracle Learning Lab** web
app together. The database files and your progress are kept in folders on the host.
Passwords are Docker secrets in `./secrets`. They are never in the image, the compose file or the
environment.

```
host                                     container "lab"  (FROM your oracle/database 19c image)
./secrets/oracle_pwd ─────────┐          ┌──────────────────────────────────────────────────────┐
./secrets/study_db_password ──┼─ /run/secrets/* ─►  entrypoint.sh (supervisor, PID 2 under tini) │
./secrets/study_auth_password ┘          │    ├─ runOracle.sh ── Oracle 19c  CDB ORCLCDB, PDB ORAPDB1
./data/oradata ◄── bind mount ──────────►│    │    └─ startup/01-provision-study-user.sh (ORASTUDY)
./data/app     ◄── bind mount ──────────►│    └─ oracle-lab init-db, then oracle-lab serve :8071 │
127.0.0.1:8071 ─────────────────────────►│  web app                                             │
127.0.0.1:1525 ─────────────────────────►│  listener :1521 (SQL Developer, SQLcl)               │
                                         └──────────────────────────────────────────────────────┘
```

## Prerequisites

1. Docker with Compose v2 and BuildKit (Docker 23 or later).
2. **An Oracle Database 19c base image.** Oracle publishes no pullable 19c image: you build it
   once from Oracle's official scripts, with the installation zip you download from Oracle
   (accepting its license):

       git clone https://github.com/oracle/docker-images
       cd docker-images/OracleDatabase/SingleInstance/dockerfiles
       cp ~/Downloads/LINUX.X64_193000_db_home.zip 19.3.0/
       ./buildContainerImage.sh -v 19.3.0 -e        # -> oracle/database:19.3.0-ee

   Put the tag in `.env` as `ORACLE_BASE_IMAGE` (the default is `oracledb:19.3.0`).
3. About 12 GB of disk for the image and the database, and 4 GB or more of RAM for the container.

## Start

    cp .env.example .env      # adjust if needed
    make up                   # = scripts/init-secrets.sh + docker compose up -d --build
    make logs                 # watch it start

The **first start creates the database, which takes 10–30 minutes** (`DATABASE IS READY TO USE!` in
the log). After that the entrypoint provisions `ORASTUDY`, creates the sample tables and starts the
app (`Oracle Learning Lab 2.0.0 on http://0.0.0.0:8071 ...`). Later starts take about a minute.
`make ps` shows `healthy` when both the database and the app are up.

Open http://127.0.0.1:8071 and log in as `study` with the password in
`secrets/study_auth_password`.

## Credentials

`make secrets` (`scripts/init-secrets.sh`) generates any missing secret and keeps the ones that exist:

| File | Used for | Read by |
|---|---|---|
| `secrets/oracle_pwd` | `SYS`, `SYSTEM`, `PDBADMIN` | the base image's `runOracle.sh` (`/run/secrets/oracle_pwd`) |
| `secrets/study_db_password` | the learning user `ORASTUDY` | `provision-study-user.sh` and the app (`STUDY_PASSWORD_FILE`) |
| `secrets/study_auth_password` | web login of user `study`; **empty file = no login** | the app (`STUDY_AUTH_PASSWORD_FILE`) |

The folder is `0700` (only you can open it on the host). The files are `0644`, because Oracle reads
them inside the container as uid 54321, and Compose cannot change the owner of file secrets.
`secrets/`, `data/` and `.env` are in `.gitignore` and `.dockerignore`.

**Rotating the ORASTUDY password:** delete or edit `secrets/study_db_password` and run
`docker compose restart lab`. The startup script runs `ALTER USER` on every start, so the database
and the app always agree. (`oracle_pwd` is applied only when the database is created.)

## Data on the host

| Host folder (`DATA_DIR`, default `./data`) | Container | Content |
|---|---|---|
| `data/oradata` | `/opt/oracle/oradata` | datafiles, control files, spfile, password file |
| `data/app` | `/var/lib/oracle-lab` | `progress.json`, `notes/` (SQL notes you saved) |

The one-shot `prepare-data` service creates these folders and gives them to uid 54321 before the
database starts. `docker compose down -v` does **not** delete them. To start from scratch, stop the
stack and remove `data/oradata` (database) or `data/app` (progress).

To back up, run `docker compose stop lab` (the database shuts down cleanly) and copy `data/`.

## Settings (`.env`)

| Variable | Default | Meaning |
|---|---|---|
| `ORACLE_BASE_IMAGE` | `oracledb:19.3.0` | Your 19c base image |
| `DATA_DIR` | `./data` | Host folder for database and app data |
| `LAB_PORT` | `8071` | Host port of the app (bound to 127.0.0.1) |
| `ORACLE_PORT` | `1525` | Host port of the listener (bound to 127.0.0.1) |
| `ORACLE_SGA_MB`, `ORACLE_PGA_MB` | Oracle's choice | Memory of the database, at creation |
| `STUDY_DSN_23AI` | – | `oracle23:1521/FREEPDB1` with the `23ai` profile |
| `STUDY_LOG_LEVEL` | `INFO` | App log level |

Every app setting is listed in [`src/oracle_lab/config.py`](../src/oracle_lab/config.py).

## Everyday commands

    make ps                   # status and health
    make logs                 # follow the log
    make down                 # stop (data is kept)
    make up                   # update after pulling new code
    make sqlplus              # SQL*Plus as ORASTUDY inside the container
    sql orastudy@//127.0.0.1:1525/ORAPDB1     # SQLcl / SQL Developer from the host

## How the container runs

- **tini** (`init: true`) is PID 1, so signals are forwarded and the processes Oracle leaves behind
  are reaped.
- **`entrypoint.sh`** starts `runOracle.sh` in the background and waits for `checkDBStatus.sh`,
  however long the first creation takes. It then runs `oracle-lab init-db` and starts
  `oracle-lab serve`. If either process exits, it stops the other one and exits non-zero, and
  `restart: unless-stopped` brings the whole container back.
- **`docker stop`** stops the app first, then the database runs `SHUTDOWN IMMEDIATE`.
  `stop_grace_period: 3m` gives it time to do so.
- The **health check** passes when the database is open *and* the app answers on `/healthz`.
- The Python runtime is a standalone CPython 3.14 build (installed with `uv`), because Oracle Linux 7
  has no modern Python. The app runs as the `oracle` user from `/opt/oracle-lab/venv`.

## Oracle 23ai for the 1Z0-171 track

    echo "STUDY_DSN_23AI=oracle23:1521/FREEPDB1" >> .env
    docker compose --profile 23ai up -d

This adds `oracle23` (`gvenzl/oracle-free:23-slim-faststart`, about 1 GB). It uses the same secrets
and stores its files in `data/oradata-23ai`. While the 1Z0-171 track is chosen, the SQL lab, the
exercises and the grader use it. The validator opens many short sessions, so raise `processes` on
it before running the validator: `ALTER SYSTEM SET processes=600 SCOPE=SPFILE`, then restart.

## Only the app (external database)

[`docker/app.Dockerfile`](../docker/app.Dockerfile) builds a small image without Oracle, for a
database that runs elsewhere (used by [`render.yaml`](../render.yaml)):

    docker build -f docker/app.Dockerfile -t oracle-learning-lab-app .
    docker run --rm -p 127.0.0.1:8071:8071 -e STUDY_DSN=db.example.com:1521/ORAPDB1 \
      -e STUDY_PASSWORD_FILE=/run/secrets/db -v "$PWD/secrets/study_db_password:/run/secrets/db:ro" \
      oracle-learning-lab-app

### Progress in the database (no persistent disk)

Hosts like Render's free plan wipe the container's files on every deploy and restart. Set
`STUDY_STATE_USER` (and `STUDY_STATE_PASSWORD[_FILE]`) and the app keeps progress and saved notes
in that user's tables, `LAB_STATE` and `LAB_NOTES`, instead of `progress.json` and `notes/`.
`oracle-lab init-db` creates them on first start. Use a user of its own, not the learning user:
the SQL lab runs whatever you type as ORASTUDY, and one `DROP TABLE` would take your progress
with it. `STUDY_STATE_DSN` defaults to `STUDY_DSN`, so both users can share one database.

### Render with an Always Free Autonomous Database

1. In Oracle Cloud, create an Autonomous Database (19c, or 23ai for the 1Z0-171 track). Under
   Network, allow access from everywhere (or from Render's outbound addresses) and turn off
   "Require mutual TLS"; then copy a TLS connect string (the `_low` service is enough).
2. Connect as `ADMIN` (Database Actions, SQL) and create the two users:

       CREATE USER orastudy IDENTIFIED BY "<password 1>" DEFAULT TABLESPACE data QUOTA 100M ON data;
       GRANT CREATE SESSION, CREATE TABLE, CREATE VIEW, CREATE SEQUENCE, CREATE SYNONYM TO orastudy;
       -- 23ai only: GRANT CREATE DOMAIN, CREATE PROCEDURE TO orastudy;
       CREATE USER oralab_app IDENTIFIED BY "<password 2>" DEFAULT TABLESPACE data QUOTA 20M ON data;
       GRANT CREATE SESSION, CREATE TABLE TO oralab_app;

3. In Render, New > Blueprint, pick this repository. It reads [`render.yaml`](../render.yaml) and
   asks for `STUDY_DSN` (the connect string), `STUDY_PASSWORD` (password 1) and
   `STUDY_STATE_PASSWORD` (password 2). The web login is `study`; its generated password is under
   the service's Environment tab.

A free Render service sleeps after a while without visits, so the first page takes a moment to
load. An Always Free database that nobody uses for 7 days is stopped by Oracle; start it again in
the cloud console.

## Oracle version note

The content was written and verified on Oracle 19c, which this image runs. CI also runs it on
XE 21c, where a few things differ: `INTERSECT ALL`, `EXCEPT` and `MINUS ALL` work, and updating a
non key-preserved join view can raise ORA-30926 instead of ORA-01779. The content records these
differences (`try_error_since`), so the checks pass on both.
