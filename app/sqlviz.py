"""Join and set-operator visualizer for the SQL lab.

join:  for a query over exactly two tables (ANSI JOIN or comma syntax, any WHERE), the SELECT
       list is replaced by the ROWIDs of both tables. That shows, for every row of each table,
       whether it was matched, kept with NULLs by an outer join, or dropped.
set:   for two queries combined with UNION [ALL], INTERSECT or MINUS, each query runs on its own
       and every distinct row is marked with its count in each query and in the result.

visualize(conn, sql, run) returns a dict for the front end, or {"error": "..."} explaining why the
query is not supported. `run(conn, sql)` executes a query and returns (columns, rows).
"""

import sqltext

ROW_LIMIT = 200
UNSUPPORTED = ("The visualizer shows one join between exactly two tables, or two queries combined "
               "with UNION, UNION ALL, INTERSECT or MINUS.")


def visualize(conn, sql, run):
    sql = sqltext.strip_terminator(sql)
    if ";" in [t.text for t in sqltext.tokens(sql)]:
        return {"error": "Visualize one statement at a time."}
    compound = sqltext.split_set_operators(sql)
    if compound:
        return set_operator(conn, compound, run)
    parts = sqltext.select_parts(sql)
    if not parts or "from" not in parts:
        return {"error": UNSUPPORTED}
    refs = sqltext.from_tables(parts["from"])
    if not refs or len(refs) != 2:
        return {"error": UNSUPPORTED}
    return join(conn, sql, parts, refs, run)


def join(conn, sql, parts, refs, run):
    names = [r["alias"] or r["table"] for r in refs]
    if names[0] == names[1]:
        return {"error": "Give the two tables different aliases (for a self-join: employees e JOIN employees m)."}
    # Everything from FROM up to (not including) GROUP BY / HAVING / ORDER BY / FETCH.
    end = min([parts[k + "_start"] for k in ("group", "having", "order", "offset", "fetch") if k + "_start" in parts],
              default=len(sql))
    body = sql[parts["from_start"]:end]
    pairs_sql = f"SELECT ROWIDTOCHAR({names[0]}.ROWID), ROWIDTOCHAR({names[1]}.ROWID) {body}"
    try:
        _, pairs = run(conn, pairs_sql)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"Could not trace this join: {first_line(exc)}"}
    sides = []
    for ref, name, mine, other in ((refs[0], names[0], 0, 1), (refs[1], names[1], 1, 0)):
        try:
            columns, rows = run(conn, f"SELECT ROWIDTOCHAR(t.ROWID) AS row_id__, t.* FROM {ref['table']} t "
                                      f"WHERE ROWNUM <= {ROW_LIMIT}")
        except Exception as exc:  # noqa: BLE001
            return {"error": f"Could not read {ref['table']}: {first_line(exc)}"}
        partners = {}
        for pair in pairs:
            if pair[mine] is not None:
                partners.setdefault(pair[mine], []).append(pair[other])
        side_rows = []
        for row in rows:
            found = partners.get(row[0], [])
            matched = [p for p in found if p is not None]
            status = "matched" if matched else "null-extended" if found else "dropped"
            side_rows.append({"rowid": row[0], "cells": row[1:], "status": status, "partners": matched})
        sides.append({"table": ref["table"], "alias": name, "columns": columns[1:], "rows": side_rows})
    join_type = refs[1]["join"] or ","
    return {
        "kind": "join",
        "join": "comma syntax (joined in WHERE)" if join_type == "," else join_type,
        "result_rows": len(pairs),
        "grouped": any(k in parts for k in ("group", "having")) or parts["distinct"],
        "sides": sides,
    }


def set_operator(conn, compound, run):
    branches, ops, _ = compound
    if len(branches) != 2:
        return {"error": UNSUPPORTED + " Split longer chains into steps."}
    results = []
    for branch in branches + [f"{branches[0]}\n{ops[0]}\n{branches[1]}"]:
        try:
            results.append(run(conn, branch))
        except Exception as exc:  # noqa: BLE001
            return {"error": f"Could not run this part: {first_line(exc)}"}
    (columns, first), (_, second), (_, combined) = results

    def key(row):
        return tuple("\x00NULL" if v is None else str(v) for v in row)

    counts = {}
    order = []
    for slot, rows in ((0, first), (1, second), (2, combined)):
        for row in rows:
            k = key(row)
            if k not in counts:
                counts[k] = [0, 0, 0, row]
                order.append(k)
            counts[k][slot] += 1
    return {
        "kind": "set",
        "operator": ops[0],
        "columns": columns,
        "rows": [{"cells": counts[k][3], "first": counts[k][0], "second": counts[k][1], "result": counts[k][2]}
                 for k in order],
        "totals": [len(first), len(second), len(combined)],
    }


def first_line(exc):
    text = str(exc).strip()
    return text.splitlines()[0] if text else type(exc).__name__
