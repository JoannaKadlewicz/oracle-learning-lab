"""In-memory account stores, for tests and simulations. One lock per repository."""

from __future__ import annotations

import dataclasses
import threading
from collections.abc import Callable

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
from oracle_lab.study.state import MemoryStateStore, StateStore

TAKEN = "Could not create the account. If you already have one, sign in instead."


class MemoryUsers:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._users: dict[str, User] = {}
        self._identities: list[Identity] = []
        self.on_delete: list[Callable[[str], None]] = []  # cascades, wired by memory_stores()

    def add(self, user: User, identity: Identity) -> None:
        with self._lock:
            if (
                user.id in self._users
                or any(u.email == user.email for u in self._users.values())
                or self._find(identity.provider, identity.subject)
            ):
                raise EmailTaken(TAKEN)
            self._users[user.id] = user
            self._identities.append(identity)

    def get(self, user_id: str) -> User | None:
        return self._users.get(user_id)

    def by_email(self, email: str) -> User | None:
        with self._lock:
            return next((u for u in self._users.values() if u.email == email), None)

    def by_identity(self, provider: str, subject: str) -> User | None:
        with self._lock:
            found = self._find(provider, subject)
            return self._users.get(found.user_id) if found else None

    def identities(self, user_id: str) -> list[Identity]:
        with self._lock:
            return [i for i in self._identities if i.user_id == user_id]

    def add_identity(self, identity: Identity) -> None:
        with self._lock:
            if self._find(identity.provider, identity.subject):
                raise EmailTaken(TAKEN)
            self._identities.append(identity)

    def remove_identity(self, user_id: str, provider: str) -> None:
        with self._lock:
            self._identities = [i for i in self._identities if not (i.user_id == user_id and i.provider == provider)]

    def update(self, user: User) -> None:
        with self._lock:
            if user.id in self._users:
                self._users[user.id] = user

    def record_login(self, user_id: str, t: float) -> None:
        with self._lock:
            user = self._users.get(user_id)
            if user is not None:
                self._users[user_id] = dataclasses.replace(user, last_login_at=t)

    def set_password(self, user_id: str, password_hash: str, changed_at: float) -> None:
        with self._lock:
            user = self._users.get(user_id)
            if user is None:
                return
            self._users[user_id] = dataclasses.replace(user, password_changed_at=changed_at)
            self._identities = [
                dataclasses.replace(i, password_hash=password_hash) if i.user_id == user_id and i.provider == "password" else i
                for i in self._identities
            ]

    def delete(self, user_id: str) -> None:
        with self._lock:
            self._users.pop(user_id, None)
            self._identities = [i for i in self._identities if i.user_id != user_id]
        for cascade in self.on_delete:
            cascade(user_id)

    def all(self) -> list[User]:
        with self._lock:
            return list(self._users.values())

    def count(self) -> int:
        return len(self._users)

    def _find(self, provider: str, subject: str) -> Identity | None:
        return next((i for i in self._identities if i.provider == provider and i.subject == subject), None)


class MemorySessions:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_hash: dict[str, SessionRecord] = {}

    def add(self, rec: SessionRecord) -> None:
        with self._lock:
            self._by_hash[rec.token_hash] = rec

    def get(self, token_hash: str) -> SessionRecord | None:
        return self._by_hash.get(token_hash)

    def touch(self, token_hash: str, t: float) -> None:
        self._change(token_hash, last_seen_at=t)

    def set_reauth(self, token_hash: str, until: float) -> None:
        self._change(token_hash, reauth_until=until)

    def delete(self, token_hash: str) -> None:
        with self._lock:
            self._by_hash.pop(token_hash, None)

    def delete_for_user(self, user_id: str, keep: str | None = None) -> None:
        with self._lock:
            self._by_hash = {h: s for h, s in self._by_hash.items() if s.user_id != user_id or h == keep}

    def for_user(self, user_id: str) -> list[SessionRecord]:
        with self._lock:
            return [s for s in self._by_hash.values() if s.user_id == user_id]

    def purge(self, now: float) -> None:
        with self._lock:
            self._by_hash = {h: s for h, s in self._by_hash.items() if s.expires_at > now}

    def _change(self, token_hash: str, **fields: float) -> None:
        with self._lock:
            rec = self._by_hash.get(token_hash)
            if rec is not None:
                self._by_hash[token_hash] = dataclasses.replace(rec, **fields)


class MemoryFlows:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._flows: dict[str, LoginFlow] = {}

    def add(self, flow: LoginFlow) -> None:
        with self._lock:
            self._flows[flow.id] = flow

    def take(self, flow_id: str) -> LoginFlow | None:
        with self._lock:
            return self._flows.pop(flow_id, None)

    def purge(self, now: float) -> None:
        with self._lock:
            self._flows = {i: f for i, f in self._flows.items() if f.expires_at > now}


class MemoryResets:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tokens: dict[str, ResetToken] = {}

    def add(self, tok: ResetToken) -> None:
        with self._lock:
            self._tokens[tok.token_hash] = tok

    def take(self, token_hash: str, now: float) -> ResetToken | None:
        with self._lock:
            tok = self._tokens.get(token_hash)
            if tok is None or tok.used_at is not None or tok.expires_at <= now:
                return None
            used = dataclasses.replace(tok, used_at=now)
            self._tokens[token_hash] = used
            return used


class MemoryThrottle:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._times: dict[str, list[float]] = {}

    def record(self, key: str, t: float) -> None:
        with self._lock:
            self._times.setdefault(key, []).append(t)

    def count_since(self, key: str, since: float) -> int:
        with self._lock:
            return sum(1 for t in self._times.get(key, []) if t >= since)

    def last(self, key: str) -> float | None:
        with self._lock:
            return max(self._times.get(key, []), default=None)

    def clear(self, key: str) -> None:
        with self._lock:
            self._times.pop(key, None)

    def purge(self, before: float) -> None:
        with self._lock:
            kept = {k: [t for t in ts if t >= before] for k, ts in self._times.items()}
            self._times = {k: ts for k, ts in kept.items() if ts}


class MemoryAudit:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: list[AuditEvent] = []

    def add(self, event: AuditEvent) -> None:
        with self._lock:
            self._events.append(event)

    def recent(self, limit: int = 200, event: str | None = None, user_id: str | None = None) -> list[AuditEvent]:
        with self._lock:
            # newest first by t, then by insertion order (later insertions first)
            ordered = sorted(enumerate(self._events), key=lambda p: (p[1].t, p[0]), reverse=True)
        matching = [e for _, e in ordered if (event is None or e.event == event) and (user_id is None or e.user_id == user_id)]
        return matching[:limit]

    def purge(self, before: float) -> None:
        with self._lock:
            self._events = [e for e in self._events if e.t >= before]


class MemorySettings:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._values: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self._values.get(key)

    def set(self, key: str, value: str) -> None:
        with self._lock:
            self._values[key] = value


class MemorySchemas:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._recs: dict[tuple[str, str], PracticeSchema] = {}

    def get(self, user_id: str, database_key: str) -> PracticeSchema | None:
        return self._recs.get((user_id, database_key))

    def put(self, rec: PracticeSchema) -> None:
        with self._lock:
            self._recs[(rec.user_id, rec.database_key)] = rec

    def for_user(self, user_id: str) -> list[PracticeSchema]:
        with self._lock:
            return [r for r in self._recs.values() if r.user_id == user_id]

    def delete_for_user(self, user_id: str) -> None:
        with self._lock:
            self._recs = {k: r for k, r in self._recs.items() if r.user_id != user_id}

    def all(self) -> list[PracticeSchema]:
        with self._lock:
            return list(self._recs.values())


class MemoryUserStates:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stores: dict[str, MemoryStateStore] = {}

    def for_user(self, user_id: str) -> StateStore:
        with self._lock:
            return self._stores.setdefault(user_id, MemoryStateStore())

    def delete(self, user_id: str) -> None:
        with self._lock:
            self._stores.pop(user_id, None)


class MemoryNotes:
    """One user's personal notes; entries() lists them by name, descending (like FileNotes)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._notes: dict[str, tuple[str, str]] = {}  # name -> (title, text)

    def entries(self) -> list[tuple[str, str]]:
        with self._lock:
            return [(name, title) for name, (title, _) in sorted(self._notes.items(), reverse=True)]

    def read(self, name: str) -> str | None:
        with self._lock:
            note = self._notes.get(name)
            return note[1] if note else None

    def add(self, stem: str, title: str, text: str) -> str:
        with self._lock:
            name, n = f"{stem}.md", 2
            while name in self._notes:
                name = f"{stem}-{n}.md"
                n += 1
            self._notes[name] = (title, text)
            return name


class MemoryUserNotes:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._notes: dict[str, MemoryNotes] = {}

    def for_user(self, user_id: str) -> MemoryNotes:
        with self._lock:
            return self._notes.setdefault(user_id, MemoryNotes())

    def delete(self, user_id: str) -> None:
        with self._lock:
            self._notes.pop(user_id, None)


def memory_stores() -> AppStores:
    """Fresh stores; deleting a user also removes its sessions, practice schemas, state and notes."""
    users, sessions, schemas = MemoryUsers(), MemorySessions(), MemorySchemas()
    states, notes = MemoryUserStates(), MemoryUserNotes()
    users.on_delete = [sessions.delete_for_user, schemas.delete_for_user, states.delete, notes.delete]
    return AppStores(
        users=users,
        sessions=sessions,
        flows=MemoryFlows(),
        resets=MemoryResets(),
        throttle=MemoryThrottle(),
        audit=MemoryAudit(),
        settings=MemorySettings(),
        schemas=schemas,
        states=states,
        notes=notes,
    )
