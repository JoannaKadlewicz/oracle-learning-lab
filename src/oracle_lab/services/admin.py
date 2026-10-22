"""What an administrator can do: list accounts, hand out reset links, lock, change roles, delete, recreate practice
schemas, open or close sign-up, and read the security events. Every change is audited with the admin as user_id."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, Protocol

from oracle_lab.accounts.deletion import AccountDeletion
from oracle_lab.accounts.repositories import AppStores
from oracle_lab.auth.audit import AuditLog
from oracle_lab.auth.models import AuthError, PracticeSchema, Principal, ResetToken, User
from oracle_lab.auth.registration import RegistrationPolicy
from oracle_lab.auth.sessions import SessionManager
from oracle_lab.auth.tokens import new_token, token_hash
from oracle_lab.services import Clock

log = logging.getLogger(__name__)

RESET_LINK_SECONDS = 24 * 3600
MAX_EVENTS = 500
DENIALS_PER_HOUR = 10
ROLES = ("free", "learner", "admin")
SELF = "You can't do that to your own account."
ONLY_ADMIN = "You can't remove the only admin."


class NotFound(AuthError):  # noqa: N818 - matches the other AuthError names
    """An unknown user id or practice target: 404 {"error": "Not found"}."""

    status = 404

    def __init__(self, message: str = "Not found"):
        super().__init__(message)


class UserPractice(Protocol):
    """The practice databases of one user (PracticeDatabases), as far as the admin page needs them."""

    provisioners: Any

    def provision(self, key: str) -> PracticeSchema | None: ...

    def size_mb(self, key: str) -> float | None: ...


PracticeFactory = Callable[[User], UserPractice]


class AdminService:
    def __init__(self, stores: AppStores, deletion: AccountDeletion, sessions: SessionManager,
                 registration: RegistrationPolicy, practice_factory: PracticeFactory, audit: AuditLog, clock: Clock,
                 public_url: str):
        self._stores = stores
        self._users = stores.users
        self._deletion = deletion
        self._sessions = sessions
        self._registration = registration
        self._practice = practice_factory
        self._audit = audit
        self._clock = clock
        self._public_url = public_url.rstrip("/")
        self._guard = deletion.guard  # shared with self-service deletion: one lock for every way to lose an admin

    # --- reading -------------------------------------------------------------------------------------------------

    def users(self) -> list[dict]:
        return [self._row(user) for user in sorted(self._users.all(), key=lambda u: (u.created_at, u.email))]

    def _row(self, user: User) -> dict:
        return {
            "id": user.id, "email": user.email,
            "methods": sorted({i.provider for i in self._users.identities(user.id)}),
            "role": user.role, "status": user.status, "created_at": user.created_at,
            "last_login_at": user.last_login_at, "sessions": len(self._sessions.live(user.id)),
            "schemas": [{"key": rec.database_key, "status": rec.status, "size_mb": self._size(user, rec),
                         "error": rec.error}
                        for rec in sorted(self._stores.schemas.for_user(user.id), key=lambda r: r.database_key)],
        }

    def _size(self, user: User, rec: PracticeSchema) -> float | None:
        """Never breaks the list: any failure (no DBA view, database down) is None."""
        if rec.status != "ready":
            return None
        try:
            size = self._practice(user).size_mb(rec.database_key)
        except Exception as exc:  # noqa: BLE001
            log.debug("size of the practice schema %s unknown: %s", rec.schema_name, exc)
            return None
        return None if size is None else round(float(size), 1)

    def settings(self) -> dict:
        return {"registration_open": self._registration.is_open(), "max_users": self._registration.max_users(),
                "users": self._users.count()}

    def events(self, limit: int = 200, event: str | None = None, user_id: str | None = None) -> list[dict]:
        """Newest first, at most MAX_EVENTS."""
        limit = max(1, min(int(limit), MAX_EVENTS))
        return [{"t": e.t, "event": e.event, "outcome": e.outcome, "user_id": e.user_id, "ip": e.ip,
                 "user_agent": e.user_agent, "detail": e.detail}
                for e in self._stores.audit.recent(limit, event or None, user_id or None)]

    # --- changing ------------------------------------------------------------------------------------------------
    # Every change takes the client's ip and user_agent (from the controller) for its audit record.

    def reset_link(self, actor: Principal, user_id: str, *, ip: str = "", user_agent: str = "") -> str:
        """A single-use password reset link, valid for 24 hours. The token is only in the returned link."""
        user = self._user(user_id)
        token = new_token()
        self._stores.resets.revoke_for_user(user.id)  # only the newest link works
        self._stores.resets.add(ResetToken(token_hash(token), user.id, actor.user_id,
                                           self._clock() + RESET_LINK_SECONDS))
        self._audit.record("reset_link_created", "ok", user_id=actor.user_id, ip=ip, user_agent=user_agent,
                           target=user.id)
        return f"{self._public_url}/reset?token={token}"

    def lock(self, actor: Principal, user_id: str, *, ip: str = "", user_agent: str = "") -> None:
        meta = {"ip": ip, "user_agent": user_agent}
        with self._guard:
            user = self._other(actor, user_id, "user_locked", meta)
            self._keep_an_admin(actor, user, "user_locked", meta)
            self._users.set_status(user.id, "locked")
        self._sessions.end_all(user.id)
        self._audit.record("user_locked", "ok", user_id=actor.user_id, target=user.id, **meta)

    def unlock(self, actor: Principal, user_id: str, *, ip: str = "", user_agent: str = "") -> None:
        user = self._user(user_id)
        self._users.set_status(user.id, "active")
        self._audit.record("user_unlocked", "ok", user_id=actor.user_id, ip=ip, user_agent=user_agent, target=user.id)

    def set_role(self, actor: Principal, user_id: str, role: str, *, ip: str = "", user_agent: str = "") -> None:
        if role not in ROLES:
            raise ValueError("Unknown role.")
        meta = {"ip": ip, "user_agent": user_agent}
        with self._guard:
            user = self._other(actor, user_id, "role_changed", meta)
            if user.role == role:
                return
            if role != "admin":
                self._keep_an_admin(actor, user, "role_changed", meta)
            self._users.set_role(user.id, role)
        self._audit.record("role_changed", "ok", user_id=actor.user_id, target=user.id, role=role, **meta)

    def delete(self, actor: Principal, user_id: str, *, ip: str = "", user_agent: str = "") -> None:
        meta = {"ip": ip, "user_agent": user_agent}
        with self._guard:
            user = self._other(actor, user_id, "account_deleted", meta)
            self._keep_an_admin(actor, user, "account_deleted", meta)
            self._deletion.delete(user.id, actor.user_id, **meta)  # audits account_deleted

    def recreate_schema(self, actor: Principal, user_id: str, key: str, *, ip: str = "",
                        user_agent: str = "") -> dict:
        """Drops the user's schema on target `key` (if any) and creates a new one, under the same per-(user, key)
        lock as every other provisioning."""
        user = self._user(user_id)
        practice = self._practice(user)
        if key not in practice.provisioners:
            raise NotFound()
        rec = practice.provision(key)
        status = rec.status if rec is not None else "deleted"
        self._audit.record("schema_recreated", "ok" if status == "ready" else "fail", user_id=actor.user_id,
                           ip=ip, user_agent=user_agent, target=user.id, key=key, status=status)
        return {"key": key, "status": status, "error": rec.error if rec is not None else None}

    def delete_inactive(self, actor: Principal, days: int, *, ip: str = "", user_agent: str = "") -> int:
        """Deletes the learners (never an admin or `actor`) not seen for `days` days: last sign-in, or creation when
        they never signed in. Returns how many were deleted."""
        if isinstance(days, bool) or not isinstance(days, int) or days < 1:
            raise ValueError("Enter a number of days of at least 1.")
        cutoff = self._clock() - days * 86400
        deleted = failed = 0
        for user in self._users.all():
            if user.role == "admin" or user.id == actor.user_id:
                continue
            if (user.last_login_at if user.last_login_at is not None else user.created_at) >= cutoff:
                continue
            try:
                with self._guard:
                    current = self._users.get(user.id)
                    if current is None or current.role == "admin":  # deleted or promoted meanwhile
                        continue
                    self._deletion.delete(user.id, actor.user_id, ip=ip, user_agent=user_agent)
            except Exception:  # noqa: BLE001 - delete the others; the summary counts the failures
                log.exception("could not delete the inactive account %s", user.id)
                failed += 1
                continue
            deleted += 1
        detail: dict[str, Any] = {"days": days, "count": deleted}
        if failed:
            detail["failed"] = failed
        self._audit.record("inactive_accounts_deleted", "ok" if not failed else "fail", user_id=actor.user_id,
                           ip=ip, user_agent=user_agent, **detail)
        return deleted

    def update_settings(self, actor: Principal, open: bool | None = None,  # noqa: A002
                        max_users: int | None = None, *, ip: str = "", user_agent: str = "") -> dict:
        if open is not None and not isinstance(open, bool):
            raise ValueError("open must be true or false.")
        if max_users is not None and (isinstance(max_users, bool) or not isinstance(max_users, int) or max_users < 1):
            raise ValueError("The user limit must be a whole number of at least 1.")
        self._registration.set(open, max_users)
        changed = {k: v for k, v in (("open", open), ("max_users", max_users)) if v is not None}
        self._audit.record("registration_settings_changed", "ok", user_id=actor.user_id, ip=ip,
                           user_agent=user_agent, **changed)
        return self.settings()

    def denied(self, principal: Principal | None, path: str, *, ip: str = "", user_agent: str = "") -> None:
        """Records a signed-in non-admin reaching for the admin API, at most DENIALS_PER_HOUR times per account
        an hour (the rest still get 404, unrecorded), so probing cannot flood the audit trail."""
        key = f"admin_denied:{principal.user_id if principal else ip}"
        now = self._clock()
        if self._stores.throttle.count_since(key, now - 3600) >= DENIALS_PER_HOUR:
            return
        self._stores.throttle.record(key, now)
        self._audit.record("admin_denied", "denied", user_id=principal.user_id if principal else None, ip=ip,
                           user_agent=user_agent, path=path[:200])

    # --- helpers -------------------------------------------------------------------------------------------------

    def _user(self, user_id: str) -> User:
        user = self._users.get(user_id) if isinstance(user_id, str) and user_id else None
        if user is None:
            raise NotFound()
        return user

    def _other(self, actor: Principal, user_id: str, event: str, meta: dict) -> User:
        """The user, refusing (and auditing) the actor's own account: no admin locks, demotes or deletes
        themselves."""
        if user_id == actor.user_id:
            self._audit.record(event, "denied", user_id=actor.user_id, target=user_id, reason="self", **meta)
            raise ValueError(SELF)
        return self._user(user_id)

    def _keep_an_admin(self, actor: Principal, user: User, event: str, meta: dict) -> None:
        """Call inside `with self._guard:`: refuses (and audits) taking away the last active admin."""
        if self._guard.is_last_active_admin(user):
            self._audit.record(event, "denied", user_id=actor.user_id, target=user.id, reason="last_admin", **meta)
            raise AuthError(ONLY_ADMIN)
