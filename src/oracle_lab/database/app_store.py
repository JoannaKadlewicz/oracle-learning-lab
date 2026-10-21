"""The app's own data in Oracle, for hosts without a persistent disk.

The tables belong to a separate user (STUDY_STATE_USER), so nothing run in the SQL lab as ORASTUDY,
and no reset of the sample schema, can drop them. `ensure_app_schema` (from `oracle-lab init-db`)
applies the versioned migrations of accounts.oracle_store; later starts keep what is there.
The single-user LAB_STATE and LAB_NOTES tables stay, and the legacy readers here exist only so
their content can be imported into the first account.
"""

from __future__ import annotations

import json
import logging
import threading

import oracledb

from oracle_lab.accounts.oracle_store import lob_text, migrate
from oracle_lab.config import DatabaseTarget
from oracle_lab.database.connection import Database, session
from oracle_lab.database.query import format_error
from oracle_lab.database.sample_schema import wait_for
from oracle_lab.study.state import State, new_state

log = logging.getLogger(__name__)


class ConnectionPool:
    """A small python-oracledb pool for one target, created on first use.

    The store is used on every request, and a new TLS session to a cloud database takes a while.
    The password is read when the pool is created, so a changed one takes effect after a restart.
    """

    def __init__(self, target: DatabaseTarget, call_timeout_ms: int = 15000, max_size: int = 4):
        self.target = target
        self.call_timeout_ms = call_timeout_ms
        self.max_size = max_size
        self._pool: oracledb.ConnectionPool | None = None
        self._lock = threading.Lock()

    def connect(self) -> oracledb.Connection:
        with self._lock:
            if self._pool is None:
                self._pool = oracledb.create_pool(
                    user=self.target.user, password=self.target.password.reveal(), dsn=self.target.dsn,
                    min=0, max=self.max_size, increment=1,
                    getmode=oracledb.POOL_GETMODE_TIMEDWAIT, wait_timeout=self.call_timeout_ms,
                )
        conn = self._pool.acquire()
        conn.call_timeout = self.call_timeout_ms
        return conn

    def __repr__(self) -> str:
        return f"ConnectionPool({self.target})"


class LegacyOracleState:
    """The state the single-user app kept as one JSON document in LAB_STATE (read only)."""

    def __init__(self, database: Database):
        self.database = database

    def load(self) -> State:
        with session(self.database) as conn, conn.cursor() as cur:
            cur.execute("SELECT doc FROM lab_state WHERE id = 1")
            row = cur.fetchone()
            return _state(row[0]) if row else new_state()


class LegacyOracleNotes:
    """The personal notes the single-user app kept in LAB_NOTES (read only)."""

    def __init__(self, database: Database):
        self.database = database

    def entries(self) -> list[tuple[str, str]]:
        with session(self.database) as conn, conn.cursor() as cur:
            cur.execute("SELECT name, title FROM lab_notes ORDER BY name DESC")
            return [(name, title) for name, title in cur]

    def read(self, name: str) -> str | None:
        with session(self.database) as conn, conn.cursor() as cur:
            cur.execute("SELECT body FROM lab_notes WHERE name = :name", name=name)
            row = cur.fetchone()
            return lob_text(row[0]) if row else None


def ensure_app_schema(database: Database, timeout: float) -> bool:
    """Wait for the database, then bring the app tables up to the latest version."""
    conn = wait_for(database, timeout)
    if conn is None:
        return False
    conn.close()
    try:
        migrate(database)
    except oracledb.Error as exc:
        log.error("migrating the app tables on %s failed: %s", database.target, format_error(exc))
        return False
    log.info("app tables ready on %s", database.target)
    return True


def _state(value: State | str | oracledb.LOB) -> State:
    """The column has an IS JSON check, so python-oracledb usually returns it parsed; it can also be the CLOB."""
    return value if isinstance(value, dict) else json.loads(lob_text(value))
