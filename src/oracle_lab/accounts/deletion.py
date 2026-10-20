"""Deleting an account together with everything it owns."""

from __future__ import annotations

from collections.abc import Callable

from oracle_lab.accounts.repositories import AppStores
from oracle_lab.auth.audit import AuditLog
from oracle_lab.auth.sessions import SessionManager


class AccountDeletion:
    def __init__(self, stores: AppStores, sessions: SessionManager, audit: AuditLog,
                 drop_schemas: Callable[[str], None] = lambda user_id: None):
        self._stores = stores
        self._sessions = sessions
        self._audit = audit
        self._drop_schemas = drop_schemas

    def delete(self, user_id: str, actor_id: str) -> None:
        self._drop_schemas(user_id)  # first: the records say what exists in the practice databases
        self._sessions.end_all(user_id)
        self._stores.schemas.delete_for_user(user_id)
        self._stores.states.delete(user_id)
        self._stores.notes.delete(user_id)
        self._stores.users.delete(user_id)  # identities go with the user
        self._audit.record("account_deleted", "ok", user_id=actor_id, target=user_id, actor=actor_id)
