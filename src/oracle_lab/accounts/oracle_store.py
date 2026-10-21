"""Oracle account stores, for hosts without a persistent disk. Every operation takes its own pooled
session and commits explicitly; the per-user state document is locked with SELECT ... FOR UPDATE.

Table names carry an `app_` prefix (users, sessions, ... and audit are reserved or too generic in
Oracle), the same one for all of them. LAB_STATE/LAB_NOTES of the single-user app are left alone.
Oracle stores an empty string as NULL, so the text columns that may be empty are nullable here and
read back as "".
"""

from __future__ import annotations

import dataclasses
import json
import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import oracledb

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
from oracle_lab.database.connection import Database, session
from oracle_lab.study.state import State, new_state

log = logging.getLogger(__name__)

# One list of statements per version; times are BINARY_DOUBLE so they come back as float.
MIGRATIONS: list[list[str]] = [
    [
        """CREATE TABLE app_users (
            seq NUMBER GENERATED ALWAYS AS IDENTITY,
            id VARCHAR2(64 CHAR) CONSTRAINT app_users_pk PRIMARY KEY,
            email VARCHAR2(320 CHAR) NOT NULL CONSTRAINT app_users_email_uq UNIQUE,
            display_name VARCHAR2(200 CHAR),
            role VARCHAR2(20 CHAR) NOT NULL,
            status VARCHAR2(20 CHAR) NOT NULL,
            created_at BINARY_DOUBLE NOT NULL,
            last_login_at BINARY_DOUBLE,
            password_changed_at BINARY_DOUBLE)""",
        """CREATE TABLE app_identities (
            seq NUMBER GENERATED ALWAYS AS IDENTITY,
            provider VARCHAR2(20 CHAR) NOT NULL,
            subject VARCHAR2(320 CHAR) NOT NULL,
            user_id VARCHAR2(64 CHAR) NOT NULL CONSTRAINT app_identities_user_fk REFERENCES app_users(id) ON DELETE CASCADE,
            password_hash VARCHAR2(500 CHAR),
            CONSTRAINT app_identities_pk PRIMARY KEY (provider, subject))""",
        "CREATE INDEX app_identities_user ON app_identities(user_id)",
        """CREATE TABLE app_sessions (
            seq NUMBER GENERATED ALWAYS AS IDENTITY,
            token_hash VARCHAR2(128 CHAR) CONSTRAINT app_sessions_pk PRIMARY KEY,
            user_id VARCHAR2(64 CHAR) NOT NULL CONSTRAINT app_sessions_user_fk REFERENCES app_users(id) ON DELETE CASCADE,
            csrf_token VARCHAR2(128 CHAR) NOT NULL,
            created_at BINARY_DOUBLE NOT NULL,
            last_seen_at BINARY_DOUBLE NOT NULL,
            expires_at BINARY_DOUBLE NOT NULL,
            ip VARCHAR2(100 CHAR),
            user_agent VARCHAR2(1000 CHAR),
            reauth_until BINARY_DOUBLE DEFAULT 0 NOT NULL)""",
        "CREATE INDEX app_sessions_user ON app_sessions(user_id)",
        """CREATE TABLE app_login_flows (
            id VARCHAR2(128 CHAR) CONSTRAINT app_login_flows_pk PRIMARY KEY,
            state VARCHAR2(256 CHAR) NOT NULL,
            nonce VARCHAR2(256 CHAR) NOT NULL,
            code_verifier VARCHAR2(256 CHAR) NOT NULL,
            intent VARCHAR2(20 CHAR) NOT NULL,
            user_id VARCHAR2(64 CHAR),
            next_path VARCHAR2(1000 CHAR),
            expires_at BINARY_DOUBLE NOT NULL)""",
        """CREATE TABLE app_reset_tokens (
            token_hash VARCHAR2(128 CHAR) CONSTRAINT app_reset_tokens_pk PRIMARY KEY,
            user_id VARCHAR2(64 CHAR) NOT NULL,
            created_by VARCHAR2(64 CHAR) NOT NULL,
            expires_at BINARY_DOUBLE NOT NULL,
            used_at BINARY_DOUBLE)""",
        "CREATE TABLE app_throttle (key VARCHAR2(500 CHAR) NOT NULL, t BINARY_DOUBLE NOT NULL)",
        "CREATE INDEX app_throttle_key ON app_throttle(key, t)",
        """CREATE TABLE app_audit (
            id NUMBER GENERATED ALWAYS AS IDENTITY CONSTRAINT app_audit_pk PRIMARY KEY,
            t BINARY_DOUBLE NOT NULL,
            event VARCHAR2(100 CHAR) NOT NULL,
            outcome VARCHAR2(20 CHAR) NOT NULL,
            user_id VARCHAR2(64 CHAR),
            ip VARCHAR2(100 CHAR),
            user_agent VARCHAR2(1000 CHAR),
            detail CLOB NOT NULL CONSTRAINT app_audit_detail_json CHECK (detail IS JSON))""",
        "CREATE INDEX app_audit_t ON app_audit(t)",
        "CREATE TABLE app_settings (key VARCHAR2(200 CHAR) CONSTRAINT app_settings_pk PRIMARY KEY, value VARCHAR2(1000 CHAR))",
        """CREATE TABLE app_practice_schemas (
            seq NUMBER GENERATED ALWAYS AS IDENTITY,
            user_id VARCHAR2(64 CHAR) NOT NULL CONSTRAINT app_practice_schemas_user_fk REFERENCES app_users(id) ON DELETE CASCADE,
            database_key VARCHAR2(100 CHAR) NOT NULL,
            schema_name VARCHAR2(128 CHAR) NOT NULL,
            status VARCHAR2(20 CHAR) NOT NULL,
            created_at BINARY_DOUBLE NOT NULL,
            error VARCHAR2(1000 CHAR),
            CONSTRAINT app_practice_schemas_pk PRIMARY KEY (user_id, database_key))""",
        """CREATE TABLE app_user_state (
            user_id VARCHAR2(64 CHAR) CONSTRAINT app_user_state_pk PRIMARY KEY
                CONSTRAINT app_user_state_user_fk REFERENCES app_users(id) ON DELETE CASCADE,
            doc CLOB NOT NULL CONSTRAINT app_user_state_json CHECK (doc IS JSON))""",
        """CREATE TABLE app_user_notes (
            user_id VARCHAR2(64 CHAR) NOT NULL CONSTRAINT app_user_notes_user_fk REFERENCES app_users(id) ON DELETE CASCADE,
            name VARCHAR2(200 CHAR) NOT NULL,
            title VARCHAR2(200 CHAR),
            body CLOB,
            created_at BINARY_DOUBLE NOT NULL,
            CONSTRAINT app_user_notes_pk PRIMARY KEY (user_id, name))""",
    ],
]

_VERSION_TABLE = "CREATE TABLE app_schema_version (version NUMBER NOT NULL)"
_UNIQUE_VIOLATION = 1  # ORA-00001; other integrity errors (ORA-02291, ...) are not "taken"
_ALREADY_THERE = {955, 1408, 2260, 2261, 2264, 2275}  # name used, index/key/constraint exists: a re-run after a partial migration
# Text columns are sized in characters; the store cuts what a client controls to fit.
IP, AGENT, NAME, TITLE, PATH, LONG = 100, 1000, 200, 200, 1000, 1000


def migrate(database: Database) -> None:
    """Apply the migrations that are not recorded in app_schema_version yet. Meant for one process
    at a time (`oracle-lab init-db`): DDL commits implicitly, so there is no lock to hold."""
    with session(database) as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM user_tables WHERE table_name = 'APP_SCHEMA_VERSION'")
        if not cur.fetchone()[0]:
            cur.execute(_VERSION_TABLE)
        cur.execute("SELECT MAX(version) FROM app_schema_version")
        current = int(cur.fetchone()[0] or 0)
        for number, statements in enumerate(MIGRATIONS, start=1):
            if number <= current:
                continue
            for statement in statements:
                try:
                    cur.execute(statement)
                except oracledb.DatabaseError as e:
                    if getattr(e.args[0], "code", None) not in _ALREADY_THERE:
                        raise
            cur.execute("INSERT INTO app_schema_version (version) VALUES (:v)", v=number)
            conn.commit()
            log.info("applied app schema version %d on %s", number, database.target)


def lob_text(value: str | oracledb.LOB | None) -> str:
    if value is None:
        return ""
    return value if isinstance(value, str) else value.read()


def _json(value: Any) -> Any:
    """An IS JSON column may come back parsed, as a string or as a CLOB."""
    return value if isinstance(value, dict | list) else json.loads(lob_text(value))


def _s(value: str | None) -> str:
    return value or ""


def _cut(value: str | None, size: int) -> str | None:
    return value[:size] if value else value


def _is_unique_violation(error: oracledb.IntegrityError) -> bool:
    detail = error.args[0] if error.args else None
    return getattr(detail, "code", None) == _UNIQUE_VIOLATION


@contextmanager
def _taken_on_duplicate() -> Iterator[None]:
    try:
        yield
    except oracledb.IntegrityError as e:
        if not _is_unique_violation(e):
            raise
        raise EmailTaken(TAKEN) from e


_USER_COLS = "id, email, display_name, role, status, created_at, last_login_at, password_changed_at"
_SESSION_COLS = "token_hash, user_id, csrf_token, created_at, last_seen_at, expires_at, ip, user_agent, reauth_until"
_FLOW_COLS = "id, state, nonce, code_verifier, intent, user_id, next_path, expires_at"
_SCHEMA_COLS = "user_id, database_key, schema_name, status, created_at, error"


def _user_binds(user: User) -> dict[str, Any]:
    return _binds(dataclasses.replace(user, display_name=_cut(user.display_name, NAME)))


def _user(r: tuple[Any, ...]) -> User:
    return User(r[0], r[1], _s(r[2]), r[3], r[4], r[5], r[6], r[7])


def _session(r: tuple[Any, ...]) -> SessionRecord:
    return SessionRecord(r[0], r[1], r[2], r[3], r[4], r[5], _s(r[6]), _s(r[7]), r[8])


def _schema(r: tuple[Any, ...]) -> PracticeSchema:
    return PracticeSchema(*r[:5], r[5] or None)


def _flow(r: tuple[Any, ...]) -> LoginFlow:
    return LoginFlow(r[0], r[1], r[2], r[3], r[4], r[5], _s(r[6]), r[7])


def _binds(obj: Any) -> dict[str, Any]:
    return dataclasses.asdict(obj)


class OracleUsers:
    def __init__(self, database: Database):
        self._db = database

    def add(self, user: User, identity: Identity) -> None:
        with _taken_on_duplicate(), session(self._db) as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO app_users (id, email, display_name, role, status, created_at, last_login_at, password_changed_at) "
                "VALUES (:id, :email, :display_name, :role, :status, :created_at, :last_login_at, :password_changed_at)",
                _user_binds(user),
            )
            self._insert_identity(cur, identity)
            conn.commit()

    def get(self, user_id: str) -> User | None:
        return self._one(f"SELECT {_USER_COLS} FROM app_users WHERE id = :v", v=user_id)

    def by_email(self, email: str) -> User | None:
        return self._one(f"SELECT {_USER_COLS} FROM app_users WHERE email = :v", v=email)

    def by_identity(self, provider: str, subject: str) -> User | None:
        return self._one(
            "SELECT u.id, u.email, u.display_name, u.role, u.status, u.created_at, u.last_login_at, u.password_changed_at "
            "FROM app_users u JOIN app_identities i ON i.user_id = u.id WHERE i.provider = :p AND i.subject = :s",
            p=provider, s=subject,
        )

    def _one(self, sql: str, **binds: Any) -> User | None:
        with session(self._db) as conn, conn.cursor() as cur:
            cur.execute(sql, binds)
            row = cur.fetchone()
            return _user(row) if row else None

    def identities(self, user_id: str) -> list[Identity]:
        with session(self._db) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT provider, subject, user_id, password_hash FROM app_identities WHERE user_id = :u ORDER BY seq", u=user_id
            )
            return [Identity(*r) for r in cur]

    def add_identity(self, identity: Identity) -> None:
        with _taken_on_duplicate(), session(self._db) as conn, conn.cursor() as cur:
            self._insert_identity(cur, identity)
            conn.commit()

    def remove_identity(self, user_id: str, provider: str) -> None:
        with session(self._db) as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM app_identities WHERE user_id = :u AND provider = :p", u=user_id, p=provider)
            conn.commit()

    def update(self, user: User) -> None:
        with session(self._db) as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE app_users SET email = :email, display_name = :display_name, role = :role, status = :status, "
                "created_at = :created_at, last_login_at = :last_login_at, password_changed_at = :password_changed_at "
                "WHERE id = :id",
                _user_binds(user),
            )
            conn.commit()

    def record_login(self, user_id: str, t: float) -> None:
        with session(self._db) as conn, conn.cursor() as cur:
            cur.execute("UPDATE app_users SET last_login_at = :t WHERE id = :u", t=t, u=user_id)
            conn.commit()

    def set_password(self, user_id: str, password_hash: str, changed_at: float) -> None:
        with session(self._db) as conn, conn.cursor() as cur:
            cur.execute("UPDATE app_users SET password_changed_at = :t WHERE id = :u", t=changed_at, u=user_id)
            if cur.rowcount:
                cur.execute(
                    "UPDATE app_identities SET password_hash = :h WHERE user_id = :u AND provider = 'password'",
                    h=password_hash, u=user_id,
                )
            conn.commit()

    def delete(self, user_id: str) -> None:
        with session(self._db) as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM app_users WHERE id = :u", u=user_id)
            conn.commit()

    def all(self) -> list[User]:
        with session(self._db) as conn, conn.cursor() as cur:
            cur.execute(f"SELECT {_USER_COLS} FROM app_users ORDER BY seq")
            return [_user(r) for r in cur]

    def count(self) -> int:
        with session(self._db) as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM app_users")
            return int(cur.fetchone()[0])

    @staticmethod
    def _insert_identity(cur: oracledb.Cursor, identity: Identity) -> None:
        cur.execute(
            "INSERT INTO app_identities (provider, subject, user_id, password_hash) "
            "VALUES (:provider, :subject, :user_id, :password_hash)",
            _binds(identity),
        )


class OracleSessions:
    def __init__(self, database: Database):
        self._db = database

    def _run(self, sql: str, binds: dict[str, Any]) -> None:
        with session(self._db) as conn, conn.cursor() as cur:
            cur.execute(sql, binds)
            conn.commit()

    def add(self, rec: SessionRecord) -> None:
        self._run(
            "MERGE INTO app_sessions s USING (SELECT :token_hash AS token_hash FROM dual) n ON (s.token_hash = n.token_hash) "
            "WHEN MATCHED THEN UPDATE SET s.user_id = :user_id, s.csrf_token = :csrf_token, s.created_at = :created_at, "
            "s.last_seen_at = :last_seen_at, s.expires_at = :expires_at, s.ip = :ip, s.user_agent = :user_agent, "
            "s.reauth_until = :reauth_until "
            f"WHEN NOT MATCHED THEN INSERT ({_SESSION_COLS}) VALUES (:token_hash, :user_id, :csrf_token, :created_at, "
            ":last_seen_at, :expires_at, :ip, :user_agent, :reauth_until)",
            _binds(dataclasses.replace(rec, ip=_cut(rec.ip, IP), user_agent=_cut(rec.user_agent, AGENT))),
        )

    def get(self, token_hash: str) -> SessionRecord | None:
        with session(self._db) as conn, conn.cursor() as cur:
            cur.execute(f"SELECT {_SESSION_COLS} FROM app_sessions WHERE token_hash = :h", h=token_hash)
            row = cur.fetchone()
            return _session(row) if row else None

    def touch(self, token_hash: str, t: float) -> None:
        self._run("UPDATE app_sessions SET last_seen_at = :t WHERE token_hash = :h", {"t": t, "h": token_hash})

    def set_reauth(self, token_hash: str, until: float) -> None:
        self._run("UPDATE app_sessions SET reauth_until = :t WHERE token_hash = :h", {"t": until, "h": token_hash})

    def delete(self, token_hash: str) -> None:
        self._run("DELETE FROM app_sessions WHERE token_hash = :h", {"h": token_hash})

    def delete_for_user(self, user_id: str, keep: str | None = None) -> None:
        if keep is None:
            self._run("DELETE FROM app_sessions WHERE user_id = :u", {"u": user_id})
        else:
            self._run("DELETE FROM app_sessions WHERE user_id = :u AND token_hash != :k", {"u": user_id, "k": keep})

    def for_user(self, user_id: str) -> list[SessionRecord]:
        with session(self._db) as conn, conn.cursor() as cur:
            cur.execute(f"SELECT {_SESSION_COLS} FROM app_sessions WHERE user_id = :u ORDER BY seq", u=user_id)
            return [_session(r) for r in cur]

    def purge(self, now: float) -> None:
        self._run("DELETE FROM app_sessions WHERE expires_at <= :t", {"t": now})


class OracleFlows:
    def __init__(self, database: Database):
        self._db = database

    def add(self, flow: LoginFlow) -> None:
        with session(self._db) as conn, conn.cursor() as cur:
            cur.execute(
                "MERGE INTO app_login_flows f USING (SELECT :id AS id FROM dual) n ON (f.id = n.id) "
                "WHEN MATCHED THEN UPDATE SET f.state = :state, f.nonce = :nonce, f.code_verifier = :code_verifier, "
                "f.intent = :intent, f.user_id = :user_id, f.next_path = :next_path, f.expires_at = :expires_at "
                f"WHEN NOT MATCHED THEN INSERT ({_FLOW_COLS}) VALUES (:id, :state, :nonce, :code_verifier, :intent, "
                ":user_id, :next_path, :expires_at)",
                _binds(dataclasses.replace(flow, next_path=_cut(flow.next_path, PATH))),
            )
            conn.commit()

    def take(self, flow_id: str) -> LoginFlow | None:
        with session(self._db) as conn, conn.cursor() as cur:
            cur.execute(f"SELECT {_FLOW_COLS} FROM app_login_flows WHERE id = :id FOR UPDATE", id=flow_id)
            row = cur.fetchone()
            if row:
                cur.execute("DELETE FROM app_login_flows WHERE id = :id", id=flow_id)
            conn.commit()
            return _flow(row) if row else None

    def purge(self, now: float) -> None:
        with session(self._db) as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM app_login_flows WHERE expires_at <= :t", t=now)
            conn.commit()


class OracleResets:
    def __init__(self, database: Database):
        self._db = database

    def add(self, tok: ResetToken) -> None:
        with session(self._db) as conn, conn.cursor() as cur:
            cur.execute(
                "MERGE INTO app_reset_tokens r USING (SELECT :token_hash AS token_hash FROM dual) n "
                "ON (r.token_hash = n.token_hash) "
                "WHEN MATCHED THEN UPDATE SET r.user_id = :user_id, r.created_by = :created_by, "
                "r.expires_at = :expires_at, r.used_at = :used_at "
                "WHEN NOT MATCHED THEN INSERT (token_hash, user_id, created_by, expires_at, used_at) "
                "VALUES (:token_hash, :user_id, :created_by, :expires_at, :used_at)",
                _binds(tok),
            )
            conn.commit()

    def take(self, token_hash: str, now: float) -> ResetToken | None:
        with session(self._db) as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE app_reset_tokens SET used_at = :now WHERE token_hash = :h AND used_at IS NULL AND expires_at > :now",
                now=now, h=token_hash,
            )
            if not cur.rowcount:
                return None
            cur.execute(
                "SELECT token_hash, user_id, created_by, expires_at, used_at FROM app_reset_tokens WHERE token_hash = :h",
                h=token_hash,
            )
            row = cur.fetchone()
            conn.commit()
            return ResetToken(*row)


class OracleThrottle:
    def __init__(self, database: Database):
        self._db = database

    def record(self, key: str, t: float) -> None:
        self._write("INSERT INTO app_throttle (key, t) VALUES (:k, :t)", k=key, t=t)

    def count_since(self, key: str, since: float) -> int:
        with session(self._db) as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM app_throttle WHERE key = :k AND t >= :t", k=key, t=since)
            return int(cur.fetchone()[0])

    def last(self, key: str) -> float | None:
        with session(self._db) as conn, conn.cursor() as cur:
            cur.execute("SELECT MAX(t) FROM app_throttle WHERE key = :k", k=key)
            return cur.fetchone()[0]

    def clear(self, key: str) -> None:
        self._write("DELETE FROM app_throttle WHERE key = :k", k=key)

    def purge(self, before: float) -> None:
        self._write("DELETE FROM app_throttle WHERE t < :t", t=before)

    def _write(self, sql: str, **binds: Any) -> None:
        with session(self._db) as conn, conn.cursor() as cur:
            cur.execute(sql, binds)
            conn.commit()


class OracleAudit:
    def __init__(self, database: Database):
        self._db = database

    def add(self, event: AuditEvent) -> None:
        with session(self._db) as conn, conn.cursor() as cur:
            cur.setinputsizes(detail=oracledb.DB_TYPE_CLOB)
            cur.execute(
                "INSERT INTO app_audit (t, event, outcome, user_id, ip, user_agent, detail) "
                "VALUES (:t, :event, :outcome, :user_id, :ip, :user_agent, :detail)",
                t=event.t, event=event.event, outcome=event.outcome, user_id=event.user_id, ip=_cut(event.ip, IP),
                user_agent=_cut(event.user_agent, AGENT), detail=json.dumps(event.detail, default=str),
            )
            conn.commit()

    def recent(self, limit: int = 200, event: str | None = None, user_id: str | None = None) -> list[AuditEvent]:
        conditions, binds = [], {"n": limit}
        if event is not None:
            conditions.append("event = :event")
            binds["event"] = event
        if user_id is not None:
            conditions.append("user_id = :user_id")
            binds["user_id"] = user_id
        where = f"WHERE {' AND '.join(conditions)} " if conditions else ""
        with session(self._db) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT t, event, outcome, user_id, ip, user_agent, detail FROM app_audit "
                f"{where}ORDER BY t DESC, id DESC FETCH FIRST :n ROWS ONLY",
                binds,
            )
            return [AuditEvent(r[0], r[1], r[2], r[3], _s(r[4]), _s(r[5]), _json(r[6])) for r in cur]

    def purge(self, before: float) -> None:
        with session(self._db) as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM app_audit WHERE t < :t", t=before)
            conn.commit()


class OracleSettings:
    def __init__(self, database: Database):
        self._db = database

    def get(self, key: str) -> str | None:
        with session(self._db) as conn, conn.cursor() as cur:
            cur.execute("SELECT value FROM app_settings WHERE key = :k", k=key)
            row = cur.fetchone()
            return _s(row[0]) if row else None

    def set(self, key: str, value: str) -> None:
        with session(self._db) as conn, conn.cursor() as cur:
            cur.execute(
                "MERGE INTO app_settings s USING (SELECT :k AS key FROM dual) n ON (s.key = n.key) "
                "WHEN MATCHED THEN UPDATE SET s.value = :v WHEN NOT MATCHED THEN INSERT (key, value) VALUES (:k, :v)",
                k=key, v=_cut(value, LONG),
            )
            conn.commit()


class OracleSchemas:
    def __init__(self, database: Database):
        self._db = database

    def get(self, user_id: str, database_key: str) -> PracticeSchema | None:
        with session(self._db) as conn, conn.cursor() as cur:
            cur.execute(
                f"SELECT {_SCHEMA_COLS} FROM app_practice_schemas WHERE user_id = :u AND database_key = :k",
                u=user_id, k=database_key,
            )
            row = cur.fetchone()
            return _schema(row) if row else None

    def put(self, rec: PracticeSchema) -> None:
        with session(self._db) as conn, conn.cursor() as cur:
            cur.execute(
                "MERGE INTO app_practice_schemas p USING (SELECT :user_id AS user_id, :database_key AS database_key FROM dual) n "
                "ON (p.user_id = n.user_id AND p.database_key = n.database_key) "
                "WHEN MATCHED THEN UPDATE SET p.schema_name = :schema_name, p.status = :status, "
                "p.created_at = :created_at, p.error = :error "
                f"WHEN NOT MATCHED THEN INSERT ({_SCHEMA_COLS}) VALUES (:user_id, :database_key, :schema_name, :status, "
                ":created_at, :error)",
                _binds(dataclasses.replace(rec, error=_cut(rec.error, LONG))),
            )
            conn.commit()

    def for_user(self, user_id: str) -> list[PracticeSchema]:
        return self._list("WHERE user_id = :u ", u=user_id)

    def delete(self, user_id: str, database_key: str) -> None:
        with session(self._db) as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM app_practice_schemas WHERE user_id = :u AND database_key = :k", u=user_id, k=database_key)
            conn.commit()

    def delete_for_user(self, user_id: str) -> None:
        with session(self._db) as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM app_practice_schemas WHERE user_id = :u", u=user_id)
            conn.commit()

    def all(self) -> list[PracticeSchema]:
        return self._list("")

    def _list(self, where: str, **binds: Any) -> list[PracticeSchema]:
        with session(self._db) as conn, conn.cursor() as cur:
            cur.execute(f"SELECT {_SCHEMA_COLS} FROM app_practice_schemas {where}ORDER BY seq", binds)
            return [_schema(r) for r in cur]


class OracleState:
    """One user's study state as a JSON document; a transaction holds the row lock until it ends."""

    def __init__(self, database: Database, user_id: str):
        self._db = database
        self._user_id = user_id

    def load(self) -> State:
        with session(self._db) as conn, conn.cursor() as cur:
            cur.execute("SELECT doc FROM app_user_state WHERE user_id = :u", u=self._user_id)
            row = cur.fetchone()
            return _json(row[0]) if row else new_state()

    @contextmanager
    def transaction(self) -> Iterator[State]:
        with session(self._db) as conn, conn.cursor() as cur:
            cur.setinputsizes(doc=oracledb.DB_TYPE_CLOB)
            try:  # a failed first transaction leaves this empty new_state() row behind, which is harmless
                cur.execute(
                    "INSERT INTO app_user_state (user_id, doc) SELECT :u, :doc FROM dual "
                    "WHERE NOT EXISTS (SELECT 1 FROM app_user_state WHERE user_id = :u)",
                    u=self._user_id, doc=json.dumps(new_state()),
                )
                conn.commit()
            except oracledb.IntegrityError as e:
                if not _is_unique_violation(e):  # a concurrent first transaction created it; ORA-02291 is real
                    raise
                conn.rollback()
            cur.execute("SELECT doc FROM app_user_state WHERE user_id = :u FOR UPDATE", u=self._user_id)
            row = cur.fetchone()
            state = _json(row[0]) if row else new_state()
            yield state
            cur.setinputsizes(doc=oracledb.DB_TYPE_CLOB)
            cur.execute(
                "MERGE INTO app_user_state s USING (SELECT :u AS user_id FROM dual) n ON (s.user_id = n.user_id) "
                "WHEN MATCHED THEN UPDATE SET s.doc = :doc WHEN NOT MATCHED THEN INSERT (user_id, doc) VALUES (:u, :doc)",
                u=self._user_id, doc=json.dumps(state),
            )
            conn.commit()


class OracleUserStates:
    def __init__(self, database: Database):
        self._db = database

    def for_user(self, user_id: str) -> OracleState:
        return OracleState(self._db, user_id)

    def delete(self, user_id: str) -> None:
        with session(self._db) as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM app_user_state WHERE user_id = :u", u=user_id)
            conn.commit()


class OracleNotes:
    """One user's personal notes; entries() lists them by name, descending (like FileNotes)."""

    def __init__(self, database: Database, user_id: str):
        self._db = database
        self._user_id = user_id

    def entries(self) -> list[tuple[str, str]]:
        with session(self._db) as conn, conn.cursor() as cur:
            cur.execute("SELECT name, title FROM app_user_notes WHERE user_id = :u ORDER BY name DESC", u=self._user_id)
            return [(name, _s(title)) for name, title in cur]

    def read(self, name: str) -> str | None:
        with session(self._db) as conn, conn.cursor() as cur:
            cur.execute("SELECT body FROM app_user_notes WHERE user_id = :u AND name = :n", u=self._user_id, n=name)
            row = cur.fetchone()
            return lob_text(row[0]) if row else None

    def add(self, stem: str, title: str, text: str) -> str:
        with session(self._db) as conn, conn.cursor() as cur:
            n = 1
            while True:
                name = f"{stem}.md" if n == 1 else f"{stem}-{n}.md"
                cur.setinputsizes(body=oracledb.DB_TYPE_CLOB)
                try:
                    cur.execute(
                        "INSERT INTO app_user_notes (user_id, name, title, body, created_at) "
                        "VALUES (:u, :name, :title, :body, :t)",
                        u=self._user_id, name=name, title=_cut(title, TITLE), body=text, t=time.time(),
                    )
                except oracledb.IntegrityError as e:
                    if not _is_unique_violation(e):
                        raise
                    n += 1
                    continue
                conn.commit()
                return name


class OracleUserNotes:
    def __init__(self, database: Database):
        self._db = database

    def for_user(self, user_id: str) -> OracleNotes:
        return OracleNotes(self._db, user_id)

    def delete(self, user_id: str) -> None:
        with session(self._db) as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM app_user_notes WHERE user_id = :u", u=user_id)
            conn.commit()


def oracle_stores(database: Database) -> AppStores:
    return AppStores(
        users=OracleUsers(database),
        sessions=OracleSessions(database),
        flows=OracleFlows(database),
        resets=OracleResets(database),
        throttle=OracleThrottle(database),
        audit=OracleAudit(database),
        settings=OracleSettings(database),
        schemas=OracleSchemas(database),
        states=OracleUserStates(database),
        notes=OracleUserNotes(database),
    )
