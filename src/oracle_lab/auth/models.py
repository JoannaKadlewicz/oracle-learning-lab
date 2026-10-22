"""Account data types and the errors of the auth services. Times are Unix seconds (float)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Role = Literal["user", "admin"]  # what a user may do in a workspace is their workspace access
Status = Literal["active", "locked"]


@dataclass(frozen=True)
class User:
    id: str
    email: str
    display_name: str
    role: Role
    status: Status
    created_at: float
    last_login_at: float | None
    password_changed_at: float | None


@dataclass(frozen=True)
class Identity:
    provider: Literal["password", "google"]
    subject: str
    user_id: str
    password_hash: str | None = None


@dataclass(frozen=True)
class SessionRecord:
    token_hash: str
    user_id: str
    csrf_token: str
    created_at: float
    last_seen_at: float
    expires_at: float
    ip: str
    user_agent: str
    reauth_until: float = 0.0


@dataclass(frozen=True)
class LoginFlow:
    id: str
    state: str
    nonce: str
    code_verifier: str
    intent: Literal["login", "link", "reauth"]
    user_id: str | None
    next_path: str
    expires_at: float


@dataclass(frozen=True)
class ResetToken:
    token_hash: str
    user_id: str
    created_by: str
    expires_at: float
    used_at: float | None = None


@dataclass(frozen=True)
class AuditEvent:
    t: float
    event: str
    outcome: Literal["ok", "fail", "denied"]
    user_id: str | None
    ip: str
    user_agent: str
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PracticeSchema:
    user_id: str
    database_key: str
    schema_name: str
    status: Literal["provisioning", "ready", "failed"]
    created_at: float
    error: str | None = None


@dataclass(frozen=True)
class Principal:
    """The signed-in account of a request."""

    user_id: str
    email: str
    role: Role
    session_hash: str
    csrf_token: str
    reauth_until: float


@dataclass(frozen=True)
class LoginResult:
    token: str
    user: User


class AuthError(Exception):
    """Base of the errors whose message is safe to show to the user."""

    status = 400


class InvalidCredentials(AuthError):  # noqa: N818 - names fixed by the design
    status = 401


class LoginRequired(AuthError):  # noqa: N818 - names fixed by the design
    status = 401


class RegistrationClosed(AuthError):  # noqa: N818 - names fixed by the design
    status = 403


class EmailTaken(AuthError):  # noqa: N818 - names fixed by the design
    status = 409


class WeakPassword(AuthError):  # noqa: N818 - names fixed by the design
    status = 400

    def __init__(self, message: str, problems: list[str] | None = None):
        super().__init__(message)
        self.problems = problems or []


class Throttled(AuthError):  # noqa: N818 - names fixed by the design
    status = 429

    def __init__(self, message: str, retry_after: int = 0):
        super().__init__(message)
        self.retry_after = retry_after


class ReauthRequired(AuthError):  # noqa: N818 - names fixed by the design
    status = 403
