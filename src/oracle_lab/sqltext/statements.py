"""Split SQL*Plus-style scripts into statements, and classify statements by their first words."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from oracle_lab.sqltext.clauses import Q_QUOTE_CLOSE

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
QUERY_VERBS = frozenset({"SELECT", "WITH"})


class StatementKind(StrEnum):
    SQL = "sql"
    PLSQL = "plsql"
    CLIENT = "client"  # a SQL*Plus command such as PROMPT, handled by the lab and never sent to Oracle


@dataclass(frozen=True, slots=True)
class Statement:
    kind: StatementKind
    text: str

    @property
    def verb(self) -> str:
        return first_words(self.text)[0]

    @property
    def is_query(self) -> bool:
        return self.kind is StatementKind.SQL and self.verb in QUERY_VERBS

    def executable_text(self) -> str:
        """The text to send to Oracle: SQL without its terminating semicolon, PL/SQL as written."""
        return self.text if self.kind is StatementKind.PLSQL else without_terminator(self.text)


def without_terminator(sql: str) -> str:
    return sql.rstrip().rstrip(";")


def strip_leading_comments(text: str) -> str:
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


def first_words(text: str) -> tuple[str, str]:
    """The first two words of a statement in upper case, after comments: ("CREATE", "TABLE")."""
    m = re.match(r"\s*(\w+)(\s+(\w+))?", strip_leading_comments(text))
    return (m.group(1).upper(), (m.group(3) or "").upper()) if m else ("", "")


def executable_statements(script: str) -> list[Statement]:
    """The statements of a script that go to the database (SQL*Plus commands left out)."""
    return [s for s in split_statements(script) if s.kind is not StatementKind.CLIENT]


def split_statements(script: str) -> list[Statement]:
    """Split a SQL*Plus-style script into statements.

    Handles quotes, q-quotes, comments, PL/SQL blocks terminated by '/', and single-line
    client commands such as PROMPT (returned with kind CLIENT).
    """
    return _Splitter(script).split()


class _Splitter:
    """One pass over the script; the state of the statement being collected lives on the instance."""

    def __init__(self, script: str):
        self.script = script
        self.statements: list[Statement] = []
        self.buf: list[str] = []
        self.in_plsql = False
        self.started = False  # a non-comment token has been seen in the current statement

    def flush(self) -> None:
        text = "".join(self.buf).strip()
        if self.started and text:
            self.statements.append(Statement(StatementKind.PLSQL if self.in_plsql else StatementKind.SQL, text))
        self.buf.clear()
        self.in_plsql = False
        self.started = False

    def begin_token(self, pos: int) -> None:
        if not self.started:
            self.started = True
            self.in_plsql = bool(PLSQL_START.match(self.script[pos:pos + 200]))

    def split(self) -> list[Statement]:  # noqa: C901 - a hand-written scanner reads best as one loop
        script, buf = self.script, self.buf
        n = len(script)
        i = 0
        at_line_start = True

        while i < n:
            ch = script[i]

            if at_line_start:
                line_end = script.find("\n", i)
                next_i = n if line_end < 0 else line_end + 1
                line = script[i:] if line_end < 0 else script[i:line_end]
                if line.strip() == "/":
                    self.flush()
                    i = next_i
                    continue
                if not self.started and CLIENT_COMMANDS.match(line):
                    buf.clear()
                    self.statements.append(Statement(StatementKind.CLIENT, line.strip()))
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
                self.begin_token(i)
                open_d = script[i + 2]
                close_d = Q_QUOTE_CLOSE.get(open_d, open_d)
                end = script.find(close_d + "'", i + 3)
                end = n if end < 0 else end + 2
                buf.append(script[i:end])
                i = end
                continue

            if ch in "'\"":
                self.begin_token(i)
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

            if ch == ";" and not self.in_plsql:
                self.flush()
                i += 1
                continue

            if not ch.isspace():
                self.begin_token(i)
            buf.append(ch)
            i += 1

        self.flush()
        return self.statements
