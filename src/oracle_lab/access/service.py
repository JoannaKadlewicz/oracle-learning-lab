"""Workspaces for the front end: the overview of what a user may open, their first pick, and admins granting or
taking access."""

from __future__ import annotations

from typing import Any

from oracle_lab import content, exams
from oracle_lab.access import plans, policy
from oracle_lab.access.models import WorkspaceAccess
from oracle_lab.accounts.repositories import AppStores
from oracle_lab.auth.audit import AuditLog
from oracle_lab.auth.models import Principal
from oracle_lab.i18n import Msg
from oracle_lab.services import AccessDenied, Clock

ALREADY_CHOSEN = "Your workspace is already chosen. Ask an admin to change it."
ADMIN_TARGET = "Admins already have every workspace."


class UnknownUserError(LookupError):
    """The admin named a user id that does not exist."""


def _workspace(code: Any) -> str:
    if code not in exams.EXAMS:
        raise ValueError(Msg.of("Unknown workspace: {code}", code=str(code)))
    return code


class WorkspaceService:
    def __init__(self, stores: AppStores, audit: AuditLog, clock: Clock):
        self._stores = stores
        self._audit = audit
        self._clock = clock

    def overview(self, principal: Principal, saved: str | None, lang: str = "en") -> dict[str, Any]:
        """Every workspace with the user's level in it, and the one they are in (None: they must pick)."""
        rows = self._stores.access.for_user(principal.user_id)
        workspaces = []
        for code, exam in exams.EXAMS.items():
            facts = content.public_exam(exam, lang)
            workspaces.append({"code": code, "title": facts["title"], "tile": facts["tile"],
                               "engine": exam.database_label, "logo": exam.engine, "questions": exam.questions,
                               "level": policy.level_in(principal.role, rows, code)})
        return {"current": policy.current_workspace(principal.role, rows, saved), "workspaces": workspaces}

    def choose(self, principal: Principal, workspace: Any, *, ip: str = "", user_agent: str = "") -> None:
        """A user's first workspace (their only one, unless a pro is given more); refused once they have any."""
        code = _workspace(workspace)
        if principal.role == "admin" or self._stores.access.for_user(principal.user_id):
            self._audit.record("workspace_chosen", "denied", user_id=principal.user_id, ip=ip, user_agent=user_agent,
                               workspace=code)
            raise AccessDenied(ALREADY_CHOSEN)
        self._stores.access.put(WorkspaceAccess(principal.user_id, code, "member", principal.user_id, self._clock()))
        with self._stores.states.for_user(principal.user_id).transaction() as state:
            state["settings"]["exam"] = code
        self._audit.record("workspace_chosen", "ok", user_id=principal.user_id, ip=ip, user_agent=user_agent,
                           workspace=code)

    def set_membership(self, actor: Principal, user_id: str, workspace: Any, member: Any, *, ip: str = "",
                       user_agent: str = "") -> None:
        """An admin adds (member=True) or removes a user's workspace. A plan with one workspace (guest, user) has it
        moved here; a pro gains one more."""
        code = _workspace(workspace)
        if not isinstance(member, bool):
            raise ValueError("member must be true or false.")
        user = self._stores.users.get(user_id)
        if user is None:
            raise UnknownUserError(user_id)
        if user.role == "admin":
            raise ValueError(ADMIN_TARGET)
        if not member:
            self._stores.access.delete(user.id, code)
        else:
            if not plans.can(user.role, "many_workspaces"):  # one workspace: moved, not added
                for row in self._stores.access.for_user(user.id):
                    if row.workspace != code:
                        self._stores.access.delete(user.id, row.workspace)
            self._stores.access.put(WorkspaceAccess(user.id, code, "member", actor.user_id, self._clock()))
        self._audit.record("workspace_access_changed", "ok", user_id=actor.user_id, ip=ip, user_agent=user_agent,
                           target=user.id, workspace=code, member=member)
