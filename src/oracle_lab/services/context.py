"""The signed-in user's own stores: what the study controllers build their services on, request by request."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from oracle_lab.accounts.repositories import AppStores
from oracle_lab.auth.models import LoginRequired, Principal
from oracle_lab.study.notes import PersonalNotes
from oracle_lab.study.state import StateStore

if TYPE_CHECKING:  # services know nothing about HTTP beyond the request's principal
    from oracle_lab.web.http import Request

PracticeDatabases = Any  # the user's practice schemas; the real type and its factory arrive with Task 16


@dataclass(frozen=True)
class UserContext:
    principal: Principal
    state: StateStore
    notes: PersonalNotes
    practice: PracticeDatabases | None = None


class UserContexts:
    """request -> UserContext of its principal; a request without one is LoginRequired, a 401 (Authenticate normally stops it)."""

    def __init__(self, stores: AppStores,
                 practice_factory: Callable[[Principal], PracticeDatabases] | None = None):
        self.stores = stores
        self.practice_factory = practice_factory

    def __call__(self, request: Request) -> UserContext:
        principal = request.principal
        if principal is None:
            raise LoginRequired("Login required")  # error_boundary: 401 {"error": "Login required"}
        practice = self.practice_factory(principal) if self.practice_factory is not None else None
        return UserContext(principal, self.stores.states.for_user(principal.user_id),
                           self.stores.notes.for_user(principal.user_id), practice)
