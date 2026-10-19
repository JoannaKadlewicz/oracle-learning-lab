"""The ORASTUDY sample tables: create them on first start, and reset them on request."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import oracledb

from oracle_lab.database.connection import Database
from oracle_lab.database.executor import ScriptRunner
from oracle_lab.database.query import format_error
from oracle_lab.resources import SQL_DIR

log = logging.getLogger(__name__)

# (step, script); errors are ignored in the cleanup step, which drops tables that may not exist.
SCRIPTS = (("cleanup", "99_cleanup.sql"), ("create", "01_create_tables.sql"), ("seed", "02_seed_data.sql"))
TOLERATES_ERRORS = {"cleanup"}
MARKER_TABLE = "EMPLOYEES"


class SampleSchema:
    def __init__(self, database: Database, sql_dir: Path = SQL_DIR):
        self.database = database
        self.sql_dir = sql_dir

    def reset(self) -> dict[str, Any]:
        """Drop and recreate the sample tables. Returns {"ok", "log"} or {"ok": False, "error"}."""
        runner = ScriptRunner(self.database)
        steps = []
        for step, file_name in SCRIPTS:
            result = runner.run((self.sql_dir / file_name).read_text(encoding="utf-8"), keep_changes=True)
            if not result["ok"]:
                return {"ok": False, "error": result["connect_error"]}
            failed = [r["error"] for r in result["results"] if r["type"] == "error"]
            if failed and step not in TOLERATES_ERRORS:
                return {"ok": False, "error": f"{step}: {failed[0]}"}
            steps.append(f"{step}: {len(result['results'])} statements")
        return {"ok": True, "log": steps}

    @staticmethod
    def exists(conn: oracledb.Connection) -> bool:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM user_tables WHERE table_name = :name", name=MARKER_TABLE)
            return cur.fetchone()[0] > 0


def wait_for(database: Database, timeout: float, retry_seconds: float = 5,
             sleep: Callable[[float], None] = time.sleep) -> oracledb.Connection | None:
    """A connection once the learning user can log in, or None after `timeout` seconds."""
    start = time.monotonic()
    attempt = 0
    while True:
        attempt += 1
        try:
            return database.connect()
        except Exception as exc:  # noqa: BLE001 - every failure means "not ready yet"
            elapsed = time.monotonic() - start
            message = " | ".join(line.strip() for line in format_error(exc).splitlines() if line.strip())
            if elapsed >= timeout:
                log.error("database %s still not reachable after %.0fs: %s", database.target, elapsed, message)
                return None
            log.info("waiting for %s (attempt %d, %.0fs of %.0fs): %s",
                     database.target, attempt, elapsed, timeout, message)
            sleep(retry_seconds)


def ensure_sample_schema(database: Database, timeout: float) -> bool:
    """Wait for the database, then create the sample schema unless it is there already.

    Restarting therefore keeps the data people changed in the lab.
    """
    conn = wait_for(database, timeout)
    if conn is None:
        return False
    try:
        present = SampleSchema.exists(conn)
    finally:
        conn.close()
    if present:
        log.info("connected to %s; sample schema already present, keeping it", database.target)
        return True
    log.info("connected to %s; creating the sample schema", database.target)
    result = SampleSchema(database).reset()
    if not result["ok"]:
        log.error("creating the sample schema on %s failed: %s", database.target, result["error"])
        return False
    log.info("sample schema created on %s (%s)", database.target, "; ".join(result["log"]))
    return True
