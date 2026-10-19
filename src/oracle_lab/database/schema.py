"""The data dictionary of the learning schema: lookups for error hints and the schema browser."""

from __future__ import annotations

from typing import Any

import oracledb

from oracle_lab.database.connection import Database

TEXT_TYPES = {"VARCHAR2", "CHAR", "NVARCHAR2", "NCHAR"}


class SchemaContext:
    """Schema lookups for error hints, on an open connection (the `ctx` of error_hints.explain)."""

    def __init__(self, conn: oracledb.Connection):
        self.conn = conn
        self._columns: dict[str, list[str]] | None = None

    def columns(self) -> dict[str, list[str]] | None:
        if self._columns is None:
            try:
                with self.conn.cursor() as cur:
                    cur.execute("SELECT table_name, column_name FROM user_tab_columns ORDER BY table_name, column_id")
                    columns: dict[str, list[str]] = {}
                    for table, column in cur:
                        columns.setdefault(table, []).append(column)
                    self._columns = columns
            except oracledb.Error:
                return None
        return self._columns

    def constraint(self, name: str) -> dict[str, Any] | None:
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """SELECT c.table_name, c.constraint_type, c.search_condition_vc, r.table_name,
                              (SELECT LISTAGG(cc.column_name, ',') WITHIN GROUP (ORDER BY cc.position)
                               FROM user_cons_columns cc WHERE cc.constraint_name = c.constraint_name),
                              (SELECT LISTAGG(rc.column_name, ',') WITHIN GROUP (ORDER BY rc.position)
                               FROM user_cons_columns rc WHERE rc.constraint_name = c.r_constraint_name)
                       FROM   user_constraints c
                       LEFT JOIN user_constraints r ON r.constraint_name = c.r_constraint_name
                       WHERE  c.constraint_name = :name""", name=name.upper())
                row = cur.fetchone()
        except oracledb.Error:
            return None
        if not row:
            return None
        table, ctype, condition, r_table, cols, r_cols = row
        return {"table": table, "type": ctype, "condition": condition, "r_table": r_table,
                "columns": (cols or "").split(","), "r_columns": (r_cols or "").split(",")}


def _shown_type(dtype: str, length: int, precision: int | None, scale: int | None) -> str:
    if dtype in TEXT_TYPES:
        return f"{dtype}({length})"
    if dtype == "NUMBER" and precision is not None:
        return f"NUMBER({precision}{',' + str(scale) if scale else ''})"
    return dtype


def describe_schema(database: Database) -> dict[str, Any]:
    """Tables and columns of the learning schema, and the database version, for the schema browser."""
    conn = database.connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT c.table_name, c.column_name, c.data_type, c.data_length,
                          c.data_precision, c.data_scale, c.nullable
                   FROM   user_tab_columns c
                   JOIN   user_tables t ON t.table_name = c.table_name
                   ORDER  BY c.table_name, c.column_id"""
            )
            tables: dict[str, list[dict[str, Any]]] = {}
            for table, column, dtype, length, precision, scale, nullable in cur:
                tables.setdefault(table, []).append(
                    {"name": column, "type": _shown_type(dtype, length, precision, scale), "nullable": nullable == "Y"})
        return {"ok": True, "tables": [{"name": k, "columns": v} for k, v in tables.items()],
                "database": {"version": conn.version, "dsn": database.target.dsn,
                             "major": int(conn.version.split(".")[0])}}
    finally:
        conn.close()
