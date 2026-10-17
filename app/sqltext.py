"""Light-weight SQL text analysis: tokens and the top-level clauses of a query.

Not a parser. It finds the SELECT list, FROM clause, GROUP BY and set operators of the queries
people write while studying, and returns None for anything it does not understand, so callers
can fall back to generic behavior.
"""

import re
from dataclasses import dataclass

Q_QUOTE_CLOSE = {"[": "]", "{": "}", "(": ")", "<": ">"}
CLAUSES = ("SELECT", "FROM", "WHERE", "GROUP", "HAVING", "ORDER", "OFFSET", "FETCH", "CONNECT", "START")
SET_OPERATORS = ("UNION", "INTERSECT", "MINUS", "EXCEPT")
GROUP_FUNCTIONS = {"COUNT", "SUM", "AVG", "MIN", "MAX", "LISTAGG", "STDDEV", "VARIANCE", "MEDIAN"}
JOIN_WORDS = {"JOIN", "INNER", "LEFT", "RIGHT", "FULL", "OUTER", "CROSS", "NATURAL"}


@dataclass
class Token:
    kind: str  # word, ident (double-quoted), string, number, punct
    text: str
    start: int
    end: int
    depth: int

    @property
    def upper(self):
        return self.text.upper() if self.kind == "word" else self.text


def tokens(sql):
    out = []
    i, n, depth = 0, len(sql), 0

    def add(kind, end):
        nonlocal i
        out.append(Token(kind, sql[i:end], i, end, depth))
        i = end

    while i < n:
        ch = sql[i]
        if ch.isspace():
            i += 1
        elif sql.startswith("--", i):
            j = sql.find("\n", i)
            i = n if j < 0 else j
        elif sql.startswith("/*", i):
            j = sql.find("*/", i + 2)
            i = n if j < 0 else j + 2
        elif (ch in "qQ" and i + 2 < n and sql[i + 1] == "'"
              and (i == 0 or not (sql[i - 1].isalnum() or sql[i - 1] in "_$#"))):
            close = Q_QUOTE_CLOSE.get(sql[i + 2], sql[i + 2])
            j = sql.find(close + "'", i + 3)
            add("string", n if j < 0 else j + 2)
        elif ch == "'":
            j = i + 1
            while j < n:
                if sql[j] == "'":
                    if j + 1 < n and sql[j + 1] == "'":
                        j += 2
                        continue
                    break
                j += 1
            add("string", min(j + 1, n))
        elif ch == '"':
            j = sql.find('"', i + 1)
            add("ident", n if j < 0 else j + 1)
        elif ch.isalpha() or ch in "_$#":
            j = i + 1
            while j < n and (sql[j].isalnum() or sql[j] in "_$#"):
                j += 1
            add("word", j)
        elif ch.isdigit() or (ch == "." and i + 1 < n and sql[i + 1].isdigit()):
            m = re.compile(r"\d*\.?\d+(?:[eE][+-]?\d+)?").match(sql, i)
            add("number", m.end())
        elif ch == "(":
            add("punct", i + 1)
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
            add("punct", i + 1)
        elif sql.startswith(("||", "<=", ">=", "<>", "!="), i):
            add("punct", i + 2)
        else:
            add("punct", i + 1)
    return out


def strip_terminator(sql):
    return sql.strip().rstrip(";").rstrip()


def split_set_operators(sql):
    """Split a compound query into branches. Returns (branches, operators, order_by_text) or None.

    The trailing ORDER BY of a compound query belongs to the whole query; it is returned separately.
    """
    sql = strip_terminator(sql)
    toks = tokens(sql)
    cuts, ops = [], []
    k = 0
    while k < len(toks):
        t = toks[k]
        if t.depth == 0 and t.kind == "word" and t.upper in SET_OPERATORS:
            op = t.upper
            end = t.end
            if op == "UNION" and k + 1 < len(toks) and toks[k + 1].upper == "ALL":
                op, end = "UNION ALL", toks[k + 1].end
                k += 1
            cuts.append((t.start, end))
            ops.append(op)
        k += 1
    if not ops:
        return None
    pieces, prev = [], 0
    for start, end in cuts:
        pieces.append(sql[prev:start].strip())
        prev = end
    last = sql[prev:].strip()
    order = ""
    last_toks = tokens(last)
    for j, t in enumerate(last_toks):
        if t.depth == 0 and t.upper == "ORDER" and j + 1 < len(last_toks) and last_toks[j + 1].upper == "BY":
            order, last = last[t.start:].strip(), last[:t.start].strip()
            break
    pieces.append(last)
    return [strip_parens(p) for p in pieces], ops, order


def strip_parens(sql):
    sql = sql.strip()
    while sql.startswith("(") and sql.endswith(")"):
        inner = tokens(sql)
        # only strip if the opening parenthesis closes at the very end
        closes = [t for t in inner if t.text == ")" and t.depth == 0]
        if len(closes) != 1 or closes[0].end != len(sql):
            break
        sql = sql[1:-1].strip()
    return sql


def select_parts(sql):
    """Top-level clauses of a simple query: {"select": text, "from": text, ...}, or None.

    Returns None for compound queries and for queries starting with WITH.
    """
    sql = strip_terminator(sql)
    toks = [t for t in tokens(sql) if t.depth == 0]
    if not toks or toks[0].upper != "SELECT" or split_set_operators(sql):
        return None
    marks = []
    for j, t in enumerate(toks):
        if t.kind != "word" or t.upper not in CLAUSES:
            continue
        if t.upper in ("GROUP", "ORDER") and not (j + 1 < len(toks) and toks[j + 1].upper == "BY"):
            continue
        if t.upper == "START" and not (j + 1 < len(toks) and toks[j + 1].upper == "WITH"):
            continue
        if t.upper == "FETCH" and not (j + 1 < len(toks) and toks[j + 1].upper in ("FIRST", "NEXT")):
            continue
        marks.append((t.upper, t.start, toks[j + 1].end if t.upper in ("GROUP", "ORDER") else t.end))
    parts = {}
    for j, (name, start, body_start) in enumerate(marks):
        end = marks[j + 1][1] if j + 1 < len(marks) else len(sql)
        key = name.lower()
        if key in parts:  # e.g. FETCH after OFFSET handled as one clause
            continue
        parts[key] = sql[body_start:end].strip()
        parts[key + "_start"] = start
    select = parts.get("select", "")
    parts["distinct"] = bool(re.match(r"(DISTINCT|UNIQUE)\b", select, re.IGNORECASE))
    if parts["distinct"]:
        parts["select"] = re.sub(r"^(DISTINCT|UNIQUE)\s+", "", select, flags=re.IGNORECASE)
    return parts


def split_commas(text):
    """Split at top-level commas."""
    items, start = [], 0
    for t in tokens(text):
        if t.depth == 0 and t.text == ",":
            items.append(text[start:t.start].strip())
            start = t.end
    items.append(text[start:].strip())
    return [i for i in items if i]


def item_alias(item):
    """Column alias of a SELECT-list item, or None."""
    toks = [t for t in tokens(item) if t.depth == 0]
    if len(toks) >= 2 and toks[-1].kind in ("word", "ident"):
        prev = toks[-2]
        if prev.upper == "AS" or prev.kind in ("word", "ident", "number", "string") or prev.text == ")":
            if toks[-1].upper not in ("NULL",) and not (len(toks) == 3 and toks[1].text == "."):
                return toks[-1].text.strip('"').upper()
    return None


def item_expression(item):
    """A SELECT-list item without its alias."""
    alias = item_alias(item)
    if not alias:
        return item.strip()
    toks = [t for t in tokens(item) if t.depth == 0]
    cut = toks[-2].start if toks[-2].upper == "AS" else toks[-1].start
    return item[:cut].strip()


def has_group_function(text):
    toks = tokens(text)
    return any(t.kind == "word" and t.upper in GROUP_FUNCTIONS and j + 1 < len(toks) and toks[j + 1].text == "("
               for j, t in enumerate(toks))


def normalize(expr):
    return re.sub(r"\s+", "", expr).upper()


def from_tables(from_text):
    """Table references of a FROM clause: [{"table", "alias", "join"}], or None if it has
    subqueries, more than plain joins, or anything the visualizer cannot follow."""
    toks = tokens(from_text)
    if any(t.text == "(" and t.depth == 0 and (j == 0 or toks[j - 1].upper in ("FROM", ",", "JOIN"))
           for j, t in enumerate(toks)):
        return None
    refs = []
    j = 0
    pending_join = None
    while j < len(toks):
        t = toks[j]
        if t.depth > 0:
            j += 1
            continue
        if t.kind in ("word", "ident") and (j == 0 or toks[j - 1].text == "," or toks[j - 1].upper == "JOIN"):
            name = t.text.strip('"').upper()
            if j + 2 < len(toks) and toks[j + 1].text == ".":  # schema.table
                name = toks[j + 2].text.strip('"').upper()
                j += 2
            alias = None
            if j + 1 < len(toks) and toks[j + 1].kind in ("word", "ident") and toks[j + 1].upper not in (
                    JOIN_WORDS | {"ON", "USING", "WHERE", "AS"}):
                alias = toks[j + 1].text.strip('"').upper()
                j += 1
            refs.append({"table": name, "alias": alias, "join": pending_join or ("," if refs else None)})
            pending_join = None
        elif t.kind == "word" and t.upper in JOIN_WORDS:
            words = []
            while j < len(toks) and toks[j].kind == "word" and toks[j].upper in JOIN_WORDS:
                words.append(toks[j].upper)
                j += 1
            pending_join = " ".join(w for w in words if w != "OUTER")
            continue
        j += 1
    return refs or None
