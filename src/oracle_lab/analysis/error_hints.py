"""Explanations for Oracle errors, with a hint about the query that caused them.

explain(error_text, sql, ctx, lang) returns {"code", "title", "text", "hint", "topic"} or None, in `lang`:
titles and explanations from the overlay analysis/i18n/<lang>.json ({code: {"title", "explanation"}}),
hints through the server catalog. A missing translation falls back to English.
ctx provides the schema: ctx.columns() -> {TABLE: [COLUMN, ...]} and
ctx.constraint(name) -> {"table", "type", "columns", "r_table", "r_columns", "condition"} or None.
Hints are best effort: when the query cannot be analysed, only the general text is shown.
"""

import difflib
import json
import logging
import re
from functools import cache
from pathlib import Path

from oracle_lab.i18n import DEFAULT_LANGUAGE, Msg, ntranslate, translate
from oracle_lab.sqltext import clauses as sqltext

OVERLAY_DIR = Path(__file__).with_name("i18n")
log = logging.getLogger(__name__)

# code: (title, explanation, topic of the study notes)
ERRORS = {
    "ORA-00001": ("Unique constraint violated",
                  "The statement would store a value that already exists in a column (or column combination) "
                  "protected by a PRIMARY KEY or UNIQUE constraint. NULLs never clash in a single-column UNIQUE constraint.", "t10"),
    "ORA-00904": ("Invalid identifier",
                  "Oracle cannot find a column or alias with this name where it was used. Common causes: a typo, a column "
                  "alias used in WHERE or GROUP BY (aliases exist only in ORDER BY), a column of a table not in FROM, or a "
                  "quoted identifier with the wrong case.", "t01"),
    "ORA-00905": ("Missing keyword",
                  "A clause is incomplete: for example JOIN without ON, CASE without END, or a wrong keyword order "
                  "such as DROP VIEW v CASCADE.", "t01"),
    "ORA-00907": ("Missing right parenthesis",
                  "Parentheses are unbalanced, or something inside them is not allowed there: for example a data type "
                  "with a wrong size, or ORDER BY inside a subquery used with IN.", "t01"),
    "ORA-00913": ("Too many values",
                  "More values than columns: an INSERT VALUES list longer than its column list, or a subquery returning "
                  "more columns than the comparison expects.", "t09"),
    "ORA-00918": ("Column ambiguously defined",
                  "An unqualified column name exists in more than one table of the FROM clause. Qualify it with a table "
                  "alias, for example e.department_id.", "t06"),
    "ORA-00920": ("Invalid relational operator",
                  "A condition is missing its comparison operator, or uses one Oracle does not have (such as == ).", "t02"),
    "ORA-00923": ("FROM keyword not found where expected",
                  "Something in the SELECT list ends earlier than Oracle expects: often a missing comma between columns, "
                  "a column alias with spaces that is not in double quotes, or a string in single quotes used as an alias.", "t01"),
    "ORA-00927": ("Missing equal sign",
                  "An UPDATE ... SET clause needs column = value for each column, or (col1, col2) = (subquery).", "t09"),
    "ORA-00932": ("Inconsistent data types",
                  "Two values that must have compatible types do not: for example NUMBER and DATE in a comparison, "
                  "CASE branches of different types, or COALESCE arguments from different type families.", "t04"),
    "ORA-00933": ("SQL command not properly ended",
                  "Oracle finished parsing a valid statement but found more text. Common causes: AS before a table alias "
                  "(Oracle does not allow it), ORDER BY inside one branch of a set operator, or clauses in the wrong order.", "t01"),
    "ORA-00934": ("Group function is not allowed here",
                  "A group function such as COUNT or AVG appears in WHERE (or in GROUP BY). WHERE filters rows before "
                  "grouping; filter on group results in HAVING instead.", "t05"),
    "ORA-00936": ("Missing expression",
                  "An expression is expected but missing: often a trailing comma before FROM, an empty pair of "
                  "parentheses, or DISTINCT in the wrong place.", "t01"),
    "ORA-00937": ("Not a single-group group function",
                  "The SELECT list mixes a group function with a plain column but there is no GROUP BY. Either add the "
                  "plain columns to GROUP BY, or remove them.", "t05"),
    "ORA-00942": ("Table or view does not exist",
                  "The table name is misspelled, belongs to another schema you have no privilege on, or was dropped. "
                  "Unquoted names are stored in uppercase.", "t12"),
    "ORA-00947": ("Not enough values",
                  "Fewer values than columns: an INSERT VALUES list shorter than its column list, or a subquery with "
                  "too few columns.", "t09"),
    "ORA-00955": ("Name is already used by an existing object",
                  "Tables, views, sequences, private synonyms and other objects of one schema share a single namespace.", "t10"),
    "ORA-00957": ("Duplicate column name",
                  "A column name appears twice in a CREATE TABLE, a view, or an INSERT column list.", "t10"),
    "ORA-00979": ("Not a GROUP BY expression",
                  "Every expression in the SELECT list (and in HAVING and ORDER BY) that is not inside a group function "
                  "must appear in GROUP BY. Oracle never picks an arbitrary value for you.", "t05"),
    "ORA-00980": ("Synonym translation is no longer valid",
                  "The synonym points to an object that was dropped or renamed. Synonyms are not dropped with their target.", "t11"),
    "ORA-00998": ("Must name this expression with a column alias",
                  "CREATE TABLE ... AS SELECT and CREATE VIEW need a name for every expression that is not a plain column.", "t10"),
    "ORA-01031": ("Insufficient privileges",
                  "You do not hold the system or object privilege this statement needs.", "t13"),
    "ORA-01086": ("Savepoint never established",
                  "There is no such savepoint in the current transaction. A COMMIT, a ROLLBACK, or any DDL statement "
                  "(which commits) erases all savepoints.", "t09"),
    "ORA-01400": ("Cannot insert NULL",
                  "A NOT NULL column (or a primary key column) would get NULL: it is missing from the INSERT column list "
                  "and has no default, or the value is NULL. In Oracle an empty string '' is NULL too.", "t09"),
    "ORA-01407": ("Cannot update to NULL",
                  "An UPDATE would set a NOT NULL column to NULL, for example from a subquery that returns no row.", "t09"),
    "ORA-01427": ("Single-row subquery returns more than one row",
                  "A subquery used with =, <, > or in the SELECT list must return at most one row. Use IN, = ANY or "
                  "> ALL for several rows, or make the subquery return one row.", "t07"),
    "ORA-01430": ("Column being added already exists in table", "ALTER TABLE ... ADD names an existing column.", "t10"),
    "ORA-01438": ("Value larger than specified precision allowed for this column",
                  "The number has more digits before the decimal point than NUMBER(p,s) allows (p - s digits). Extra "
                  "digits after the decimal point are rounded instead.", "t10"),
    "ORA-01439": ("Column to be modified must be empty to change data type",
                  "ALTER TABLE ... MODIFY to another data type family works only when the column has no values.", "t10"),
    "ORA-01441": ("Cannot decrease column length because some value is too big",
                  "Existing data does not fit the new, smaller size.", "t10"),
    "ORA-01468": ("A predicate may reference only one outer-joined table",
                  "The old (+) syntax cannot mark both sides of one condition. Use FULL OUTER JOIN.", "t06"),
    "ORA-01476": ("Divisor is equal to zero",
                  "Oracle raises an error for division by zero instead of returning NULL. Use NULLIF(divisor, 0) to get NULL.", "t03"),
    "ORA-01722": ("Invalid number",
                  "A character value that is not a number was converted to NUMBER: usually implicitly, when a string is "
                  "compared with a number column, used in arithmetic, or in NVL/DECODE with a number first argument.", "t04"),
    "ORA-01732": ("Data manipulation operation not legal on this view",
                  "The view contains DISTINCT, GROUP BY, a group function, a set operator or ROWNUM, so it cannot be "
                  "changed through.", "t11"),
    "ORA-01733": ("Virtual column not allowed here",
                  "You tried to insert or update a view column that is an expression, not a base table column.", "t11"),
    "ORA-01735": ("Invalid ALTER TABLE option",
                  "The ALTER TABLE syntax is not Oracle's: for example ALTER COLUMN (use MODIFY), or SET NOT NULL "
                  "(use MODIFY col NOT NULL).", "t10"),
    "ORA-01779": ("Cannot modify a column which maps to a non key-preserved table",
                  "Through a join view you can only change a table whose primary key is still unique in the view.", "t11"),
    "ORA-01789": ("Query block has incorrect number of result columns",
                  "All queries combined with UNION, INTERSECT or MINUS must select the same number of columns. "
                  "Pad with NULL or a literal where a column is missing.", "t08"),
    "ORA-01790": ("Expression must have same data type as corresponding expression",
                  "Corresponding columns of a set operator must be in the same type family. Set operators do not "
                  "convert NUMBER to text implicitly; use TO_CHAR.", "t08"),
    "ORA-01830": ("Date format picture ends before converting entire input string",
                  "The string has more characters (often a time part) than the format model describes.", "t04"),
    "ORA-01839": ("Date not valid for month specified",
                  "The date does not exist: for example 31 February, often from adding INTERVAL '1' MONTH to a month end. "
                  "ADD_MONTHS adjusts to the last day of the month instead.", "t14"),
    "ORA-01843": ("Not a valid month", "The month part does not match the format model or the session's date language.", "t04"),
    "ORA-01847": ("Day of month must be between 1 and last day of month", "The day value is out of range.", "t04"),
    "ORA-01858": ("A non-numeric character was found where a numeric was expected",
                  "The string and the format model do not line up: compare them position by position.", "t04"),
    "ORA-01861": ("Literal does not match format string",
                  "A string was converted to a date with a format model (often the session's NLS_DATE_FORMAT) it does not "
                  "match. Use a DATE '2024-01-31' literal or TO_DATE with an explicit format.", "t04"),
    "ORA-02260": ("Table can have only one primary key", "Use UNIQUE constraints for other candidate keys.", "t10"),
    "ORA-02264": ("Name already used by an existing constraint", "Constraint names are unique within a schema.", "t10"),
    "ORA-02266": ("Unique/primary keys in table referenced by enabled foreign keys",
                  "You cannot TRUNCATE a parent table while enabled foreign keys reference it and child rows exist.", "t09"),
    "ORA-02270": ("No matching unique or primary key for this column list",
                  "A foreign key must reference a PRIMARY KEY or UNIQUE constraint on exactly those columns.", "t10"),
    "ORA-02287": ("Sequence number not allowed here",
                  "NEXTVAL and CURRVAL are not allowed in WHERE, GROUP BY, ORDER BY, DISTINCT queries, set operators, "
                  "subqueries or views.", "t11"),
    "ORA-02290": ("Check constraint violated", "The new or changed row fails a CHECK constraint.", "t10"),
    "ORA-02291": ("Integrity constraint violated - parent key not found",
                  "A foreign key value has no matching row in the parent table. Insert the parent first, or use an "
                  "existing key. NULL foreign keys are allowed.", "t10"),
    "ORA-02292": ("Integrity constraint violated - child record found",
                  "The parent row still has child rows and the foreign key has no ON DELETE CASCADE or SET NULL. Delete or "
                  "re-point the children first.", "t10"),
    "ORA-02449": ("Unique/primary keys in table referenced by foreign keys",
                  "DROP TABLE of a parent table needs CASCADE CONSTRAINTS, which drops the child foreign keys.", "t10"),
    "ORA-08002": ("Sequence CURRVAL is not yet defined in this session",
                  "CURRVAL returns the last NEXTVAL of your own session, so call NEXTVAL first.", "t11"),
    "ORA-12899": ("Value too large for column", "A string is longer than the column's maximum size.", "t10"),
    "ORA-25154": ("Column part of USING clause cannot have qualifier",
                  "With JOIN ... USING (col), refer to the join column without a table alias anywhere in the query.", "t06"),
    "ORA-25155": ("Column used in NATURAL join cannot have qualifier",
                  "With NATURAL JOIN, refer to the common columns without a table alias anywhere in the query.", "t06"),
    "ORA-25156": ("Old style outer join (+) cannot be used with ANSI joins",
                  "Do not combine (+) in WHERE with JOIN ... ON in the same query; write LEFT or RIGHT JOIN.", "t06"),
    "ORA-30076": ("Invalid extract field for extract source",
                  "EXTRACT can take only YEAR, MONTH and DAY from a DATE; HOUR, MINUTE and SECOND need a TIMESTAMP.", "t14"),
    "ORA-38104": ("Columns referenced in the ON clause cannot be updated",
                  "MERGE cannot update the columns used to match rows in its ON clause.", "t09"),
}

NOTES = {
    "t01": "topics/01-basic-select/notes.md", "t02": "topics/02-restricting-and-sorting/notes.md",
    "t03": "topics/03-single-row-functions/notes.md", "t04": "topics/04-conversion-and-conditional/notes.md",
    "t05": "topics/05-aggregation/notes.md", "t06": "topics/06-joins/notes.md",
    "t07": "topics/07-subqueries/notes.md", "t08": "topics/08-set-operators/notes.md",
    "t09": "topics/09-dml-and-transactions/notes.md", "t10": "topics/10-tables-and-constraints/notes.md",
    "t11": "topics/11-views-sequences-indexes/notes.md", "t12": "topics/12-data-dictionary/notes.md",
    "t13": "topics/13-user-access-control/notes.md", "t14": "topics/14-time-zones-and-intervals/notes.md",
    "t15": "topics/15-oracle-23ai/notes.md",
}


# --------------------------------------------------------------------------- hints

def _quoted_names(message):
    return re.findall(r'"([^"]+)"', message)


def _closest(name, candidates):
    match = difflib.get_close_matches(name.upper(), list(candidates), n=1, cutoff=0.75)
    return match[0] if match else None


def _select_items(sql):
    parts = sqltext.select_parts(sql)
    return (parts, sqltext.split_commas(parts["select"])) if parts else (None, [])


@cache
def overlay(lang):
    """{code: {"title", "explanation"}} of `lang`, read once; {} for English or without a file."""
    file = OVERLAY_DIR / f"{lang}.json"
    if lang == DEFAULT_LANGUAGE or not file.is_file():
        return {}
    try:
        data = json.loads(file.read_text("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        log.error("error explanation overlay %s left out: %s", file, exc)
        return {}
    return data if isinstance(data, dict) else {}


def _and(names, lang):
    return translate(lang, " and ").join(names)


def hint_00904(message, sql, ctx, lang="en"):
    names = _quoted_names(message)
    if not names:
        return None
    name = names[-1].upper()
    parts, items = _select_items(sql)
    if parts and name in {sqltext.item_alias(i) for i in items}:
        where = [c for c in ("where", "group", "having") if c in parts and re.search(rf"\b{re.escape(name)}\b", parts[c], re.I)]
        if where:
            clause = {"where": "WHERE", "group": "GROUP BY", "having": "HAVING"}[where[0]]
            return translate(lang, Msg.of(
                "{name} is a column alias from your SELECT list, used in {clause}. {clause} is evaluated before "
                "the SELECT list, so the alias does not exist there yet. Repeat the expression, or wrap the query "
                "in an inline view.", name=name, clause=clause))
    columns = ctx.columns()
    if columns is None:
        return None
    if any(name in cols for cols in columns.values()):
        if len(names) == 2:
            prefix = names[0].upper()
            owner = [t for t, cols in columns.items() if name in cols]
            return translate(lang, Msg.of(
                "The column {name} exists (in {tables}), but not in the table that {prefix} refers to, or {prefix} "
                "is not an alias or table name of this query block.", name=name, tables=", ".join(sorted(owner)),
                prefix=prefix))
        return translate(lang, Msg.of(
            "{name} is a column of {tables}. Is that table in this query block's FROM clause?",
            name=name, tables=", ".join(sorted(t for t, c in columns.items() if name in c))))
    all_columns = {c for cols in columns.values() for c in cols}
    suggestion = _closest(name, all_columns)
    if suggestion:
        tables = sorted(t for t, c in columns.items() if suggestion in c)
        return translate(lang, Msg.of("No column is called {name}. Did you mean {suggestion} ({tables})?",
                                      name=name, suggestion=suggestion, tables=", ".join(tables)))
    return translate(lang, Msg.of("No table in your schema has a column called {name}.", name=name))


def hint_00942(message, sql, ctx, lang="en"):
    columns = ctx.columns()
    if columns is None:
        return None
    known = set(columns) | {"DUAL"}
    words = [t for t in sqltext.tokens(sql) if t.kind in ("word", "ident")]
    for j, t in enumerate(words[:-1]):
        if t.upper in ("FROM", "JOIN", "INTO", "UPDATE", "TABLE"):
            name = words[j + 1].text.strip('"').upper()
            if name not in known and name not in ("SELECT",) and not name.startswith(("USER_", "ALL_", "DBA_", "V$")):
                suggestion = _closest(name, known)
                if suggestion:
                    return translate(lang, Msg.of("There is no table or view {name} in your schema. "
                                                  "Did you mean {suggestion}?", name=name, suggestion=suggestion))
                return translate(lang, Msg.of("There is no table or view {name} in your schema.", name=name))
    return None


def _non_grouped(sql):
    parts, items = _select_items(sql)
    if not parts:
        return None, []
    grouped = {sqltext.normalize(g) for g in sqltext.split_commas(parts.get("group", ""))}
    missing = []
    for item in items:
        expr = sqltext.item_expression(item)
        if sqltext.has_group_function(expr) or expr == "*" or re.fullmatch(r"('.*'|\d+(\.\d+)?|NULL)", expr, re.I | re.S):
            continue
        if sqltext.normalize(expr) not in grouped:
            missing.append(expr)
    return parts, missing


def hint_00979(message, sql, ctx, lang="en"):
    parts, missing = _non_grouped(sql)
    if missing:
        return ntranslate(lang, len(missing),
                          "In your SELECT list, {items} is not inside a group function and not in GROUP BY. "
                          "Add to GROUP BY, or aggregate it.",
                          "In your SELECT list, {items} are not inside a group function and not in GROUP BY. "
                          "Add to GROUP BY, or aggregate it.", items=", ".join(missing))
    if parts and "order" in parts:
        return translate(lang, Msg.of(
            "Check ORDER BY too: after GROUP BY it may only use grouped expressions or group functions."))
    return None


def hint_00937(message, sql, ctx, lang="en"):
    parts, missing = _non_grouped(sql)
    if parts and missing and "group" not in parts:
        return ntranslate(lang, len(missing),
                          "{items} is next to a group function without GROUP BY. Add GROUP BY {items} for one row "
                          "per group.",
                          "{items} are next to a group function without GROUP BY. Add GROUP BY {items} for one row "
                          "per group.", items=", ".join(missing))
    return None


def hint_00918(message, sql, ctx, lang="en"):
    parts = sqltext.select_parts(sql)
    columns = ctx.columns()
    if not parts or columns is None or "from" not in parts:
        return None
    tables = [r["table"] for r in sqltext.from_tables(parts["from"]) or []]
    if len(tables) < 2:
        return None
    shared = set.intersection(*(set(columns.get(t, [])) for t in set(tables))) if len(set(tables)) > 1 else set()
    unqualified = []
    toks = sqltext.tokens(sql)
    for j, t in enumerate(toks):
        if (t.kind == "word" and t.upper in shared and (j == 0 or toks[j - 1].text != ".")
                and t.upper not in unqualified):
            unqualified.append(t.upper)
    if unqualified:
        return translate(lang, Msg.of("{columns} exists in {tables}. Qualify it, for example with a table alias.",
                                      columns=", ".join(unqualified), tables=_and(sorted(set(tables)), lang)))
    return None


def hint_00933(message, sql, ctx, lang="en"):
    if re.search(r"\b(FROM|JOIN)\s+\w+\s+AS\s+\w+", sql, re.I):
        return translate(lang, Msg.of(
            "Oracle does not allow AS before a table alias: write FROM employees e, not FROM employees AS e."))
    compound = sqltext.split_set_operators(sql)
    if compound and any(re.search(r"\bORDER\s+BY\b", b, re.I) for b in compound[0][:-1]):
        return translate(lang, Msg.of(
            "ORDER BY may appear only once, after the last query of a UNION, INTERSECT or MINUS."))
    return None


def hint_00923(message, sql, ctx, lang="en"):
    parts = sqltext.select_parts(sql)
    select = parts["select"] if parts else ""
    if re.search(r"'[^']*'\s*(,|$)", select) and re.search(r"\s(AS\s+)?'[^']+'\s*(,|$)", select, re.I):
        return translate(lang, Msg.of(
            "A column alias goes in double quotes (\"Annual Pay\"); single quotes make a string literal."))
    return translate(lang, Msg.of(
        "Check the SELECT list for a missing comma between columns, and for aliases with spaces that need double quotes."))


def hint_00936(message, sql, ctx, lang="en"):
    if re.search(r",\s*FROM\b", sql, re.I):
        return translate(lang, Msg.of(
            "There is a comma right before FROM: remove the trailing comma from the SELECT list."))
    return None


def _constraint_hint(message, ctx, kind, lang="en"):
    m = re.search(r"\((\w+)\.(\w+)\)", message)
    info = ctx.constraint(m.group(2)) if m else None
    if not info:
        return None
    cols = ", ".join(f"{info['table']}.{c}" for c in info["columns"])
    name = m.group(2)
    if kind == "parent":
        return translate(lang, Msg.of(
            "{columns} must match an existing {parent_columns} in {parent} (constraint {name}).",
            columns=cols, parent_columns=", ".join(info["r_columns"]), parent=info["r_table"], name=name))
    if kind == "child":
        return translate(lang, Msg.of(
            "Rows in {table} still reference this row through {columns} (constraint {name}).",
            table=info["table"], columns=cols, name=name))
    if kind == "unique":
        return translate(lang, Msg.of("The value of {columns} already exists (constraint {name}).", columns=cols,
                                      name=name))
    if kind == "check":
        return translate(lang, Msg.of("The row fails CHECK ({condition}) on {table} (constraint {name}).",
                                      condition=info["condition"], table=info["table"], name=name))
    return None


def hint_01400(message, sql, ctx, lang="en"):
    names = _quoted_names(message)
    if len(names) >= 3:
        return translate(lang, Msg.of("{table}.{column} cannot be NULL: give it a value in your INSERT.",
                                      table=names[-2], column=names[-1]))
    return None


HINTS = {
    "ORA-00904": hint_00904,
    "ORA-00942": hint_00942,
    "ORA-00979": hint_00979,
    "ORA-00937": hint_00937,
    "ORA-00918": hint_00918,
    "ORA-00933": hint_00933,
    "ORA-00923": hint_00923,
    "ORA-00936": hint_00936,
    "ORA-01400": hint_01400,
    "ORA-02291": lambda m, s, c, lang="en": _constraint_hint(m, c, "parent", lang),
    "ORA-02292": lambda m, s, c, lang="en": _constraint_hint(m, c, "child", lang),
    "ORA-00001": lambda m, s, c, lang="en": _constraint_hint(m, c, "unique", lang),
    "ORA-02290": lambda m, s, c, lang="en": _constraint_hint(m, c, "check", lang),
}


def explain(error_text, sql, ctx, lang="en"):
    m = re.search(r"ORA-\d{5}", error_text or "")
    if not m or m.group(0) not in ERRORS:
        return None
    code = m.group(0)
    title, text, topic = ERRORS[code]
    translated = overlay(lang).get(code)
    translated = translated if isinstance(translated, dict) else {}
    title, text = translated.get("title") or title, translated.get("explanation") or text
    hint = None
    try:
        hint = HINTS[code](error_text, sql, ctx, lang) if code in HINTS else None
    except Exception:  # noqa: BLE001  a hint is optional; never let it break the error display
        hint = None
    return {"code": code, "title": title, "text": text, "hint": hint, "topic": topic, "note": NOTES[topic]}
