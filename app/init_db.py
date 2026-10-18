"""Prepare the database for Oracle Learning Lab (used by docker compose and CI).

Run from the repository root:
    python app/init_db.py

Waits until the learning user can log in (up to STUDY_INIT_TIMEOUT seconds, default 600),
then creates the sample schema with the same scripts as "Reset sample data", but only when
table EMPLOYEES does not exist yet, so restarting the stack keeps your data.
Connection settings come from the same environment variables as server.py.
With STUDY_DSN_23AI set (the Oracle 23ai database of the 1Z0-171 track), prepares that one too.
Exits with status 1 if a database never becomes reachable or the schema cannot be created.
"""

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import server  # noqa: E402

TIMEOUT = int(os.environ.get("STUDY_INIT_TIMEOUT", "600"))
RETRY_SECONDS = 5


def target():
    if server.USE_23AI:
        return f"{server.DB_USER_23AI}@{server.DSN_23AI}"
    return f"{server.DB_USER}@{server.DSN}"


def wait_for_database():
    start = time.monotonic()
    attempt = 0
    while True:
        attempt += 1
        try:
            return server.connect()
        except Exception as exc:  # noqa: BLE001
            elapsed = time.monotonic() - start
            message = " | ".join(line.strip() for line in server.format_error(exc).splitlines() if line.strip())
            if elapsed >= TIMEOUT:
                print(f"init_db: database still not reachable after {elapsed:.0f}s: {message}", flush=True)
                return None
            print(f"init_db: waiting for {target()} "
                  f"(attempt {attempt}, {elapsed:.0f}s of {TIMEOUT}s): {message}", flush=True)
            time.sleep(RETRY_SECONDS)


def main():
    status = prepare()
    if status == 0 and server.DSN_23AI:
        server.USE_23AI = True  # connect() now targets the 23ai database
        status = prepare()
    return status


def prepare():
    conn = wait_for_database()
    if conn is None:
        return 1
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM user_tables WHERE table_name = 'EMPLOYEES'")
            exists = cur.fetchone()[0] > 0
    finally:
        conn.close()
    if exists:
        print(f"init_db: connected to {target()}; sample schema already present, keeping it.",
              flush=True)
        return 0
    print(f"init_db: connected to {target()}; creating the sample schema...", flush=True)
    result = server.reset_sample_data()
    if not result["ok"]:
        print(f"init_db: creating the sample schema failed: {result['error']}", flush=True)
        return 1
    print("init_db: sample schema created (" + "; ".join(result["log"]) + ").", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
