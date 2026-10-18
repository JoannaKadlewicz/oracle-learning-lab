"""Oracle Learning Lab: a local study app for 1Z0-071 (quiz, flashcards, SQL lab, graded exercises).

Run from the repository root:
    .venv/bin/python app/server.py            # http://127.0.0.1:8071

Connects to the learning schema ORASTUDY (default localhost:1521/ORAPDB1; see the STUDY_*
environment variables below). The password comes from STUDY_PASSWORD or ~/.orastudy_pwd.
Binds to 127.0.0.1 by default: the SQL lab executes whatever you type as ORASTUDY. In Docker it
binds 0.0.0.0 inside the container, and the port is published on the host's 127.0.0.1 only.
"""

import datetime
import decimal
import json
import os
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse

import oracledb

sys.path.insert(0, str(Path(__file__).resolve().parent))
import content  # noqa: E402
import engine  # noqa: E402
import errors  # noqa: E402
import report  # noqa: E402
import sqlviz  # noqa: E402

APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"
SQL_DIR = APP_DIR / "sql"
NOTES_DIR = APP_DIR / "notes"
STATE_FILE = Path(os.environ.get("STUDY_STATE_FILE", APP_DIR / "state" / "progress.json"))

HOST = os.environ.get("STUDY_HOST", "127.0.0.1")
PORT = int(os.environ.get("STUDY_PORT", "8071"))
DSN = os.environ.get("STUDY_DSN", "localhost:1521/ORAPDB1")
DB_USER = os.environ.get("STUDY_USER", "orastudy")
# Optional second database for the 1Z0-171 track (Oracle 23ai). Without it, both tracks use STUDY_DSN.
DSN_23AI = os.environ.get("STUDY_DSN_23AI")
DB_USER_23AI = os.environ.get("STUDY_USER_23AI", DB_USER)
PASSWORD_23AI = os.environ.get("STUDY_PASSWORD_23AI")
PASSWORD_FILE = Path(os.environ.get("STUDY_PASSWORD_FILE", Path.home() / ".orastudy_pwd"))

MAX_ROWS = 500
CALL_TIMEOUT_MS = 15000

oracledb.defaults.fetch_decimals = True


# --------------------------------------------------------------------------- state

_state_lock = threading.Lock()


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"attempts": {}, "cards": {}, "labs": {}, "settings": {}, "mocks": []}


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=1))
    tmp.replace(STATE_FILE)


def update_state(fn):
    with _state_lock:
        state = load_state()
        fn(state)
        save_state(state)
        return state


def exam_code(state):
    code = state.get("settings", {}).get("exam")
    return code if code in content.EXAMS else content.DEFAULT_EXAM


def track(state):
    """The content of the exam track chosen in the settings (1Z0-071 or 1Z0-171)."""
    return content.for_exam(exam_code(state))


def mock_exam(mock):
    return mock.get("exam") or content.DEFAULT_EXAM


def track_state(state):
    """The state as the engine sees it on the current track: only that track's mock exams."""
    code = exam_code(state)
    return {**state, "mocks": [m for m in state.get("mocks", []) if mock_exam(m) == code]}


def snapshot(state):
    """What the front end needs after every change: the raw state and the computed progress."""
    use_track_database(state)
    return {"state": state, "progress": {**engine.progress(track(state), track_state(state), time.time()),
                                         "exam": exam_code(state)}}


QUESTIONS_BY_ID = {q["id"]: q for q in content.QUESTIONS}
CARD_IDS = {c["id"] for c in content.FLASHCARDS}


def record_attempt(state, data, now):
    q = QUESTIONS_BY_ID[data["id"]]
    chosen = sorted({int(i) for i in data.get("chosen", []) if 0 <= int(i) < len(q["options"])})
    confidence = data.get("confidence") if data.get("confidence") in engine.CONFIDENCE else None
    state["attempts"].setdefault(q["id"], []).append({
        "t": now,
        "correct": chosen == sorted(q["answer"]),
        "chosen": chosen,
        "confidence": confidence,
        "mode": "exam" if data.get("mode") == "exam" else "practice",
    })


def record_card(state, data, now):
    if data["id"] not in CARD_IDS or data.get("rating") not in engine.CARD_RATINGS:
        raise ValueError("unknown card or rating")
    state["cards"].setdefault(data["id"], {"reviews": []})["reviews"].append([now, data["rating"]])


def find_mock(state, mock_id):
    mock = next((m for m in state.setdefault("mocks", []) if m["id"] == mock_id), None)
    if mock is None:
        raise ValueError("unknown mock exam")
    return mock


def start_mock(state, data, now):
    """Abandon any running mock and start a new one."""
    for mock in state.setdefault("mocks", []):
        if not mock["submitted"] and not mock["abandoned"]:
            mock["abandoned"] = now
    view = track(state)
    topics = [t for t in data.get("topics") or [] if t in view.TOPICS] or None
    count = int(data.get("count") or view.EXAM["questions"])
    minutes = int(data.get("minutes") or view.EXAM["minutes"])
    if not (1 <= count <= len(view.QUESTIONS) and 1 <= minutes <= 300):
        raise ValueError("count or minutes out of range")
    ids = [i for i in data.get("ids") or [] if i in {q["id"] for q in view.QUESTIONS}]
    if ids:  # a timed drill on chosen questions (for example only "Which error?" questions)
        pool = SimpleNamespace(**{**vars(view), "QUESTIONS": [q for q in view.QUESTIONS if q["id"] in set(ids)]})
        mock = engine.build_mock(pool, track_state(state), now, len(ids), minutes, None)
        mock["topics"] = sorted({q["topic"] for q in pool.QUESTIONS})
    else:
        mock = engine.build_mock(view, track_state(state), now, count, minutes, topics)
    mock["exam"] = view.CODE
    state["mocks"].append(mock)
    return mock


def answer_mock(state, data, now):
    mock = find_mock(state, data.get("mock_id"))
    if mock["submitted"] or mock["abandoned"] or now > engine.mock_deadline(mock) + engine.MOCK_GRACE:
        raise ValueError("this mock exam is over")
    if data.get("time_on"):
        mock["time_on"] = {qid: float(v) for qid, v in data["time_on"].items() if qid in mock["items"]}
    qid = data.get("id")
    if qid is None:
        return
    if qid not in mock["items"]:
        raise ValueError("question is not part of this mock exam")
    q = QUESTIONS_BY_ID[qid]
    answer = mock["answers"].setdefault(qid, {"chosen": [], "confidence": None, "flagged": False})
    if "chosen" in data:
        answer["chosen"] = sorted({int(i) for i in data["chosen"] if 0 <= int(i) < len(q["options"])})
        mock["events"].append([now, qid, answer["chosen"]])
    if "confidence" in data:
        answer["confidence"] = data["confidence"] if data["confidence"] in engine.CONFIDENCE else None
    if "flagged" in data:
        answer["flagged"] = bool(data["flagged"])


def submit_mock(state, mock, now):
    """Close a mock. Answered questions become exam-mode attempts. Unanswered ones score zero in the
    mock report but are not recorded as answers, so they stay fresh evidence for readiness."""
    mock["submitted"] = min(now, engine.mock_deadline(mock))
    for qid in mock["items"]:
        answer = mock["answers"].get(qid, {})
        if qid in QUESTIONS_BY_ID and answer.get("chosen"):
            record_attempt(state, {"id": qid, "chosen": answer.get("chosen", []),
                                   "confidence": answer.get("confidence"), "mode": "exam"}, mock["submitted"])


def finalize_expired(state, now):
    """Submit mocks whose time ran out while the app was closed."""
    for mock in state.get("mocks", []):
        if not mock["submitted"] and not mock["abandoned"] and now > engine.mock_deadline(mock) + engine.MOCK_GRACE:
            submit_mock(state, mock, now)


HISTORY_LIMIT = 100


def record_history(state, sql, result, now):
    """Remember a SQL lab run; re-running the same SQL moves it to the top."""
    if not sql.strip():
        return
    history = [h for h in state.setdefault("history", []) if h["sql"] != sql]
    entries = result.get("results", [])
    history.append({"t": now, "sql": sql, "statements": len(entries),
                    "errors": sum(1 for e in entries if e.get("type") == "error") if result.get("ok") else None})
    state["history"] = history[-HISTORY_LIMIT:]


def save_personal_note(title, sql, now):
    """Write a SQL snippet to app/notes/personal/ as Markdown; returns the note path."""
    title = " ".join(title.split())[:80] or "SQL note"
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:50] or "note"
    folder = NOTES_DIR / "personal"
    folder.mkdir(parents=True, exist_ok=True)
    day = datetime.date.fromtimestamp(now).isoformat()
    path = folder / f"{day}-{slug}.md"
    n = 2
    while path.exists():
        path = folder / f"{day}-{slug}-{n}.md"
        n += 1
    path.write_text(f"# {title}\n\nSaved from the SQL lab on {day}.\n\n```sql\n{sql.strip()}\n```\n")
    return str(path.relative_to(NOTES_DIR))


def record_settings(state, data):
    settings = state.setdefault("settings", {})
    if "exam_date" in data:
        if data["exam_date"]:
            datetime.date.fromisoformat(data["exam_date"])  # raises ValueError if invalid
        settings["exam_date"] = data["exam_date"] or None
    if "daily_minutes" in data:
        minutes = int(data["daily_minutes"])
        if not 5 <= minutes <= 480:
            raise ValueError("daily_minutes must be between 5 and 480")
        settings["daily_minutes"] = minutes
    if "exam" in data:
        if data["exam"] not in content.EXAMS:
            raise ValueError("exam must be one of " + ", ".join(content.EXAMS))
        settings["exam"] = data["exam"]


# --------------------------------------------------------------------------- SQL splitting

PLSQL_START = re.compile(
    r"^\s*(DECLARE|BEGIN|CREATE\s+(OR\s+REPLACE\s+)?((NON)?EDITIONABLE\s+)?"
    r"(PROCEDURE|FUNCTION|PACKAGE|TRIGGER|TYPE))\b",
    re.IGNORECASE,
)
CLIENT_COMMANDS = re.compile(
    r"^\s*(?:(?:PROMPT|COLUMN|COL|SPOOL|TTITLE|BTITLE|BREAK|COMPUTE|CLEAR|DEFINE|UNDEFINE|ACCEPT|PAUSE"
    r"|WHENEVER|SHOW|EXIT|QUIT|REM|REMARK)\b|SET\b(?!\s+(?:TRANSACTION|ROLE|CONSTRAINTS?)\b)|@)",
    re.IGNORECASE,
)
Q_QUOTE_CLOSE = {"[": "]", "{": "}", "(": ")", "<": ">"}


def strip_leading_comments(text):
    while True:
        stripped = text.lstrip()
        if stripped.startswith("--"):
            nl = stripped.find("\n")
            text = "" if nl < 0 else stripped[nl + 1:]
        elif stripped.startswith("/*"):
            end = stripped.find("*/")
            text = "" if end < 0 else stripped[end + 2:]
        else:
            return stripped


def split_statements(script):
    """Split a SQL*Plus-style script into statements.

    Handles quotes, q-quotes, comments, PL/SQL blocks terminated by '/',
    and single-line client commands such as PROMPT (returned with kind 'client').
    """
    statements = []
    buf = []
    n = len(script)
    i = 0
    in_plsql = False
    started = False  # a non-comment token has been seen in the current statement
    at_line_start = True

    def flush():
        nonlocal in_plsql, started
        text = "".join(buf).strip()
        if started and text:
            statements.append({"kind": "plsql" if in_plsql else "sql", "text": text})
        buf.clear()
        in_plsql = False
        started = False

    def begin_token(pos):
        nonlocal in_plsql, started
        if not started:
            started = True
            in_plsql = bool(PLSQL_START.match(script[pos:pos + 200]))

    while i < n:
        ch = script[i]

        if at_line_start:
            line_end = script.find("\n", i)
            next_i = n if line_end < 0 else line_end + 1
            line = script[i:] if line_end < 0 else script[i:line_end]
            if line.strip() == "/":
                flush()
                i = next_i
                continue
            if not started and CLIENT_COMMANDS.match(line):
                buf.clear()
                statements.append({"kind": "client", "text": line.strip()})
                i = next_i
                continue
            at_line_start = False

        if ch == "\n":
            buf.append(ch)
            i += 1
            at_line_start = True
            continue

        if script.startswith("--", i):
            end = script.find("\n", i)
            end = n if end < 0 else end
            buf.append(script[i:end])
            i = end
            continue

        if script.startswith("/*", i):
            end = script.find("*/", i + 2)
            end = n if end < 0 else end + 2
            buf.append(script[i:end])
            i = end
            continue

        if (ch in "qQ" and i + 2 < n and script[i + 1] == "'"
                and (i == 0 or not (script[i - 1].isalnum() or script[i - 1] in "_$#"))):
            begin_token(i)
            open_d = script[i + 2]
            close_d = Q_QUOTE_CLOSE.get(open_d, open_d)
            end = script.find(close_d + "'", i + 3)
            end = n if end < 0 else end + 2
            buf.append(script[i:end])
            i = end
            continue

        if ch in "'\"":
            begin_token(i)
            j = i + 1
            while j < n:
                if script[j] == ch:
                    if j + 1 < n and script[j + 1] == ch:
                        j += 2
                        continue
                    break
                j += 1
            buf.append(script[i:j + 1])
            i = j + 1
            continue

        if ch == ";" and not in_plsql:
            flush()
            i += 1
            continue

        if not ch.isspace():
            begin_token(i)
        buf.append(ch)
        i += 1

    flush()
    return statements


# --------------------------------------------------------------------------- execution

def password():
    # STUDY_PASSWORD (used by docker compose and CI) takes precedence over the password file.
    return os.environ.get("STUDY_PASSWORD") or PASSWORD_FILE.read_text().strip()


USE_23AI = False  # set from the exam track when STUDY_DSN_23AI is configured


def use_track_database(state):
    """Point the SQL lab and the grader at the 23ai database while studying for 1Z0-171."""
    global USE_23AI
    USE_23AI = bool(DSN_23AI) and exam_code(state) == "1Z0-171"


def connect():
    if USE_23AI:
        conn = oracledb.connect(user=DB_USER_23AI, password=PASSWORD_23AI or password(), dsn=DSN_23AI)
    else:
        conn = oracledb.connect(user=DB_USER, password=password(), dsn=DSN)
    conn.call_timeout = CALL_TIMEOUT_MS
    with conn.cursor() as cur:
        cur.execute("ALTER SESSION SET NLS_DATE_FORMAT = 'YYYY-MM-DD HH24:MI:SS'")
        cur.execute("ALTER SESSION SET NLS_TIMESTAMP_FORMAT = 'YYYY-MM-DD HH24:MI:SS.FF'")
    return conn


def to_json_value(value):
    if value is None:
        return None
    if isinstance(value, decimal.Decimal):
        return format(value.normalize(), "f") if value == value.to_integral() else str(value.normalize())
    if isinstance(value, datetime.datetime):
        if value.microsecond:
            return value.isoformat(sep=" ")
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, datetime.timedelta):
        return format_interval_ds(value)
    if isinstance(value, oracledb.IntervalYM):
        sign = "-" if value.years < 0 or value.months < 0 else "+"
        return f"{sign}{abs(value.years):02d}-{abs(value.months):02d}"
    if isinstance(value, datetime.date):
        return str(value)
    if isinstance(value, (bytes, bytearray)):
        return value.hex().upper()
    if hasattr(value, "read"):
        return value.read()
    if isinstance(value, float):
        return repr(value)
    return value if isinstance(value, (int, str, bool)) else str(value)


def format_interval_ds(delta):
    """Format like SQL*Plus shows INTERVAL DAY TO SECOND: +01 02:03:04 or -00 00:00:01.500000."""
    sign = "-" if delta < datetime.timedelta(0) else "+"
    delta = abs(delta)
    hours, rest = divmod(delta.seconds, 3600)
    minutes, seconds = divmod(rest, 60)
    text = f"{sign}{delta.days:02d} {hours:02d}:{minutes:02d}:{seconds:02d}"
    return text + (f".{delta.microseconds:06d}" if delta.microseconds else "")


# Thin-mode python-oracledb cannot fetch TIMESTAMP WITH TIME ZONE values that use a region
# name (DPY-3022), drops the offset of the others, and does not convert TIMESTAMP WITH LOCAL
# TIME ZONE to the session time zone. Such columns are converted to text by the database.
TEXT_FETCH_FORMATS = {
    oracledb.DB_TYPE_TIMESTAMP_TZ: "YYYY-MM-DD HH24:MI:SSXFF TZR",
    oracledb.DB_TYPE_TIMESTAMP_LTZ: "YYYY-MM-DD HH24:MI:SSXFF",
}


def fetchable_sql(cur, sql):
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


def execute_query(cur, sql):
    """Execute a SELECT or WITH query so that every column can be fetched."""
    wrapped = fetchable_sql(cur, sql)
    if wrapped is not sql:
        try:
            return cur.execute(wrapped)
        except oracledb.Error:
            pass  # e.g. FOR UPDATE inside the inline view; fall back to the plain query
    return cur.execute(sql)


def first_word(text):
    m = re.match(r"\s*(\w+)(\s+(\w+))?", strip_leading_comments(text))
    return (m.group(1).upper(), (m.group(3) or "").upper()) if m else ("", "")


def describe_success(text, rowcount):
    verb, obj = first_word(text)
    plural = "row" if rowcount == 1 else "rows"
    messages = {
        "INSERT": f"{rowcount} {plural} inserted.",
        "UPDATE": f"{rowcount} {plural} updated.",
        "DELETE": f"{rowcount} {plural} deleted.",
        "MERGE": f"{rowcount} {plural} merged.",
        "COMMIT": "Commit complete.",
        "ROLLBACK": "Rollback complete.",
        "SAVEPOINT": "Savepoint created.",
        "GRANT": "Grant succeeded.",
        "REVOKE": "Revoke succeeded.",
        "TRUNCATE": "Table truncated.",
        "FLASHBACK": "Flashback complete.",
        "COMMENT": "Comment created.",
    }
    if verb in messages:
        return messages[verb]
    if verb in ("CREATE", "ALTER", "DROP", "RENAME", "PURGE"):
        past = {"CREATE": "created", "ALTER": "altered", "DROP": "dropped", "RENAME": "renamed", "PURGE": "purged"}[verb]
        noun = obj.capitalize() if obj and obj not in ("OR", "GLOBAL", "PUBLIC", "UNIQUE") else "Object"
        return f"{noun} {past}."
    return "Statement executed."


def format_error(exc):
    text = str(exc).strip()
    lines = [ln for ln in text.splitlines() if not ln.startswith("Help:")]
    return "\n".join(lines)


BLOCKED_MESSAGE = ("ALTER USER is blocked: changing the ORASTUDY password would no longer match "
                   "the password file the app connects with.")


def is_blocked(text):
    return first_word(text) == ("ALTER", "USER")


def execute_one(cur, stmt):
    text = stmt["text"]
    if is_blocked(text):
        raise oracledb.DatabaseError(BLOCKED_MESSAGE)
    if stmt["kind"] == "plsql":
        sql = text
    else:
        sql = text.rstrip().rstrip(";")
    started = time.time()
    if stmt["kind"] == "sql" and first_word(sql)[0] in ("SELECT", "WITH"):
        execute_query(cur, sql)
    else:
        cur.execute(sql)
    elapsed = round((time.time() - started) * 1000)
    if cur.description:
        columns = [d[0] for d in cur.description]
        rows = cur.fetchmany(MAX_ROWS + 1)
        truncated = len(rows) > MAX_ROWS
        rows = [[to_json_value(v) for v in r] for r in rows[:MAX_ROWS]]
        return {"type": "rows", "columns": columns, "rows": rows, "truncated": truncated, "ms": elapsed}
    if stmt["kind"] == "plsql":
        return {"type": "message", "message": "PL/SQL procedure successfully completed.", "ms": elapsed}
    return {"type": "message", "message": describe_success(text, cur.rowcount), "ms": elapsed}


class SchemaContext:
    """Schema lookups for error hints, on an open connection."""

    def __init__(self, conn):
        self.conn = conn
        self._columns = None

    def columns(self):
        if self._columns is None:
            try:
                with self.conn.cursor() as cur:
                    cur.execute("SELECT table_name, column_name FROM user_tab_columns ORDER BY table_name, column_id")
                    self._columns = {}
                    for table, column in cur:
                        self._columns.setdefault(table, []).append(column)
            except oracledb.Error:
                return None
        return self._columns

    def constraint(self, name):
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


# Target table of a single-table DML statement, for the before/after view in the SQL lab.
DML_TARGET = re.compile(
    r"(?:INSERT\s+INTO|UPDATE|DELETE(?:\s+FROM)?|MERGE\s+INTO)\s+([A-Za-z][\w$#]*(?:\.[A-Za-z][\w$#]*)?)\b",
    re.IGNORECASE)
SNAPSHOT_LIMIT = 300
DDL_VERBS = {"CREATE", "ALTER", "DROP", "TRUNCATE", "RENAME", "GRANT", "REVOKE", "COMMENT", "PURGE", "FLASHBACK", "AUDIT"}


def table_snapshot(cur, table):
    """{rowid: row} of a small table, or None if it is too big or cannot be read."""
    try:
        execute_query(cur, f"SELECT ROWIDTOCHAR(t.ROWID) AS row_id__, t.* FROM {table} t WHERE ROWNUM <= {SNAPSHOT_LIMIT + 1}")
        columns = [d[0] for d in cur.description][1:]
        rows = {r[0]: [to_json_value(v) for v in r[1:]] for r in cur.fetchall()}
    except oracledb.Error:
        return None
    return None if len(rows) > SNAPSHOT_LIMIT else (columns, rows)


def row_changes(table, before, after):
    columns, old = before
    _, new = after
    return {
        "table": table.upper(),
        "columns": columns,
        "inserted": [new[k] for k in new if k not in old],
        "deleted": [old[k] for k in old if k not in new],
        "updated": [{"before": old[k], "after": new[k], "changed": [i for i, (x, y) in enumerate(zip(old[k], new[k])) if x != y]}
                    for k in old if k in new and new[k] != old[k]],
    }


class Transaction:
    """What the lab session has changed since the last commit, as shown after each statement."""

    def __init__(self):
        self.pending = 0
        self.savepoints = []  # [name, pending rows when it was set]

    def after(self, text, rowcount):
        verb, obj = first_word(text)
        note = None
        if verb in ("INSERT", "UPDATE", "DELETE", "MERGE"):
            self.pending += max(rowcount or 0, 0)
        elif verb == "SAVEPOINT":
            self.savepoints = [sp for sp in self.savepoints if sp[0] != obj] + [[obj, self.pending]]
        elif verb == "ROLLBACK":
            m = re.search(r"\bTO\s+(?:SAVEPOINT\s+)?(\w+)", strip_leading_comments(text), re.IGNORECASE)
            names = [sp[0] for sp in self.savepoints]
            if m and m.group(1).upper() in names:
                i = names.index(m.group(1).upper())
                self.pending = self.savepoints[i][1]
                self.savepoints = self.savepoints[:i + 1]
            elif not m:
                self.pending, self.savepoints = 0, []
        elif verb == "COMMIT" or verb in DDL_VERBS:
            if verb in DDL_VERBS and self.pending:
                note = f"This DDL statement committed {self.pending} pending row change{'s' if self.pending != 1 else ''} first."
            self.pending, self.savepoints = 0, []
        return {"pending": self.pending, "savepoints": [sp[0] for sp in self.savepoints], "note": note}


def run_script(script, keep_changes=False, stop_on_error=False, inspect=False):
    """Run a script in one transaction. With inspect (the SQL lab), DML results include the rows
    before and after, every result the transaction state, and errors an explanation."""
    results = []
    statements = split_statements(script)
    try:
        conn = connect()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "connect_error": format_error(exc), "results": []}
    tx = Transaction()
    ctx = SchemaContext(conn)
    try:
        with conn.cursor() as cur:
            for stmt in statements:
                entry = {"sql": stmt["text"]}
                if stmt["kind"] == "client":
                    m = re.match(r"\s*PROMPT\s?(.*)", stmt["text"], re.IGNORECASE)
                    if m:
                        entry.update({"type": "prompt", "message": m.group(1)})
                    else:
                        entry.update({"type": "skipped", "message": "SQL*Plus command ignored by the lab."})
                    results.append(entry)
                    continue
                target = DML_TARGET.match(strip_leading_comments(stmt["text"])) if inspect and stmt["kind"] == "sql" else None
                before = table_snapshot(cur, target.group(1)) if target else None
                try:
                    entry.update(execute_one(cur, stmt))
                except oracledb.Error as exc:
                    entry.update({"type": "error", "error": format_error(exc)})
                    if inspect:
                        entry["explain"] = errors.explain(entry["error"], stmt["text"], ctx)
                        entry["tx"] = tx.after("", 0)
                    results.append(entry)
                    if stop_on_error:
                        break
                    continue
                if inspect:
                    rowcount = cur.rowcount if entry["type"] == "message" else 0
                    entry["tx"] = tx.after(stmt["text"], rowcount)
                    after = table_snapshot(cur, target.group(1)) if before else None
                    if after:
                        entry["changes"] = row_changes(target.group(1), before, after)
                results.append(entry)
        if keep_changes:
            conn.commit()
        else:
            conn.rollback()
    finally:
        conn.close()
    return {"ok": True, "results": results, "kept": keep_changes}


def single_query(conn, sql):
    stmts = [s for s in split_statements(sql) if s["kind"] != "client"]
    if len(stmts) != 1:
        raise ValueError("Submit exactly one SELECT statement.")
    verb, _ = first_word(stmts[0]["text"])
    if verb not in ("SELECT", "WITH"):
        raise ValueError("Exercises expect a SELECT (or WITH ... SELECT) query.")
    with conn.cursor() as cur:
        execute_query(cur, stmts[0]["text"].rstrip().rstrip(";"))
        columns = [d[0] for d in cur.description]
        rows = [[to_json_value(v) for v in r] for r in cur.fetchmany(MAX_ROWS)]
    return columns, rows


def query_rows(conn, sql, limit=MAX_ROWS):
    with conn.cursor() as cur:
        execute_query(cur, sql)
        columns = [d[0] for d in cur.description]
        return columns, [[to_json_value(v) for v in r] for r in cur.fetchmany(limit)]


def visualize(sql):
    conn = connect()
    try:
        return sqlviz.visualize(conn, sql, query_rows)
    finally:
        conn.rollback()
        conn.close()


def normalize_rows(rows):
    return [tuple("\x00NULL" if v is None else str(v) for v in r) for r in rows]


# Lab kinds:
#   query  one SELECT, graded on its result
#   dml    DML statements, graded on the result of the lab's check query afterwards; rolled back
#   ddl    any statements, graded on the check query (usually over the data dictionary);
#          DDL commits, so the lab's cleanup script drops its objects before and after grading
DML_LAB_VERBS = {"INSERT", "UPDATE", "DELETE", "MERGE", "SAVEPOINT", "ROLLBACK", "SELECT", "WITH"}


def lab_kind(lab):
    return lab.get("kind", "query")


def run_cleanup(conn, lab):
    """Run the lab's cleanup statements, ignoring errors such as ORA-00942 (no such table)."""
    with conn.cursor() as cur:
        for stmt in split_statements(lab.get("cleanup", "")):
            try:
                cur.execute(stmt["text"].rstrip().rstrip(";"))
            except oracledb.Error:
                pass


def run_lab_statements(conn, lab, script):
    """Run a dml or ddl lab script, then return the lab's check query result."""
    stmts = [s for s in split_statements(script) if s["kind"] != "client"]
    if not stmts:
        raise ValueError("Write at least one statement.")
    with conn.cursor() as cur:
        for n, stmt in enumerate(stmts, 1):
            verb, _ = first_word(stmt["text"])
            if stmt["kind"] == "plsql":
                raise ValueError(f"Statement {n}: this exercise does not use PL/SQL blocks.")
            if is_blocked(stmt["text"]):
                raise ValueError(f"Statement {n}: {BLOCKED_MESSAGE}")
            if lab_kind(lab) == "dml" and verb not in DML_LAB_VERBS:
                raise ValueError(f"Statement {n}: this exercise expects DML only. {verb} is not allowed "
                                 "(COMMIT and DDL would make the changes permanent).")
            try:
                cur.execute(stmt["text"].rstrip().rstrip(";"))
            except oracledb.Error as exc:
                raise ValueError(f"Statement {n} failed: {format_error(exc)}") from exc
    return single_query(conn, lab["check"])


def lab_result(conn, lab, sql):
    """Return (columns, rows) that a lab submission is graded on, leaving no changes behind."""
    if lab_kind(lab) == "query":
        try:
            return single_query(conn, sql)
        finally:
            conn.rollback()
    if lab_kind(lab) == "ddl":
        run_cleanup(conn, lab)
    try:
        return run_lab_statements(conn, lab, sql)
    finally:
        conn.rollback()
        if lab_kind(lab) == "ddl":
            run_cleanup(conn, lab)


def grade(lab, sql):
    conn = connect()
    try:
        try:
            columns, rows = lab_result(conn, lab, sql)
        except (oracledb.Error, ValueError) as exc:
            message = format_error(exc)
            return {"passed": False, "error": message, "explain": errors.explain(message, sql, SchemaContext(conn))}
        exp_columns, exp_rows = lab_result(conn, lab, lab["solution"])
    finally:
        conn.close()
    return compare_results(lab, columns, rows, exp_columns, exp_rows)


def diff_rows(got, want, ordered):
    """One table showing your rows against the expected ones.

    Each row: {"status": ok | extra | missing | changed | moved, "cells", "expected"?, "diff"?}.
    A wrong row is paired with a missing row when at least half of their cells are equal, and
    shown as changed with the differing cells; rows in the wrong position are shown as moved.
    """
    g, w = normalize_rows(got), normalize_rows(want)
    if ordered and sorted(g) == sorted(w):
        return [{"status": "ok" if gi == wi else "moved", "cells": row} for row, gi, wi in zip(got, g, w)]
    remaining = {}
    for i, key in enumerate(w):
        remaining.setdefault(key, []).append(i)
    out = []
    for row, key in zip(got, g):
        if remaining.get(key):
            remaining[key].pop(0)
            out.append({"status": "ok", "cells": row})
        else:
            out.append({"status": "extra", "cells": row, "key": key})
    missing = [i for idxs in remaining.values() for i in idxs]
    for entry in out:
        if entry["status"] != "extra" or not missing:
            continue
        same = [(sum(a == b for a, b in zip(entry["key"], w[i])), i) for i in missing]
        score, best = max(same)
        if score * 2 >= len(entry["key"]) and score < len(entry["key"]):
            entry.update({"status": "changed", "expected": want[best],
                          "diff": [c for c, (a, b) in enumerate(zip(entry["key"], w[best])) if a != b]})
            missing.remove(best)
    for entry in out:
        entry.pop("key", None)
    return out + [{"status": "missing", "cells": want[i]} for i in sorted(missing)]


def compare_results(lab, columns, rows, exp_columns, exp_rows):
    feedback = []
    got, want = normalize_rows(rows), normalize_rows(exp_rows)
    passed = True
    if len(columns) != len(exp_columns):
        passed = False
        feedback.append(f"Expected {len(exp_columns)} columns ({', '.join(exp_columns)}), got {len(columns)}.")
    elif len(rows) != len(exp_rows):
        passed = False
        feedback.append(f"Expected {len(exp_rows)} rows, got {len(rows)}.")
    elif sorted(got) != sorted(want):
        passed = False
        missing = [r for r in want if r not in got]
        feedback.append("Row values differ from the expected result.")
        if missing:
            feedback.append("Example expected row not in your result: " + ", ".join("NULL" if v == "\x00NULL" else v for v in missing[0]))
    elif lab.get("ordered", True) and got != want:
        passed = False
        feedback.append("The right rows, but in the wrong order. Check ORDER BY and tie-breakers.")
    if passed and lab_kind(lab) == "query":
        expected_names = [c.strip().upper() for c in lab["columns"].split(",")]
        if [c.upper() for c in columns] != expected_names:
            feedback.append("Correct values. Column names differ from " + lab["columns"] + "; aliases are not graded.")

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


def schema_info():
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT c.table_name, c.column_name, c.data_type, c.data_length,
                          c.data_precision, c.data_scale, c.nullable
                   FROM   user_tab_columns c
                   JOIN   user_tables t ON t.table_name = c.table_name
                   ORDER  BY c.table_name, c.column_id"""
            )
            tables = {}
            for t, col, dtype, length, prec, scale, nullable in cur:
                if dtype in ("VARCHAR2", "CHAR", "NVARCHAR2", "NCHAR"):
                    shown = f"{dtype}({length})"
                elif dtype == "NUMBER" and prec is not None:
                    shown = f"NUMBER({prec}{',' + str(scale) if scale else ''})"
                else:
                    shown = dtype
                tables.setdefault(t, []).append({"name": col, "type": shown, "nullable": nullable == "Y"})
            cur.execute("SELECT table_name, num_rows FROM user_tables")
        return {"ok": True, "tables": [{"name": k, "columns": v} for k, v in tables.items()],
                "database": {"version": conn.version, "dsn": DSN_23AI if USE_23AI else DSN,
                             "major": int(conn.version.split(".")[0])}}
    finally:
        conn.close()


def reset_sample_data():
    cleanup = (SQL_DIR / "99_cleanup.sql").read_text()
    create = (SQL_DIR / "01_create_tables.sql").read_text()
    seed = (SQL_DIR / "02_seed_data.sql").read_text()
    log = []
    for name, script in (("cleanup", cleanup), ("create", create), ("seed", seed)):
        result = run_script(script, keep_changes=True)
        if not result["ok"]:
            return {"ok": False, "error": result["connect_error"]}
        errors = [r["error"] for r in result["results"] if r["type"] == "error"]
        if name != "cleanup" and errors:
            return {"ok": False, "error": f"{name}: {errors[0]}"}
        log.append(f"{name}: {len(result['results'])} statements")
    return {"ok": True, "log": log}


# --------------------------------------------------------------------------- notes

def list_notes():
    notes = []
    for path in sorted((NOTES_DIR / "docs").glob("*.md")):
        notes.append({"path": str(path.relative_to(NOTES_DIR)), "title": path.stem.replace("-", " ").capitalize()})
    for path in sorted((NOTES_DIR / "topics").glob("*/*.md")):
        notes.append({"path": str(path.relative_to(NOTES_DIR)), "title": f"{path.parent.name} / {path.stem}"})
    for path in sorted((NOTES_DIR / "topics").glob("*/*.sql")):
        if path.name != "solutions.sql":
            notes.append({"path": str(path.relative_to(NOTES_DIR)), "title": f"{path.parent.name} / {path.name}"})
    for path in sorted((NOTES_DIR / "personal").glob("*.md"), reverse=True):
        first = path.read_text().split("\n", 1)[0]
        title = first[2:].strip() if first.startswith("# ") else path.stem
        notes.append({"path": str(path.relative_to(NOTES_DIR)), "title": f"My notes / {title}"})
    return notes


def read_note(rel):
    allowed = {n["path"] for n in list_notes()}
    if rel not in allowed:
        return None
    return (NOTES_DIR / rel).read_text()


# --------------------------------------------------------------------------- HTTP

def public_content(state):
    view = track(state)
    return {
        "topics": view.TOPICS,
        "sections": view.SECTIONS,
        "objectives": view.OBJECTIVES,
        "exam": view.EXAM,
        "exams": content.EXAMS,
        "dual_database": bool(DSN_23AI),
        "questions": view.QUESTIONS,
        "flashcards": view.FLASHCARDS,
        "labs": view.LABS,
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "OracleLearningLab/1.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (self.command, self.path))

    def send_json(self, payload, status=200):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, html):
        body = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(length) or b"{}")

    def check_origin(self):
        origin = self.headers.get("Origin")
        host = self.headers.get("Host", "")
        if origin and urlparse(origin).netloc != host:
            self.send_json({"error": "Cross-origin requests are not allowed."}, 403)
            return False
        return True

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/content":
            return self.send_json(public_content(load_state()))
        if path == "/api/state":
            return self.send_json(load_state())
        if path == "/api/progress":
            return self.send_json(snapshot(update_state(lambda st: finalize_expired(st, time.time()))))
        if path == "/report":
            state = load_state()
            view, seen = track(state), track_state(state)
            html = report.render(view, seen, engine.progress(view, seen, time.time()), time.time())
            return self.send_html(html)
        if path == "/api/mock":
            from urllib.parse import parse_qs
            mock_id = parse_qs(urlparse(self.path).query).get("id", [""])[0]
            state = load_state()
            try:
                mock = find_mock(state, mock_id)
            except ValueError as exc:
                return self.send_json({"error": str(exc)}, 404)
            summary = engine.mock_report(content.for_exam(mock_exam(mock)), mock) if mock["submitted"] else None
            return self.send_json({"mock": mock, "report": summary})
        if path == "/api/schema":
            try:
                return self.send_json(schema_info())
            except Exception as exc:  # noqa: BLE001
                return self.send_json({"ok": False, "error": format_error(exc)})
        if path == "/api/notes":
            return self.send_json(list_notes())
        if path == "/api/note":
            from urllib.parse import parse_qs
            rel = parse_qs(urlparse(self.path).query).get("path", [""])[0]
            text = read_note(rel)
            if text is None:
                return self.send_json({"error": "Not found"}, 404)
            return self.send_json({"path": rel, "text": text})
        return self.serve_static(path)

    def do_POST(self):
        if not self.check_origin():
            return
        path = urlparse(self.path).path
        data = self.read_json()
        if path == "/api/run":
            sql = data.get("sql", "")
            result = run_script(sql, keep_changes=bool(data.get("keep")), inspect=True)
            state = update_state(lambda st: record_history(st, sql, result, time.time()))
            return self.send_json({**result, "history": state["history"]})
        if path == "/api/notes/save":
            if not str(data.get("sql", "")).strip():
                return self.send_json({"error": "Nothing to save"}, 400)
            return self.send_json({"path": save_personal_note(str(data.get("title", "")), data["sql"], time.time())})
        if path == "/api/visualize":
            try:
                return self.send_json(visualize(data.get("sql", "")))
            except Exception as exc:  # noqa: BLE001
                return self.send_json({"error": format_error(exc)})
        if path == "/api/grade":
            lab = next((l for l in content.LABS if l["id"] == data.get("id")), None)
            if not lab:
                return self.send_json({"error": "Unknown exercise"}, 404)
            try:
                result = grade(lab, data.get("sql", ""))
            except Exception as exc:  # noqa: BLE001
                return self.send_json({"passed": False, "error": format_error(exc)})

            def record(state):
                entry = state["labs"].setdefault(lab["id"], {"tries": 0, "passed": False})
                entry["tries"] += 1
                entry["passed"] = entry["passed"] or result["passed"]
                entry["last"] = data.get("sql", "")
                entry["t"] = time.time()

            update_state(record)
            return self.send_json(result)
        if path == "/api/attempt":
            if data.get("id") not in QUESTIONS_BY_ID:
                return self.send_json({"error": "Unknown question"}, 404)
            return self.send_json(snapshot(update_state(lambda st: record_attempt(st, data, time.time()))))
        if path == "/api/card":
            try:
                return self.send_json(snapshot(update_state(lambda st: record_card(st, data, time.time()))))
            except ValueError as exc:
                return self.send_json({"error": str(exc)}, 400)
        if path == "/api/lab-solution":
            if data.get("id") not in {lab["id"] for lab in content.LABS}:
                return self.send_json({"error": "Unknown exercise"}, 404)

            def seen(state):
                state["labs"].setdefault(data["id"], {"tries": 0, "passed": False})["solution_seen"] = True

            return self.send_json(snapshot(update_state(seen)))
        if path == "/api/settings":
            try:
                return self.send_json(snapshot(update_state(lambda st: record_settings(st, data))))
            except (ValueError, TypeError) as exc:
                return self.send_json({"error": str(exc)}, 400)
        if path == "/api/pick":
            topics = data.get("topics") or None
            state = load_state()
            view = track(state)
            count = max(1, min(int(data.get("count", 10)), len(view.QUESTIONS)))
            return self.send_json({"ids": engine.pick_questions(view, track_state(state), time.time(), count, topics)})
        if path.startswith("/api/mock/"):
            return self.handle_mock(path.rsplit("/", 1)[1], data)
        if path == "/api/reset-progress":
            def clear(state):
                kept = {"settings": state.get("settings", {}), "history": state.get("history", [])}
                state.clear()
                state.update({"attempts": {}, "cards": {}, "labs": {}, "mocks": [], **kept})

            return self.send_json(snapshot(update_state(clear)))
        if path == "/api/reset-data":
            return self.send_json(reset_sample_data())
        return self.send_json({"error": "Not found"}, 404)

    def handle_mock(self, action, data):
        now = time.time()
        result = {}

        def change(state):
            if action == "start":
                result["mock"] = start_mock(state, data, now)
            elif action == "answer":
                answer_mock(state, data, now)
            elif action == "submit":
                mock = find_mock(state, data.get("mock_id"))
                if mock["abandoned"]:
                    raise ValueError("this mock exam was abandoned")
                if data.get("time_on"):
                    mock["time_on"] = {q: float(v) for q, v in data["time_on"].items() if q in mock["items"]}
                if not mock["submitted"]:
                    submit_mock(state, mock, now)
                result["report"] = engine.mock_report(content.for_exam(mock_exam(mock)), mock)
            elif action == "abandon":
                mock = find_mock(state, data.get("mock_id"))
                if not mock["submitted"]:
                    mock["abandoned"] = now
            else:
                raise LookupError(action)

        try:
            state = update_state(change)
        except LookupError:
            return self.send_json({"error": "Not found"}, 404)
        except (ValueError, TypeError) as exc:
            return self.send_json({"error": str(exc)}, 400)
        if action == "answer":
            return self.send_json({"ok": True})
        return self.send_json({**snapshot(state), **result})

    def serve_static(self, path):
        if path in ("", "/"):
            path = "/index.html"
        target = (STATIC_DIR / path.lstrip("/")).resolve()
        if STATIC_DIR not in target.parents or not target.is_file():
            if Path(path).suffix:  # a missing asset is a 404, not the app shell
                return self.send_json({"error": "Not found"}, 404)
            target = STATIC_DIR / "index.html"
        types = {".html": "text/html", ".css": "text/css", ".js": "text/javascript", ".svg": "image/svg+xml"}
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", types.get(target.suffix, "application/octet-stream") + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    use_track_database(load_state())
    print(f"Oracle Learning Lab: http://{HOST}:{PORT}  (database {DB_USER}@{DSN}"
          + (f"; 1Z0-171 track: {DB_USER_23AI}@{DSN_23AI}" if DSN_23AI else "") + ")")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
