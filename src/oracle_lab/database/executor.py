"""Run SQL*Plus-style scripts for the SQL lab, in one transaction per run.

With `inspect` (the interactive lab), every result also carries the transaction state, DML
results the rows of the target table before and after, and errors an explanation.
"""

from __future__ import annotations

import re
import time
from typing import Any

import oracledb

from oracle_lab.analysis import error_hints
from oracle_lab.database.connection import Database
from oracle_lab.database.policy import BLOCKED_MESSAGE, is_blocked
from oracle_lab.database.query import MAX_ROWS, execute_query, format_error
from oracle_lab.database.schema import SchemaContext
from oracle_lab.database.values import to_json_row
from oracle_lab.sqltext.messages import PLSQL_DONE, describe_success
from oracle_lab.sqltext.statements import Statement, StatementKind, first_words, split_statements, strip_leading_comments

# Target table of a single-table DML statement, for the before/after view in the SQL lab.
DML_TARGET = re.compile(
    r"(?:INSERT\s+INTO|UPDATE|DELETE(?:\s+FROM)?|MERGE\s+INTO)\s+([A-Za-z][\w$#]*(?:\.[A-Za-z][\w$#]*)?)\b",
    re.IGNORECASE)
SNAPSHOT_LIMIT = 300
DML_VERBS = {"INSERT", "UPDATE", "DELETE", "MERGE"}
DDL_VERBS = {"CREATE", "ALTER", "DROP", "TRUNCATE", "RENAME", "GRANT", "REVOKE", "COMMENT", "PURGE", "FLASHBACK", "AUDIT"}
PROMPT = re.compile(r"\s*PROMPT\s?(.*)", re.IGNORECASE)

TableSnapshot = tuple[list[str], dict[str, list]]


class Transaction:
    """What the lab session has changed since the last commit, as shown after each statement."""

    def __init__(self) -> None:
        self.pending = 0
        self.savepoints: list[list] = []  # [name, pending rows when it was set]

    def after(self, text: str, rowcount: int) -> dict[str, Any]:
        verb, obj = first_words(text)
        note = None
        if verb in DML_VERBS:
            self.pending += max(rowcount or 0, 0)
        elif verb == "SAVEPOINT":
            self.savepoints = [sp for sp in self.savepoints if sp[0] != obj] + [[obj, self.pending]]
        elif verb == "ROLLBACK":
            self._rollback(text)
        elif verb == "COMMIT" or verb in DDL_VERBS:
            if verb in DDL_VERBS and self.pending:
                note = f"This DDL statement committed {self.pending} pending row change{'s' if self.pending != 1 else ''} first."
            self.pending, self.savepoints = 0, []
        return {"pending": self.pending, "savepoints": [sp[0] for sp in self.savepoints], "note": note}

    def _rollback(self, text: str) -> None:
        m = re.search(r"\bTO\s+(?:SAVEPOINT\s+)?(\w+)", strip_leading_comments(text), re.IGNORECASE)
        names = [sp[0] for sp in self.savepoints]
        if m and m.group(1).upper() in names:
            i = names.index(m.group(1).upper())
            self.pending = self.savepoints[i][1]
            self.savepoints = self.savepoints[:i + 1]
        elif not m:
            self.pending, self.savepoints = 0, []


def table_snapshot(cur: oracledb.Cursor, table: str) -> TableSnapshot | None:
    """(columns, {rowid: row}) of a small table, or None if it is too big or cannot be read."""
    try:
        execute_query(cur, f"SELECT ROWIDTOCHAR(t.ROWID) AS row_id__, t.* FROM {table} t WHERE ROWNUM <= {SNAPSHOT_LIMIT + 1}")
        columns = [d[0] for d in cur.description][1:]
        rows = {r[0]: to_json_row(r[1:]) for r in cur.fetchall()}
    except oracledb.Error:
        return None
    return None if len(rows) > SNAPSHOT_LIMIT else (columns, rows)


def _changed_cells(before: list, after: list) -> list[int]:
    return [i for i, (x, y) in enumerate(zip(before, after, strict=True)) if x != y]


def row_changes(table: str, before: TableSnapshot, after: TableSnapshot) -> dict[str, Any]:
    columns, old = before
    _, new = after
    return {
        "table": table.upper(),
        "columns": columns,
        "inserted": [new[k] for k in new if k not in old],
        "deleted": [old[k] for k in old if k not in new],
        "updated": [{"before": old[k], "after": new[k], "changed": _changed_cells(old[k], new[k])}
                    for k in old if k in new and new[k] != old[k]],
    }


def execute_one(cur: oracledb.Cursor, stmt: Statement) -> dict[str, Any]:
    """Run one statement; returns a "rows" or "message" result. Raises oracledb.Error."""
    if is_blocked(stmt.text):
        raise oracledb.DatabaseError(BLOCKED_MESSAGE)
    sql = stmt.executable_text()
    started = time.perf_counter()
    if stmt.is_query:
        execute_query(cur, sql)
    else:
        cur.execute(sql)
    elapsed = round((time.perf_counter() - started) * 1000)
    if cur.description:
        columns = [d[0] for d in cur.description]
        rows = cur.fetchmany(MAX_ROWS + 1)
        return {"type": "rows", "columns": columns, "rows": [to_json_row(r) for r in rows[:MAX_ROWS]],
                "truncated": len(rows) > MAX_ROWS, "ms": elapsed}
    if stmt.kind is StatementKind.PLSQL:
        return {"type": "message", "message": PLSQL_DONE, "ms": elapsed}
    return {"type": "message", "message": describe_success(stmt.text, cur.rowcount), "ms": elapsed}


def client_command_result(stmt: Statement) -> dict[str, Any]:
    m = PROMPT.match(stmt.text)
    if m:
        return {"type": "prompt", "message": m.group(1)}
    return {"type": "skipped", "message": "SQL*Plus command ignored by the lab."}


class ScriptRunner:
    """Runs scripts on one database. Each run is one session and one transaction."""

    def __init__(self, database: Database):
        self.database = database

    def run(self, script: str, keep_changes: bool = False, stop_on_error: bool = False,
            inspect: bool = False) -> dict[str, Any]:
        statements = split_statements(script)
        try:
            conn = self.database.connect()
        except Exception as exc:  # noqa: BLE001 - any failure to connect is reported to the user
            return {"ok": False, "connect_error": format_error(exc), "results": []}
        try:
            results = self._run_all(conn, statements, stop_on_error, inspect)
            if keep_changes:
                conn.commit()
            else:
                conn.rollback()
        finally:
            conn.close()
        return {"ok": True, "results": results, "kept": keep_changes}

    @staticmethod
    def _run_all(conn: oracledb.Connection, statements: list[Statement], stop_on_error: bool,
                 inspect: bool) -> list[dict[str, Any]]:
        results = []
        tx = Transaction()
        ctx = SchemaContext(conn)
        with conn.cursor() as cur:
            for stmt in statements:
                entry: dict[str, Any] = {"sql": stmt.text}
                if stmt.kind is StatementKind.CLIENT:
                    results.append(entry | client_command_result(stmt))
                    continue
                target = DML_TARGET.match(strip_leading_comments(stmt.text)) \
                    if inspect and stmt.kind is StatementKind.SQL else None
                before = table_snapshot(cur, target.group(1)) if target else None
                try:
                    entry.update(execute_one(cur, stmt))
                except oracledb.Error as exc:
                    entry.update({"type": "error", "error": format_error(exc)})
                    if inspect:
                        entry["explain"] = error_hints.explain(entry["error"], stmt.text, ctx)
                        entry["tx"] = tx.after("", 0)
                    results.append(entry)
                    if stop_on_error:
                        break
                    continue
                if inspect:
                    entry["tx"] = tx.after(stmt.text, cur.rowcount if entry["type"] == "message" else 0)
                    after = table_snapshot(cur, target.group(1)) if before else None
                    if after:
                        entry["changes"] = row_changes(target.group(1), before, after)
                results.append(entry)
        return results
