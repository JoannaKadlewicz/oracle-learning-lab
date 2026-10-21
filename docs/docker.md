# Running with Docker

One container runs **Oracle Database 19c Enterprise Edition** and the **Oracle Learning Lab** web
app together. The database files and your progress are kept in folders on the host.
Passwords are Docker secrets in `./secrets`. They are never in the image, the compose file or the
environment.

```
host                                     container "lab"  (FROM your oracle/database 19c image)
./secrets/oracle_pwd ─────────┐          ┌──────────────────────────────────────────────────────┐
./secrets/study_db_password ──┼─ /run/secrets/* ─►  entrypoint.sh (supervisor, PID 2 under tini) │
./secrets/provisioner_password ┤
./secrets/gateway_password ───┘          │    ├─ runOracle.sh ── Oracle 19c  CDB ORCLCDB, PDB ORAPDB1
./data/oradata ◄── bind mount ──────────►│    │    └─ startup/: ORASTUDY, OLL_PROVISIONER, OLL_GATEWAY
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
the log). After that the startup scripts provision `ORASTUDY`, `OLL_PROVISIONER` and `OLL_GATEWAY`, the entrypoint creates the sample tables and starts the
app (`Oracle Learning Lab 2.0.0 on http://0.0.0.0:8071 ...`). Later starts take about a minute.
`make ps` shows `healthy` when both the database and the app are up.

Open http://127.0.0.1:8071; you are sent to the sign-in page. Register the first account there
(it is a learner; see [Accounts and Google sign-in](#accounts-and-google-sign-in) for the administrator).
The two provisioning scripts run on every start, so an existing database from an earlier version
gets the new users on the next `make up`; no data is touched.

## Credentials

`make secrets` (`scripts/init-secrets.sh`) generates any missing secret and keeps the ones that exist:

| File | Used for | Read by |
|---|---|---|
| `secrets/oracle_pwd` | `SYS`, `SYSTEM`, `PDBADMIN` | the base image's `runOracle.sh` (`/run/secrets/oracle_pwd`) |
| `secrets/study_db_password` | the learning user `ORASTUDY` | `provision-study-user.sh` and the app (`STUDY_PASSWORD_FILE`) |
| `secrets/provisioner_password` | `OLL_PROVISIONER`, which creates and drops the practice schemas | `provision-practice-users.sh` and the app (`STUDY_PROVISIONER_PASSWORD_FILE`) |
| `secrets/gateway_password` | `OLL_GATEWAY`, the proxy user the app connects through | `provision-practice-users.sh` and the app (`STUDY_GATEWAY_PASSWORD_FILE`) |

The folder is `0700` (only you can open it on the host). The files are `0644`, because Oracle reads
them inside the container as uid 54321, and Compose cannot change the owner of file secrets.
`secrets/`, `data/` and `.env` are in `.gitignore` and `.dockerignore`.

An old `secrets/study_auth_password` is no longer used (the web login is now per user); you can delete it.

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
| `STUDY_PUBLIC_URL` | `http://localhost:8071` | Address users open the app at (also the base of the Google redirect URI) |
| `STUDY_ADMIN_EMAIL` | – | Account that becomes administrator |
| `STUDY_GOOGLE_CLIENT_ID`, `STUDY_GOOGLE_CLIENT_SECRET` | – | Turn on "Sign in with Google" |

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
   asks for `STUDY_DSN` (the connect string), `STUDY_PASSWORD` (password 1),
   `STUDY_STATE_PASSWORD` (password 2) and the account settings described in the next section.

A free Render service sleeps after a while without visits, so the first page takes a moment to
load. An Always Free database that nobody uses for 7 days is stopped by Oracle; start it again in
the cloud console.

## Accounts and Google sign-in

Every visitor has an account (e-mail and password, or Google). Progress, notes and SQL history are
per user, and each user gets a private **practice schema** `OLL_U...` in the database with its own
copy of the sample tables, so a `DROP TABLE` in the SQL lab only affects that user. Two Oracle users
make this work. Learner schemas have no password (`NO AUTHENTICATION`); the app reaches them by
proxy authentication through the gateway.

| Oracle user | Rights | Setting |
|---|---|---|
| provisioner (`OLL_PROVISIONER` locally, `ADMIN` on Autonomous) | creates, sizes and drops the practice schemas and the profile `OLL_LEARNER` | `STUDY_PROVISIONER_USER`, `STUDY_PROVISIONER_PASSWORD[_FILE]` |
| gateway (`OLL_GATEWAY`) | `CREATE SESSION` only | `STUDY_GATEWAY_USER`, `STUDY_GATEWAY_PASSWORD[_FILE]` |

Without both, the app still works but everyone shares the `ORASTUDY` schema. Locally the all-in-one
container creates both users itself on every start. The 23ai container does the same through
`docker/23ai-start/`, which the image runs after each start, so an existing 23ai database gets them
too.

| Variable | Default | Meaning |
|---|---|---|
| `STUDY_PUBLIC_URL` | `http://HOST:PORT` | Address users open the app at; `https://` turns on secure cookies |
| `STUDY_TRUST_PROXY` | off | `1` behind a reverse proxy such as Render's, so `X-Forwarded-For` is believed |
| `STUDY_ADMIN_EMAIL`, `STUDY_ADMIN_PASSWORD[_FILE]` | – | The account with this e-mail is the administrator; the password is its initial one |
| `STUDY_GOOGLE_CLIENT_ID`, `STUDY_GOOGLE_CLIENT_SECRET[_FILE]` | – | Both together turn on "Sign in with Google" |
| `STUDY_REGISTRATION` | `open` | `closed` stops new sign-ups |
| `STUDY_MAX_USERS` | `25` | Cap on accounts |
| `STUDY_PRACTICE_TABLESPACE`, `STUDY_PRACTICE_QUOTA_MB` | `USERS`, `50` | Where practice schemas live and their quota (`DATA` on Autonomous) |

The `*_23AI` variants of the provisioner, gateway and practice settings apply to `STUDY_DSN_23AI`.
In `docker-compose.yml` set `STUDY_ADMIN_EMAIL`, `STUDY_PUBLIC_URL` and `STUDY_GOOGLE_CLIENT_ID` in
`.env`. The Google client secret goes into the file `secrets/google_client_secret`, which
`make secrets` creates empty (an empty file leaves Google sign-in off); it is mounted like the other
secrets, never put in the environment.

**The first administrator.** Set `STUDY_ADMIN_EMAIL` and register with that e-mail (or sign in with
Google using it). Without it, the first account that registers is the administrator. The last
administrator cannot be deleted or demoted.

**Google sign-in.**

1. In the [Google Cloud Console](https://console.cloud.google.com/) pick or create a project, open
   APIs & Services > OAuth consent screen and configure it (External, your e-mail as contact).
2. Under Credentials choose Create credentials > OAuth client ID, application type
   **Web application**.
3. Add the authorized redirect URI `<STUDY_PUBLIC_URL>/auth/google/callback`, for example
   `http://localhost:8071/auth/google/callback` locally or
   `https://oracle-learning-lab.onrender.com/auth/google/callback` on Render. It must match exactly.
4. Put the client ID in `STUDY_GOOGLE_CLIENT_ID` and the client secret in `STUDY_GOOGLE_CLIENT_SECRET`
   (locally: the file `secrets/google_client_secret`).

**Autonomous Database.** `ADMIN` is the provisioner, so only the gateway has to be created (as
`ADMIN`, in Database Actions):

    CREATE USER oll_gateway IDENTIFIED BY "<password>";
    GRANT CREATE SESSION TO oll_gateway;

Then set `STUDY_PROVISIONER_USER=ADMIN` with ADMIN's password, `STUDY_GATEWAY_USER=oll_gateway`,
`STUDY_PRACTICE_TABLESPACE=DATA` (all in `render.yaml`), `STUDY_PUBLIC_URL` to the service's
`https://` address and `STUDY_ADMIN_EMAIL` to yours.

**One process.** Sessions, sign-in rate limits and provisioning state live in the app's memory, so
run one instance (one container, one Render service); several instances would not share them.

## Oracle version note

The content was written and verified on Oracle 19c, which this image runs. CI also runs it on
XE 21c, where a few things differ: `INTERSECT ALL`, `EXCEPT` and `MINUS ALL` work, and updating a
non key-preserved join view can raise ORA-30926 instead of ORA-01779. The content records these
differences (`try_error_since`), so the checks pass on both.
