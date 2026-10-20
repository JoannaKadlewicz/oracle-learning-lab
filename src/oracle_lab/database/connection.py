"""Connections to the learning schema, and the choice of database per exam track."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Protocol

import oracledb

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
    """The database each exam track runs its SQL on; tracks without their own use the default."""

    def __init__(self, default: Database, by_exam: Mapping[str, Database] | None = None):
        self.default = default
        self.by_exam = dict(by_exam or {})

    def for_exam(self, exam_code: str) -> Database:
        return self.by_exam.get(exam_code, self.default)

    @property
    def has_track_databases(self) -> bool:
        return bool(self.by_exam)

    def all(self) -> list[Database]:
        return [self.default, *(db for db in self.by_exam.values() if db is not self.default)]
