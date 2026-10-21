"""Deleting an account together with everything it owns."""

from __future__ import annotations

from collections.abc import Callable

from oracle_lab.accounts.repositories import AppStores
from oracle_lab.auth.audit import AuditLog
from oracle_lab.auth.models import AuthError
from oracle_lab.auth.sessions import SessionManager


class AccountDeletion:
    def __init__(self, stores: AppStores, sessions: SessionManager, audit: AuditLog,
                 drop_schemas: Callable[[str], None] = lambda user_id: None):
        self._stores = stores
        self._sessions = sessions
        self._audit = audit
        self._drop_schemas = drop_schemas

    def delete(self, user_id: str, actor_id: str, *, ip: str = "", user_agent: str = "") -> None:
        user = self._stores.users.get(user_id)
        if user is not None and user.role == "admin" and sum(u.role == "admin" for u in self._stores.users.all()) <= 1:
            raise AuthError("You can't delete the only admin account.")
        self._sessions.end_all(user_id)  # first: no request of the user can provision a schema meanwhile
        self._drop_schemas(user_id)  # before the records go: they say what exists in the practice databases
        self._stores.schemas.delete_for_user(user_id)
        self._stores.states.delete(user_id)
        self._stores.notes.delete(user_id)
        self._stores.users.delete(user_id)  # identities go with the user
        self._audit.record("account_deleted", "ok", user_id=actor_id, ip=ip, user_agent=user_agent, target=user_id,
                           actor=actor_id)
