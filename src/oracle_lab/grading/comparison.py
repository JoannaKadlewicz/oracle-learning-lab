"""Compare a submission's result with the expected one, and explain the difference."""

from __future__ import annotations

from typing import Any

from oracle_lab.i18n import Msg, translate

NULL = "\x00NULL"  # a key for NULL that no string value can collide with

Key = tuple[str, ...]


def normalize_rows(rows: list[list]) -> list[Key]:
    return [tuple(NULL if v is None else str(v) for v in r) for r in rows]


def diff_rows(got: list[list], want: list[list], ordered: bool) -> list[dict[str, Any]]:
    """One table showing your rows against the expected ones.

    Each row: {"status": ok | extra | missing | changed | moved, "cells", "expected"?, "diff"?}.
    A wrong row is paired with a missing row when at least half of their cells are equal, and
    shown as changed with the differing cells; rows in the wrong position are shown as moved.
    """
    g, w = normalize_rows(got), normalize_rows(want)
    if ordered and sorted(g) == sorted(w):
        return [{"status": "ok" if gi == wi else "moved", "cells": row} for row, gi, wi in zip(got, g, w, strict=True)]
    remaining: dict[Key, list[int]] = {}
    for i, key in enumerate(w):
        remaining.setdefault(key, []).append(i)
    out = []
    for row, key in zip(got, g, strict=True):
        if remaining.get(key):
            remaining[key].pop(0)
            out.append({"status": "ok", "cells": row})
        else:
            out.append({"status": "extra", "cells": row, "key": key})
    missing = [i for idxs in remaining.values() for i in idxs]
    for entry in out:
        if entry["status"] != "extra" or not missing:
            continue
        score, best = max((sum(a == b for a, b in zip(entry["key"], w[i], strict=False)), i) for i in missing)
        if score * 2 >= len(entry["key"]) and score < len(entry["key"]):
            entry.update({"status": "changed", "expected": want[best],
                          "diff": [c for c, (a, b) in enumerate(zip(entry["key"], w[best], strict=False)) if a != b]})
            missing.remove(best)
    for entry in out:
        entry.pop("key", None)
    return out + [{"status": "missing", "cells": want[i]} for i in sorted(missing)]


def _feedback(lab: dict, columns: list[str], rows: list[list], exp_columns: list[str],
              exp_rows: list[list]) -> tuple[bool, list[str]]:
    """Passed, and the feedback in English (Msg, translated by compare_results)."""
    got, want = normalize_rows(rows), normalize_rows(exp_rows)
    if len(columns) != len(exp_columns):
        return False, [Msg.of("Expected {count} columns ({names}), got {got}.", count=len(exp_columns),
                              names=", ".join(exp_columns), got=len(columns))]
    if len(rows) != len(exp_rows):
        return False, [Msg.of("Expected {count} rows, got {got}.", count=len(exp_rows), got=len(rows))]
    if sorted(got) != sorted(want):
        feedback = [Msg.of("Row values differ from the expected result.")]
        missing = [r for r in want if r not in got]
        if missing:
            feedback.append(Msg.of("Example expected row not in your result: {row}",
                                   row=", ".join("NULL" if v == NULL else v for v in missing[0])))
        return False, feedback
    if lab.get("ordered", True) and got != want:
        return False, [Msg.of("The right rows, but in the wrong order. Check ORDER BY and tie-breakers.")]
    return True, []


def compare_results(lab: dict, columns: list[str], rows: list[list], exp_columns: list[str],
                    exp_rows: list[list], lang: str = "en") -> dict[str, Any]:
    passed, feedback = _feedback(lab, columns, rows, exp_columns, exp_rows)
    if passed and lab.get("kind", "query") == "query":
        expected_names = [c.strip().upper() for c in lab["columns"].split(",")]
        if [c.upper() for c in columns] != expected_names:
            feedback.append(Msg.of("Correct values. Column names differ from {columns}; aliases are not graded.",
                                   columns=lab["columns"]))
    feedback = [translate(lang, f) for f in feedback]
    return {
        "passed": passed,
        "feedback": feedback,
        "columns": columns,
        "rows": rows,
        "expected_columns": exp_columns if not passed else None,
        "expected_rows": exp_rows if not passed else None,
        "diff": diff_rows(rows, exp_rows, lab.get("ordered", True))
        if not passed and len(columns) == len(exp_columns) else None,
    }
