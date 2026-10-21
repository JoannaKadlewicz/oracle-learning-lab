"""Connections to the learning schema, and the choice of database per exam (by database key)."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Protocol

import oracledb

from oracle_lab import exams
from oracle_lab.config import DatabaseTarget

# Fetch NUMBER as Decimal, so values.to_json_value shows exactly what Oracle stores.
oracledb.defaults.fetch_decimals = True

SESSION_SETUP = (
    "ALTER SESSION SET NLS_DATE_FORMAT = 'YYYY-MM-DD HH24:MI:SS'",
    "ALTER SESSION SET NLS_TIMESTAMP_FORMAT = 'YYYY-MM-DD HH24:MI:SS.FF'",
)


def open_session(user: str, password: str, dsn: str, call_timeout_ms: int) -> oracledb.Connection:
    """A thin-mode connection with the call timeout and SESSION_SETUP applied."""
    conn = oracledb.connect(user=user, password=password, dsn=dsn)
    conn.call_timeout = call_timeout_ms
    with conn.cursor() as cur:
        for statement in SESSION_SETUP:
            cur.execute(statement)
    return conn


class Database(Protocol):
    """Something that opens sessions on one Oracle schema."""

    target: DatabaseTarget

    def connect(self) -> oracledb.Connection: ...


class OracleDatabase:
    """A python-oracledb (thin mode) connection source for one target."""

    def __init__(self, target: DatabaseTarget, call_timeout_ms: int = 15000):
        self.target = target
        self.call_timeout_ms = call_timeout_ms

    def connect(self) -> oracledb.Connection:
        return open_session(self.target.user, self.target.password.reveal(), self.target.dsn, self.call_timeout_ms)

    def __repr__(self) -> str:
        return f"OracleDatabase({self.target})"


@contextmanager
def session(database: Database) -> Iterator[oracledb.Connection]:
    """A connection that is rolled back and closed when the block ends."""
    conn = database.connect()
    try:
        yield conn
    finally:
        try:
            conn.rollback()
        finally:
            conn.close()


class DatabaseCatalog:
    """The shared database of each database key; an exam runs on its key's database, else its fallback key's."""

    def __init__(self, by_key: Mapping[str, Database]):
        self.by_key = dict(by_key)
        self.default = self.by_key[exams.DEFAULT_DATABASE]

    def for_exam(self, exam_code: str | None) -> Database | None:
        """The database of the exam's key, else of its registry fallback key; None when neither is configured."""
        exam = exams.get(exam_code)
        for key in (exam.database, exam.fallback):
            if key is not None and key in self.by_key:
                return self.by_key[key]
        return None

    @property
    def has_track_databases(self) -> bool:
        return len(self.by_key) > 1

    def all(self) -> list[Database]:
        """The distinct databases, the default first."""
        found: list[Database] = []
        for database in (self.default, *self.by_key.values()):
            if not any(database is seen for seen in found):
                found.append(database)
        return found
