"""SQLite account stores, for local use. One connection per thread; writes that span several
statements run in an explicit transaction (BEGIN IMMEDIATE, so concurrent writers queue up)."""

from __future__ import annotations

import dataclasses
import json
import sqlite3
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from oracle_lab.accounts.memory import TAKEN
from oracle_lab.accounts.repositories import AppStores
from oracle_lab.auth.models import (
    AuditEvent,
    EmailTaken,
    Identity,
    LoginFlow,
    PracticeSchema,
    ResetToken,
    SessionRecord,
    User,
)
from oracle_lab.study.state import State, new_state

MIGRATIONS = [
    """
    CREATE TABLE users (
        id TEXT PRIMARY KEY,
        email TEXT NOT NULL UNIQUE,
        display_name TEXT NOT NULL,
        role TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at REAL NOT NULL,
        last_login_at REAL,
        password_changed_at REAL
    );
    CREATE TABLE identities (
        provider TEXT NOT NULL,
        subject TEXT NOT NULL,
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        password_hash TEXT,
        PRIMARY KEY (provider, subject)
    );
    CREATE INDEX identities_user ON identities(user_id);
    CREATE TABLE sessions (
        token_hash TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        csrf_token TEXT NOT NULL,
        created_at REAL NOT NULL,
        last_seen_at REAL NOT NULL,
        expires_at REAL NOT NULL,
        ip TEXT NOT NULL,
        user_agent TEXT NOT NULL,
        reauth_until REAL NOT NULL DEFAULT 0
    );
    CREATE INDEX sessions_user ON sessions(user_id);
    CREATE TABLE login_flows (
        id TEXT PRIMARY KEY,
        state TEXT NOT NULL,
        nonce TEXT NOT NULL,
        code_verifier TEXT NOT NULL,
        intent TEXT NOT NULL,
        user_id TEXT,
        next_path TEXT NOT NULL,
        expires_at REAL NOT NULL
    );
    CREATE TABLE reset_tokens (
        token_hash TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        created_by TEXT NOT NULL,
        expires_at REAL NOT NULL,
        used_at REAL
    );
    CREATE TABLE throttle (key TEXT NOT NULL, t REAL NOT NULL);
    CREATE INDEX throttle_key ON throttle(key, t);
    CREATE TABLE audit (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        t REAL NOT NULL,
        event TEXT NOT NULL,
        outcome TEXT NOT NULL,
        user_id TEXT,
        ip TEXT NOT NULL,
        user_agent TEXT NOT NULL,
        detail TEXT NOT NULL
    );
    CREATE INDEX audit_t ON audit(t);
    CREATE TABLE app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE practice_schemas (
        user_id TEXT NOT NULL,
        database_key TEXT NOT NULL,
        schema_name TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at REAL NOT NULL,
        error TEXT,
        PRIMARY KEY (user_id, database_key)
    );
    CREATE TABLE user_state (user_id TEXT PRIMARY KEY, doc TEXT NOT NULL);
    CREATE TABLE user_notes (
        user_id TEXT NOT NULL,
        name TEXT NOT NULL,
        title TEXT NOT NULL,
        body TEXT NOT NULL,
        created_at REAL NOT NULL,
        PRIMARY KEY (user_id, name)
    );
    """,
]

_UNIQUE_ERRORS = {"SQLITE_CONSTRAINT_UNIQUE", "SQLITE_CONSTRAINT_PRIMARYKEY"}


class _Holder:
    """A thread's connection; closed when the thread (and with it this object) goes away."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def __del__(self) -> None:
        try:
            self.conn.close()
        except sqlite3.Error:
            pass


class _Database:
    def __init__(self, path: Path):
        self.path = path
        self._local = threading.local()
        path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate()

    @property
    def conn(self) -> sqlite3.Connection:
        holder: _Holder | None = getattr(self._local, "holder", None)
        if holder is None:
            conn = sqlite3.connect(self.path, isolation_level=None, check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=5000")
            holder = self._local.holder = _Holder(conn)
        return holder.conn

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        conn = self.conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        conn.execute("COMMIT")

    def _migrate(self) -> None:
        conn = self.conn
        conn.execute("CREATE TABLE IF NOT EXISTS app_schema_version (version INTEGER NOT NULL)")
        for number, script in enumerate(MIGRATIONS, start=1):
            with self.tx():
                row = conn.execute("SELECT MAX(version) FROM app_schema_version").fetchone()
                if (row[0] or 0) >= number:
                    continue
                for statement in _statements(script):
                    conn.execute(statement)
                conn.execute("INSERT INTO app_schema_version (version) VALUES (?)", (number,))


def _statements(script: str) -> Iterator[str]:
    pending = ""
    for line in script.splitlines():
        pending += line + "\n"
        if sqlite3.complete_statement(pending):
            yield pending
            pending = ""


def _user(row: tuple[Any, ...]) -> User:
    return User(*row)


_USER_COLS = "id, email, display_name, role, status, created_at, last_login_at, password_changed_at"
_SESSION_COLS = "token_hash, user_id, csrf_token, created_at, last_seen_at, expires_at, ip, user_agent, reauth_until"
_FLOW_COLS = "id, state, nonce, code_verifier, intent, user_id, next_path, expires_at"
_SCHEMA_COLS = "user_id, database_key, schema_name, status, created_at, error"


class SqliteUsers:
    def __init__(self, db: _Database):
        self._db = db

    def add(self, user: User, identity: Identity) -> None:
        try:
            with self._db.tx() as conn:
                conn.execute(f"INSERT INTO users ({_USER_COLS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", dataclasses.astuple(user))
                self._insert_identity(conn, identity)
        except sqlite3.IntegrityError as e:
            raise EmailTaken(TAKEN) from e

    def get(self, user_id: str) -> User | None:
        row = self._db.conn.execute(f"SELECT {_USER_COLS} FROM users WHERE id = ?", (user_id,)).fetchone()
        return _user(row) if row else None

    def by_email(self, email: str) -> User | None:
        row = self._db.conn.execute(f"SELECT {_USER_COLS} FROM users WHERE email = ?", (email,)).fetchone()
        return _user(row) if row else None

    def by_identity(self, provider: str, subject: str) -> User | None:
        row = self._db.conn.execute(
            "SELECT u.id, u.email, u.display_name, u.role, u.status, u.created_at, u.last_login_at, u.password_changed_at "
            "FROM users u JOIN identities i ON i.user_id = u.id WHERE i.provider = ? AND i.subject = ?",
            (provider, subject),
        ).fetchone()
        return _user(row) if row else None

    def identities(self, user_id: str) -> list[Identity]:
        rows = self._db.conn.execute(
            "SELECT provider, subject, user_id, password_hash FROM identities WHERE user_id = ? ORDER BY rowid", (user_id,)
        )
        return [Identity(*r) for r in rows]

    def add_identity(self, identity: Identity) -> None:
        try:
            with self._db.tx() as conn:
                self._insert_identity(conn, identity)
        except sqlite3.IntegrityError as e:
            if e.sqlite_errorname not in _UNIQUE_ERRORS:
                raise
            raise EmailTaken(TAKEN) from e

    def remove_identity(self, user_id: str, provider: str) -> None:
        self._db.conn.execute("DELETE FROM identities WHERE user_id = ? AND provider = ?", (user_id, provider))

    def update(self, user: User) -> None:
        self._db.conn.execute(
            "UPDATE users SET email = ?, display_name = ?, role = ?, status = ?, created_at = ?, last_login_at = ?, "
            "password_changed_at = ? WHERE id = ?",
            (*dataclasses.astuple(user)[1:], user.id),
        )

    def set_password(self, user_id: str, password_hash: str, changed_at: float) -> None:
        with self._db.tx() as conn:
            done = conn.execute("UPDATE users SET password_changed_at = ? WHERE id = ?", (changed_at, user_id))
            if done.rowcount:
                conn.execute(
                    "UPDATE identities SET password_hash = ? WHERE user_id = ? AND provider = 'password'",
                    (password_hash, user_id),
                )

    def delete(self, user_id: str) -> None:
        self._db.conn.execute("DELETE FROM users WHERE id = ?", (user_id,))

    def all(self) -> list[User]:
        return [_user(r) for r in self._db.conn.execute(f"SELECT {_USER_COLS} FROM users ORDER BY rowid")]

    def count(self) -> int:
        return self._db.conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    @staticmethod
    def _insert_identity(conn: sqlite3.Connection, identity: Identity) -> None:
        conn.execute(
            "INSERT INTO identities (provider, subject, user_id, password_hash) VALUES (?, ?, ?, ?)",
            dataclasses.astuple(identity),
        )


class SqliteSessions:
    def __init__(self, db: _Database):
        self._db = db

    def add(self, rec: SessionRecord) -> None:
        cols = _SESSION_COLS.split(", ")
        updates = ", ".join(f"{c} = excluded.{c}" for c in cols[1:])
        self._db.conn.execute(
            f"INSERT INTO sessions ({_SESSION_COLS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            f"ON CONFLICT(token_hash) DO UPDATE SET {updates}",
            dataclasses.astuple(rec),
        )

    def get(self, token_hash: str) -> SessionRecord | None:
        row = self._db.conn.execute(f"SELECT {_SESSION_COLS} FROM sessions WHERE token_hash = ?", (token_hash,)).fetchone()
        return SessionRecord(*row) if row else None

    def touch(self, token_hash: str, t: float) -> None:
        self._db.conn.execute("UPDATE sessions SET last_seen_at = ? WHERE token_hash = ?", (t, token_hash))

    def set_reauth(self, token_hash: str, until: float) -> None:
        self._db.conn.execute("UPDATE sessions SET reauth_until = ? WHERE token_hash = ?", (until, token_hash))

    def delete(self, token_hash: str) -> None:
        self._db.conn.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))

    def delete_for_user(self, user_id: str, keep: str | None = None) -> None:
        self._db.conn.execute("DELETE FROM sessions WHERE user_id = ? AND (? IS NULL OR token_hash != ?)", (user_id, keep, keep))

    def for_user(self, user_id: str) -> list[SessionRecord]:
        rows = self._db.conn.execute(f"SELECT {_SESSION_COLS} FROM sessions WHERE user_id = ? ORDER BY rowid", (user_id,))
        return [SessionRecord(*r) for r in rows]

    def purge(self, now: float) -> None:
        self._db.conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))


class SqliteFlows:
    def __init__(self, db: _Database):
        self._db = db

    def add(self, flow: LoginFlow) -> None:
        cols = _FLOW_COLS.split(", ")
        updates = ", ".join(f"{c} = excluded.{c}" for c in cols[1:])
        self._db.conn.execute(
            f"INSERT INTO login_flows ({_FLOW_COLS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET {updates}",
            dataclasses.astuple(flow),
        )

    def take(self, flow_id: str) -> LoginFlow | None:
        with self._db.tx() as conn:
            row = conn.execute(f"SELECT {_FLOW_COLS} FROM login_flows WHERE id = ?", (flow_id,)).fetchone()
            if row:
                conn.execute("DELETE FROM login_flows WHERE id = ?", (flow_id,))
        return LoginFlow(*row) if row else None

    def purge(self, now: float) -> None:
        self._db.conn.execute("DELETE FROM login_flows WHERE expires_at <= ?", (now,))


class SqliteResets:
    def __init__(self, db: _Database):
        self._db = db

    def add(self, tok: ResetToken) -> None:
        self._db.conn.execute(
            "INSERT INTO reset_tokens (token_hash, user_id, created_by, expires_at, used_at) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(token_hash) DO UPDATE SET user_id = excluded.user_id, created_by = excluded.created_by, "
            "expires_at = excluded.expires_at, used_at = excluded.used_at",
            dataclasses.astuple(tok),
        )

    def take(self, token_hash: str, now: float) -> ResetToken | None:
        with self._db.tx() as conn:
            done = conn.execute(
                "UPDATE reset_tokens SET used_at = ? WHERE token_hash = ? AND used_at IS NULL AND expires_at > ?",
                (now, token_hash, now),
            )
            if not done.rowcount:
                return None
            row = conn.execute(
                "SELECT token_hash, user_id, created_by, expires_at, used_at FROM reset_tokens WHERE token_hash = ?",
                (token_hash,),
            ).fetchone()
        return ResetToken(*row)


class SqliteThrottle:
    def __init__(self, db: _Database):
        self._db = db

    def record(self, key: str, t: float) -> None:
        self._db.conn.execute("INSERT INTO throttle (key, t) VALUES (?, ?)", (key, t))

    def count_since(self, key: str, since: float) -> int:
        return self._db.conn.execute("SELECT COUNT(*) FROM throttle WHERE key = ? AND t >= ?", (key, since)).fetchone()[0]

    def last(self, key: str) -> float | None:
        return self._db.conn.execute("SELECT MAX(t) FROM throttle WHERE key = ?", (key,)).fetchone()[0]

    def clear(self, key: str) -> None:
        self._db.conn.execute("DELETE FROM throttle WHERE key = ?", (key,))

    def purge(self, before: float) -> None:
        self._db.conn.execute("DELETE FROM throttle WHERE t < ?", (before,))


class SqliteAudit:
    def __init__(self, db: _Database):
        self._db = db

    def add(self, event: AuditEvent) -> None:
        self._db.conn.execute(
            "INSERT INTO audit (t, event, outcome, user_id, ip, user_agent, detail) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (event.t, event.event, event.outcome, event.user_id, event.ip, event.user_agent, json.dumps(event.detail)),
        )

    def recent(self, limit: int = 200, event: str | None = None, user_id: str | None = None) -> list[AuditEvent]:
        rows = self._db.conn.execute(
            "SELECT t, event, outcome, user_id, ip, user_agent, detail FROM audit "
            "WHERE (? IS NULL OR event = ?) AND (? IS NULL OR user_id = ?) ORDER BY t DESC, id DESC LIMIT ?",
            (event, event, user_id, user_id, limit),
        )
        return [AuditEvent(*r[:6], json.loads(r[6])) for r in rows]

    def purge(self, before: float) -> None:
        self._db.conn.execute("DELETE FROM audit WHERE t < ?", (before,))


class SqliteSettings:
    def __init__(self, db: _Database):
        self._db = db

    def get(self, key: str) -> str | None:
        row = self._db.conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def set(self, key: str, value: str) -> None:
        self._db.conn.execute(
            "INSERT INTO app_settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


class SqliteSchemas:
    def __init__(self, db: _Database):
        self._db = db

    def get(self, user_id: str, database_key: str) -> PracticeSchema | None:
        row = self._db.conn.execute(
            f"SELECT {_SCHEMA_COLS} FROM practice_schemas WHERE user_id = ? AND database_key = ?", (user_id, database_key)
        ).fetchone()
        return PracticeSchema(*row) if row else None

    def put(self, rec: PracticeSchema) -> None:
        self._db.conn.execute(
            f"INSERT INTO practice_schemas ({_SCHEMA_COLS}) VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(user_id, database_key) DO UPDATE SET schema_name = excluded.schema_name, "
            "status = excluded.status, created_at = excluded.created_at, error = excluded.error",
            dataclasses.astuple(rec),
        )

    def for_user(self, user_id: str) -> list[PracticeSchema]:
        rows = self._db.conn.execute(f"SELECT {_SCHEMA_COLS} FROM practice_schemas WHERE user_id = ? ORDER BY rowid", (user_id,))
        return [PracticeSchema(*r) for r in rows]

    def delete_for_user(self, user_id: str) -> None:
        self._db.conn.execute("DELETE FROM practice_schemas WHERE user_id = ?", (user_id,))

    def all(self) -> list[PracticeSchema]:
        return [PracticeSchema(*r) for r in self._db.conn.execute(f"SELECT {_SCHEMA_COLS} FROM practice_schemas ORDER BY rowid")]


class SqliteState:
    """One user's study state as a JSON document."""

    def __init__(self, db: _Database, user_id: str):
        self._db = db
        self._user_id = user_id

    def load(self) -> State:
        return self._read(self._db.conn)

    @contextmanager
    def transaction(self) -> Iterator[State]:
        with self._db.tx() as conn:
            state = self._read(conn)
            yield state
            conn.execute(
                "INSERT INTO user_state (user_id, doc) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET doc = excluded.doc",
                (self._user_id, json.dumps(state)),
            )

    def _read(self, conn: sqlite3.Connection) -> State:
        row = conn.execute("SELECT doc FROM user_state WHERE user_id = ?", (self._user_id,)).fetchone()
        return json.loads(row[0]) if row else new_state()


class SqliteUserStates:
    def __init__(self, db: _Database):
        self._db = db

    def for_user(self, user_id: str) -> SqliteState:
        return SqliteState(self._db, user_id)

    def delete(self, user_id: str) -> None:
        self._db.conn.execute("DELETE FROM user_state WHERE user_id = ?", (user_id,))


class SqliteNotes:
    """One user's personal notes; entries() lists them by name, descending (like FileNotes)."""

    def __init__(self, db: _Database, user_id: str):
        self._db = db
        self._user_id = user_id

    def entries(self) -> list[tuple[str, str]]:
        rows = self._db.conn.execute("SELECT name, title FROM user_notes WHERE user_id = ? ORDER BY name DESC", (self._user_id,))
        return [(name, title) for name, title in rows]

    def read(self, name: str) -> str | None:
        row = self._db.conn.execute(
            "SELECT body FROM user_notes WHERE user_id = ? AND name = ?", (self._user_id, name)
        ).fetchone()
        return row[0] if row else None

    def add(self, stem: str, title: str, text: str) -> str:
        with self._db.tx() as conn:
            name, n = f"{stem}.md", 2
            while conn.execute("SELECT 1 FROM user_notes WHERE user_id = ? AND name = ?", (self._user_id, name)).fetchone():
                name = f"{stem}-{n}.md"
                n += 1
            conn.execute(
                "INSERT INTO user_notes (user_id, name, title, body, created_at) VALUES (?, ?, ?, ?, ?)",
                (self._user_id, name, title, text, time.time()),
            )
        return name


class SqliteUserNotes:
    def __init__(self, db: _Database):
        self._db = db

    def for_user(self, user_id: str) -> SqliteNotes:
        return SqliteNotes(self._db, user_id)

    def delete(self, user_id: str) -> None:
        self._db.conn.execute("DELETE FROM user_notes WHERE user_id = ?", (user_id,))


def sqlite_stores(path: Path) -> AppStores:
    db = _Database(Path(path))
    return AppStores(
        users=SqliteUsers(db),
        sessions=SqliteSessions(db),
        flows=SqliteFlows(db),
        resets=SqliteResets(db),
        throttle=SqliteThrottle(db),
        audit=SqliteAudit(db),
        settings=SqliteSettings(db),
        schemas=SqliteSchemas(db),
        states=SqliteUserStates(db),
        notes=SqliteUserNotes(db),
    )
