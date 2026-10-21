"""Deleting an account together with everything it owns, and the guard that keeps one active admin."""

from __future__ import annotations

import threading
from collections.abc import Callable

from oracle_lab.accounts.repositories import AppStores, UserRepository
from oracle_lab.auth.audit import AuditLog
from oracle_lab.auth.models import AuthError, User
from oracle_lab.auth.sessions import SessionManager


class AdminGuard:
    """One per app: every change that can take away an active admin (deleting, demoting, locking, from the admin
    page or the account's own settings) runs inside `with guard:`, so "count the active admins + change" is atomic.
    Re-entrant, so the admin page can hold it around AccountDeletion.delete. Assumes ONE process."""

    def __init__(self, users: UserRepository):
        self._users = users
        self._lock = threading.RLock()

    def __enter__(self) -> AdminGuard:
        self._lock.acquire()
        return self

    def __exit__(self, *exc: object) -> None:
        self._lock.release()

    def is_last_active_admin(self, user: User | None) -> bool:
        """Call inside `with guard:`. True when `user` is an active admin and no other active admin exists."""
        if user is None or user.role != "admin" or user.status != "active":
            return False
        return sum(u.role == "admin" and u.status == "active" for u in self._users.all()) <= 1


class AccountDeletion:
    def __init__(self, stores: AppStores, sessions: SessionManager, audit: AuditLog,
                 drop_schemas: Callable[[str], None] = lambda user_id: None, guard: AdminGuard | None = None):
        self._stores = stores
        self._sessions = sessions
        self._audit = audit
        self._drop_schemas = drop_schemas
        self.guard = guard or AdminGuard(stores.users)

    def delete(self, user_id: str, actor_id: str, *, ip: str = "", user_agent: str = "") -> None:
        with self.guard:
            if self.guard.is_last_active_admin(self._stores.users.get(user_id)):
                raise AuthError("You can't delete the only admin account.")
            self._sessions.end_all(user_id)  # first: no request of the user can provision a schema meanwhile
            self._drop_schemas(user_id)  # before the records go: they say what exists in the practice databases
            self._stores.schemas.delete_for_user(user_id)
            self._stores.states.delete(user_id)
            self._stores.notes.delete(user_id)
            self._stores.users.delete(user_id)  # identities go with the user
        self._audit.record("account_deleted", "ok", user_id=actor_id, ip=ip, user_agent=user_agent, target=user_id,
                           actor=actor_id)
