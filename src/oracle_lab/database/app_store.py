"""The app's own data in Oracle: study progress and personal notes, for hosts without a persistent disk.

The tables belong to a separate user (STUDY_STATE_USER), so nothing run in the SQL lab as ORASTUDY,
and no reset of the sample schema, can drop them. `ensure_app_schema` creates them on first start
(from `oracle-lab init-db`); later starts keep what is there.
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Iterator
from contextlib import contextmanager

import oracledb

from oracle_lab.config import DatabaseTarget
from oracle_lab.database.connection import Database, session
from oracle_lab.database.query import format_error
from oracle_lab.database.sample_schema import wait_for
from oracle_lab.study.state import State, new_state

log = logging.getLogger(__name__)

TABLES = {
    "LAB_STATE": """
        CREATE TABLE lab_state (
            id         NUMBER(1) DEFAULT 1 CONSTRAINT lab_state_pk PRIMARY KEY CONSTRAINT lab_state_one_row CHECK (id = 1),
            doc        CLOB NOT NULL CONSTRAINT lab_state_is_json CHECK (doc IS JSON),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL
        )""",
    "LAB_NOTES": """
        CREATE TABLE lab_notes (
            name       VARCHAR2(100) CONSTRAINT lab_notes_pk PRIMARY KEY,
            title      VARCHAR2(200) NOT NULL,
            body       CLOB NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL
        )""",
}
SEED_STATE = "INSERT INTO lab_state (id, doc) SELECT 1, :doc FROM dual WHERE NOT EXISTS (SELECT 1 FROM lab_state)"
SAVE_STATE = """
    MERGE INTO lab_state s USING (SELECT 1 AS id FROM dual) n ON (s.id = n.id)
    WHEN MATCHED THEN UPDATE SET s.doc = :doc, s.updated_at = SYSTIMESTAMP
    WHEN NOT MATCHED THEN INSERT (id, doc) VALUES (1, :doc)"""


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


class OracleStateStore:
    """The state as one JSON document in LAB_STATE. A transaction locks the row, so writers queue up."""

    def __init__(self, database: Database):
        self.database = database

    def load(self) -> State:
        with session(self.database) as conn, conn.cursor() as cur:
            cur.execute("SELECT doc FROM lab_state WHERE id = 1")
            row = cur.fetchone()
            return _state(row[0]) if row else new_state()

    @contextmanager
    def transaction(self) -> Iterator[State]:
        with session(self.database) as conn, conn.cursor() as cur:
            cur.execute("SELECT doc FROM lab_state WHERE id = 1 FOR UPDATE")
            row = cur.fetchone()
            state = _state(row[0]) if row else new_state()
            yield state
            cur.setinputsizes(doc=oracledb.DB_TYPE_CLOB)
            cur.execute(SAVE_STATE, doc=json.dumps(state))
            conn.commit()


class OracleNotes:
    """Personal notes as rows of LAB_NOTES, named like the files of FileNotes."""

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
            return _text(row[0]) if row else None

    def add(self, stem: str, title: str, text: str) -> str:
        with session(self.database) as conn, conn.cursor() as cur:
            n = 1
            while True:
                name = f"{stem}.md" if n == 1 else f"{stem}-{n}.md"
                cur.setinputsizes(body=oracledb.DB_TYPE_CLOB)
                try:
                    cur.execute("INSERT INTO lab_notes (name, title, body) VALUES (:name, :title, :body)",
                                name=name, title=title, body=text)
                except oracledb.IntegrityError:
                    n += 1
                    continue
                conn.commit()
                return name


def ensure_app_schema(database: Database, timeout: float) -> bool:
    """Wait for the database, then create the missing tables and the empty state row."""
    conn = wait_for(database, timeout)
    if conn is None:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT table_name FROM user_tables")
            present = {name for (name,) in cur}
            for name, ddl in TABLES.items():
                if name not in present:
                    cur.execute(ddl)
                    log.info("created table %s on %s", name, database.target)
            cur.setinputsizes(doc=oracledb.DB_TYPE_CLOB)
            cur.execute(SEED_STATE, doc=json.dumps(new_state()))
        conn.commit()
    except oracledb.Error as exc:
        log.error("creating the app tables on %s failed: %s", database.target, format_error(exc))
        return False
    finally:
        conn.close()
    log.info("app tables ready on %s", database.target)
    return True


def _state(value: State | str | oracledb.LOB) -> State:
    """The column has an IS JSON check, so python-oracledb usually returns it parsed; it can also be the CLOB."""
    return value if isinstance(value, dict) else json.loads(_text(value))


def _text(value: str | oracledb.LOB) -> str:
    return value if isinstance(value, str) else value.read()
