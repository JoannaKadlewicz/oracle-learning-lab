"""The database-engine boundary: everything the app asks of a database product goes through an Engine.

An exam names its engine in the registry (exams.py); its database key names the database it runs on.
Oracle is the only engine today (engines/oracle.py).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from oracle_lab import exams
from oracle_lab.engines.oracle import OracleEngine

if TYPE_CHECKING:
    from oracle_lab.config import DatabaseTarget, PracticeTarget
    from oracle_lab.database.connection import Database


class Provisioner(Protocol):
    """Creates and drops the learners' practice schemas on one practice target."""

    def ensure_profile(self) -> None: ...
    def create(self, name: str) -> None: ...
    def drop(self, name: str) -> None: ...
    def size_mb(self, name: str) -> float | None: ...


class Engine(Protocol):
    name: str          # registry engine id, "oracle"
    label: str         # shown to learners, "Oracle"
    editor_mode: str   # CodeMirror mode, "text/x-plsql" for Oracle

    def database(self, target: DatabaseTarget, call_timeout_ms: int) -> Database: ...
    def proxy_database(self, gateway: DatabaseTarget, schema: str, call_timeout_ms: int) -> Database: ...
    def provisioner(self, target: PracticeTarget, call_timeout_ms: int) -> Provisioner: ...
    # `lang`: the language of the feedback the engine writes itself (explanations, grading notes); the
    # database's own error texts and SQL*Plus-style result lines stay as the database writes them.
    def run_script(self, database: Database, script: str, *, keep_changes: bool = False,
                   inspect: bool = False, lang: str = "en") -> dict[str, Any]: ...
    def run_cleanup(self, database: Database, item: dict) -> None: ...
    def grade(self, database: Database, lab: dict, sql: str, *, lang: str = "en") -> dict[str, Any]: ...
    def visualize(self, database: Database, sql: str, *, lang: str = "en") -> dict[str, Any]: ...
    def describe(self, database: Database) -> dict[str, Any]: ...
    def reset_sample(self, database: Database) -> dict[str, Any]: ...
    def ensure_sample(self, database: Database, timeout: float) -> bool: ...


ENGINES: dict[str, Engine] = {"oracle": OracleEngine()}


def engine(name: str) -> Engine:
    """The engine registered as `name`; KeyError for an unknown one."""
    return ENGINES[name]


def engine_for_exam(code: str | None) -> Engine:
    """The engine of exam `code` (an unknown or missing code means the default exam)."""
    return engine(exams.get(code).engine)


def engine_for_key(key: str) -> Engine:
    """The engine of the exams that run on database key `key`."""
    return engine(exams.engine_of_key(key))
