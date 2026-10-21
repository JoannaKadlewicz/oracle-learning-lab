"""Run queries so that every column type can be fetched, and turn errors into readable text."""

from __future__ import annotations

import oracledb

from oracle_lab.database.values import to_json_row
from oracle_lab.i18n import Msg
from oracle_lab.sqltext.statements import QUERY_VERBS, executable_statements

MAX_ROWS = 500

Rows = list[list]
Result = tuple[list[str], Rows]

# Thin-mode python-oracledb cannot fetch TIMESTAMP WITH TIME ZONE values that use a region
# name (DPY-3022), drops the offset of the others, and does not convert TIMESTAMP WITH LOCAL
# TIME ZONE to the session time zone. Such columns are converted to text by the database.
TEXT_FETCH_FORMATS = {
    oracledb.DB_TYPE_TIMESTAMP_TZ: "YYYY-MM-DD HH24:MI:SSXFF TZR",
    oracledb.DB_TYPE_TIMESTAMP_LTZ: "YYYY-MM-DD HH24:MI:SSXFF",
}


def format_error(exc: BaseException) -> str:
    """The error text without python-oracledb's "Help:" link lines."""
    return "\n".join(line for line in str(exc).strip().splitlines() if not line.startswith("Help:"))


def first_line(text: str) -> str:
    return text.strip().splitlines()[0] if text.strip() else text


def fetchable_sql(cur: oracledb.Cursor, sql: str) -> str:
    """Return the query, wrapped so that time zone columns are fetched as text."""
    cur.parse(sql)
    columns = cur.description or []
    names = [d.name for d in columns]
    if (not any(d.type_code in TEXT_FETCH_FORMATS for d in columns)
            or len(set(names)) != len(names) or any('"' in n for n in names)):
        return sql
    select = []
    for d in columns:
        ident = '"' + d.name + '"'
        fmt = TEXT_FETCH_FORMATS.get(d.type_code)
        select.append(f"TO_CHAR({ident}, '{fmt}') AS {ident}" if fmt else ident)
    return f"SELECT {', '.join(select)}\nFROM ({sql})"


def execute_query(cur: oracledb.Cursor, sql: str) -> oracledb.Cursor:
    """Execute a SELECT or WITH query so that every column can be fetched."""
    wrapped = fetchable_sql(cur, sql)
    if wrapped is not sql:
        try:
            return cur.execute(wrapped)
        except oracledb.Error:
            pass  # e.g. FOR UPDATE inside the inline view; fall back to the plain query
    return cur.execute(sql)


def fetch(cur: oracledb.Cursor, limit: int = MAX_ROWS) -> Result:
    columns = [d[0] for d in cur.description]
    return columns, [to_json_row(r) for r in cur.fetchmany(limit)]


def query_rows(conn: oracledb.Connection, sql: str, limit: int = MAX_ROWS) -> Result:
    with conn.cursor() as cur:
        execute_query(cur, sql)
        return fetch(cur, limit)


def single_query(conn: oracledb.Connection, sql: str) -> Result:
    """(columns, rows) of a script that must hold exactly one SELECT; ValueError otherwise."""
    statements = executable_statements(sql)
    if len(statements) != 1:
        raise ValueError(Msg.of("Submit exactly one SELECT statement."))
    if statements[0].verb not in QUERY_VERBS:
        raise ValueError(Msg.of("Exercises expect a SELECT (or WITH ... SELECT) query."))
    return query_rows(conn, statements[0].executable_text())
