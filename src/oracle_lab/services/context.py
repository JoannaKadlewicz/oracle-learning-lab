"""The signed-in user's own stores and workspace: what the study controllers build their services on, request by
request."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from functools import cached_property
from typing import TYPE_CHECKING, Any

from oracle_lab.access import policy
from oracle_lab.access.limits import FreeLimits, used_today
from oracle_lab.accounts.repositories import AppStores
from oracle_lab.auth.models import LoginRequired, Principal
from oracle_lab.services import WORKSPACE_REQUIRED, WorkspaceRequired
from oracle_lab.study.notes import PersonalNotes
from oracle_lab.study.state import State, StateStore

if TYPE_CHECKING:  # services know nothing about HTTP beyond the request's principal
    from oracle_lab.provisioning.practice import PracticeDatabases
    from oracle_lab.web.http import Request


@dataclass(frozen=True)
class Access:
    """The user's place in the current workspace: its code, their level there, the free plan's limits (None for
    subscribers) and every workspace they may switch to."""

    workspace: str | None
    level: str = "subscribed"
    limits: FreeLimits | None = None
    usable: tuple[str, ...] = ()

    def public(self, state: State, now: float) -> dict[str, Any]:
        return {"workspace": self.workspace, "level": self.level, "usable": list(self.usable),
                "limits": self.limits.public() if self.limits else None, "used": used_today(state, now)}


UNRESTRICTED = Access(None)  # services built without a request (tests, tools) apply no workspace rules


@dataclass(frozen=True)
class UserContext:
    principal: Principal
    state: StateStore
    notes: PersonalNotes
    practice_factory: Callable[[Principal], PracticeDatabases] | None = field(default=None, repr=False)
    sql_available: bool = True  # whether the plan may include SQL exercises
    access: Access = UNRESTRICTED

    @property
    def level(self) -> str:
        return self.access.level

    @cached_property
    def practice(self) -> PracticeDatabases | None:
        """The user's practice databases, built on first use: study and notes requests never pay for them."""
        return self.practice_factory(self.principal) if self.practice_factory is not None else None


class UserContexts:
    """request -> UserContext of its principal; a request without one is LoginRequired, a 401 (Authenticate normally
    stops it), and a user without a workspace is WorkspaceRequired, a 409 (unless `require_workspace` is False)."""

    def __init__(self, stores: AppStores,
                 practice_factory: Callable[[Principal], PracticeDatabases] | None = None,
                 learners_get_sql: bool = True):
        self.stores = stores
        self.practice_factory = practice_factory
        self.learners_get_sql = learners_get_sql

    def __call__(self, request: Request, require_workspace: bool = True) -> UserContext:
        principal = request.principal
        if principal is None:
            raise LoginRequired("Login required")  # error_boundary: 401 {"error": "Login required"}
        state = self.stores.states.for_user(principal.user_id)
        access = self.access(principal, state)
        if access.workspace is None and require_workspace:
            raise WorkspaceRequired(WORKSPACE_REQUIRED)
        sql = access.level == "subscribed" and (self.learners_get_sql or principal.role == "admin")
        return UserContext(principal, state, self.stores.notes.for_user(principal.user_id), self.practice_factory,
                           sql, access)

    def access(self, principal: Principal, state: StateStore) -> Access:
        """The user's current workspace and level. A saved workspace the user may no longer use is replaced in their
        settings by one they may, so every service reads the same workspace."""
        rows = self.stores.access.for_user(principal.user_id)
        saved = state.load().get("settings", {}).get("exam")
        workspace = policy.current_workspace(principal.role, rows, saved)
        if workspace is not None and workspace != saved:
            with state.transaction() as changing:
                changing["settings"]["exam"] = workspace
        level = policy.level_in(principal.role, rows, workspace) if workspace else "none"
        limits = FreeLimits.load(self.stores.settings) if level == "free" else None
        return Access(workspace, level, limits, tuple(policy.usable(principal.role, rows)))
