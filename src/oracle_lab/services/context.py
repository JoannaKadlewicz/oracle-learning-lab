"""The signed-in user's own stores: what the study controllers build their services on, request by request."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from functools import cached_property
from typing import TYPE_CHECKING

from oracle_lab.accounts.repositories import AppStores
from oracle_lab.auth.models import LoginRequired, Principal
from oracle_lab.study.notes import PersonalNotes
from oracle_lab.study.state import StateStore

if TYPE_CHECKING:  # services know nothing about HTTP beyond the request's principal
    from oracle_lab.provisioning.practice import PracticeDatabases
    from oracle_lab.web.http import Request


@dataclass(frozen=True)
class UserContext:
    principal: Principal
    state: StateStore
    notes: PersonalNotes
    practice_factory: Callable[[Principal], PracticeDatabases] | None = field(default=None, repr=False)
    sql_available: bool = True  # whether the plan may include SQL exercises

    @cached_property
    def practice(self) -> PracticeDatabases | None:
        """The user's practice databases, built on first use: study and notes requests never pay for them."""
        return self.practice_factory(self.principal) if self.practice_factory is not None else None


class UserContexts:
    """request -> UserContext of its principal; a request without one is LoginRequired, a 401 (Authenticate normally stops it)."""

    def __init__(self, stores: AppStores,
                 practice_factory: Callable[[Principal], PracticeDatabases] | None = None,
                 learners_get_sql: bool = True):
        self.stores = stores
        self.practice_factory = practice_factory
        self.learners_get_sql = learners_get_sql

    def __call__(self, request: Request) -> UserContext:
        principal = request.principal
        if principal is None:
            raise LoginRequired("Login required")  # error_boundary: 401 {"error": "Login required"}
        return UserContext(principal, self.stores.states.for_user(principal.user_id),
                           self.stores.notes.for_user(principal.user_id), self.practice_factory,
                           principal.role == "admin" or (self.learners_get_sql and principal.role != "free"))
