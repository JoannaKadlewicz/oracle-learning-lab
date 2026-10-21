"""The storage interfaces of the account system, and the bundle of them the app uses."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from oracle_lab.auth.models import (
    AuditEvent,
    Identity,
    LoginFlow,
    PracticeSchema,
    ResetToken,
    SessionRecord,
    User,
)
from oracle_lab.study.notes import PersonalNotes
from oracle_lab.study.state import StateStore


class UserRepository(Protocol):
    def add(self, user: User, identity: Identity) -> None:
        """Create the user with its first identity, atomically; raises EmailTaken when the email
        or the (provider, subject) is already in use."""

    def get(self, user_id: str) -> User | None: ...

    def by_email(self, email: str) -> User | None: ...

    def by_identity(self, provider: str, subject: str) -> User | None: ...

    def identities(self, user_id: str) -> list[Identity]: ...

    def add_identity(self, identity: Identity) -> None: ...

    def remove_identity(self, user_id: str, provider: str) -> None: ...

    def update(self, user: User) -> None: ...

    def set_status(self, user_id: str, status: str) -> None:
        """Set status only (an admin locking or unlocking); unknown user: no-op."""

    def set_role(self, user_id: str, role: str) -> None:
        """Set role only; unknown user: no-op."""

    def set_password(self, user_id: str, password_hash: str, changed_at: float) -> None: ...

    def record_login(self, user_id: str, t: float) -> None:
        """Set last_login_at only; every other field is left as stored."""

    def delete(self, user_id: str) -> None:
        """Remove the user and its identities (not its sessions, state or notes)."""

    def all(self) -> list[User]: ...

    def count(self) -> int: ...


class SessionRepository(Protocol):
    def add(self, rec: SessionRecord) -> None: ...

    def get(self, token_hash: str) -> SessionRecord | None: ...

    def touch(self, token_hash: str, t: float) -> None: ...

    def set_reauth(self, token_hash: str, until: float) -> None: ...

    def delete(self, token_hash: str) -> None: ...

    def delete_for_user(self, user_id: str, keep: str | None = None) -> None: ...

    def for_user(self, user_id: str) -> list[SessionRecord]: ...

    def purge(self, now: float) -> None:
        """Drop the sessions that expired by `now`."""


class FlowRepository(Protocol):
    def add(self, flow: LoginFlow) -> None: ...

    def take(self, flow_id: str) -> LoginFlow | None:
        """Return the flow and delete it; None when unknown or already taken."""

    def purge(self, now: float) -> None: ...


class ResetTokenRepository(Protocol):
    def add(self, tok: ResetToken) -> None: ...

    def take(self, token_hash: str, now: float) -> ResetToken | None:
        """Mark an unused, unexpired token used and return it (with used_at set); else None."""


class ThrottleRepository(Protocol):
    def record(self, key: str, t: float) -> None: ...

    def count_since(self, key: str, since: float) -> int: ...

    def last(self, key: str) -> float | None: ...

    def clear(self, key: str) -> None: ...

    def purge(self, before: float) -> None: ...


class AuditRepository(Protocol):
    def add(self, event: AuditEvent) -> None: ...

    def recent(self, limit: int = 200, event: str | None = None, user_id: str | None = None) -> list[AuditEvent]:
        """Newest first."""

    def purge(self, before: float) -> None: ...


class SettingsRepository(Protocol):
    def get(self, key: str) -> str | None: ...

    def set(self, key: str, value: str) -> None: ...


class PracticeSchemaRepository(Protocol):
    def get(self, user_id: str, database_key: str) -> PracticeSchema | None: ...

    def put(self, rec: PracticeSchema) -> None: ...

    def for_user(self, user_id: str) -> list[PracticeSchema]: ...

    def delete(self, user_id: str, database_key: str) -> None: ...

    def delete_for_user(self, user_id: str) -> None: ...

    def all(self) -> list[PracticeSchema]: ...


class UserStateStores(Protocol):
    def for_user(self, user_id: str) -> StateStore: ...

    def delete(self, user_id: str) -> None: ...


class UserNotesStores(Protocol):
    def for_user(self, user_id: str) -> PersonalNotes: ...

    def delete(self, user_id: str) -> None: ...


@dataclass(frozen=True)
class AppStores:
    users: UserRepository
    sessions: SessionRepository
    flows: FlowRepository
    resets: ResetTokenRepository
    throttle: ThrottleRepository
    audit: AuditRepository
    settings: SettingsRepository
    schemas: PracticeSchemaRepository
    states: UserStateStores
    notes: UserNotesStores
