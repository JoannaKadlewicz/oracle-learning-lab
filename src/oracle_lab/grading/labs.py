"""Run exercise submissions against the database and grade them, leaving no changes behind.

Lab kinds:
    query  one SELECT, graded on its result
    dml    DML statements, graded on the result of the lab's check query afterwards; rolled back
    ddl    any statements, graded on the check query (usually over the data dictionary);
           DDL commits, so the lab's cleanup script drops its objects before and after grading
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

import oracledb

from oracle_lab.analysis import error_hints
from oracle_lab.database.connection import Database
from oracle_lab.database.policy import BLOCKED_MESSAGE, is_blocked
from oracle_lab.database.query import Result, format_error, single_query
from oracle_lab.database.schema import SchemaContext
from oracle_lab.grading.comparison import compare_results
from oracle_lab.sqltext.statements import StatementKind, executable_statements, split_statements

DML_LAB_VERBS = frozenset({"INSERT", "UPDATE", "DELETE", "MERGE", "SAVEPOINT", "ROLLBACK", "SELECT", "WITH"})


class LabKind(StrEnum):
    QUERY = "query"
    DML = "dml"
    DDL = "ddl"


def lab_kind(lab: dict) -> LabKind:
    return LabKind(lab.get("kind", LabKind.QUERY))


def run_cleanup(conn: oracledb.Connection, lab: dict) -> None:
    """Run the lab's cleanup statements, ignoring errors such as ORA-00942 (no such table)."""
    with conn.cursor() as cur:
        for stmt in split_statements(lab.get("cleanup", "")):
            try:
                cur.execute(stmt.executable_text())
            except oracledb.Error:
                pass


def run_lab_statements(conn: oracledb.Connection, lab: dict, script: str) -> Result:
    """Run a dml or ddl lab script, then return the lab's check query result."""
    statements = executable_statements(script)
    if not statements:
        raise ValueError("Write at least one statement.")
    with conn.cursor() as cur:
        for n, stmt in enumerate(statements, 1):
            if stmt.kind is StatementKind.PLSQL:
                raise ValueError(f"Statement {n}: this exercise does not use PL/SQL blocks.")
            if is_blocked(stmt.text):
                raise ValueError(f"Statement {n}: {BLOCKED_MESSAGE}")
            if lab_kind(lab) is LabKind.DML and stmt.verb not in DML_LAB_VERBS:
                raise ValueError(f"Statement {n}: this exercise expects DML only. {stmt.verb} is not allowed "
                                 "(COMMIT and DDL would make the changes permanent).")
            try:
                cur.execute(stmt.executable_text())
            except oracledb.Error as exc:
                raise ValueError(f"Statement {n} failed: {format_error(exc)}") from exc
    return single_query(conn, lab["check"])


def lab_result(conn: oracledb.Connection, lab: dict, sql: str) -> Result:
    """Return (columns, rows) that a lab submission is graded on, leaving no changes behind."""
    kind = lab_kind(lab)
    if kind is LabKind.QUERY:
        try:
            return single_query(conn, sql)
        finally:
            conn.rollback()
    if kind is LabKind.DDL:
        run_cleanup(conn, lab)
    try:
        return run_lab_statements(conn, lab, sql)
    finally:
        conn.rollback()
        if kind is LabKind.DDL:
            run_cleanup(conn, lab)


def grade(database: Database, lab: dict, sql: str) -> dict[str, Any]:
    """Grade a submission by comparing its result with the result of the lab's solution."""
    conn = database.connect()
    try:
        try:
            columns, rows = lab_result(conn, lab, sql)
        except (oracledb.Error, ValueError) as exc:
            message = format_error(exc)
            return {"passed": False, "error": message, "explain": error_hints.explain(message, sql, SchemaContext(conn))}
        exp_columns, exp_rows = lab_result(conn, lab, lab["solution"])
    finally:
        conn.close()
    return compare_results(lab, columns, rows, exp_columns, exp_rows)
