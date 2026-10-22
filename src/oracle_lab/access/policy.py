"""Who may use which workspace. Pure: the caller passes the account role and its access rows."""

from __future__ import annotations

from typing import Literal

from oracle_lab import exams
from oracle_lab.access.models import WorkspaceAccess

LevelIn = Literal["none", "member"]


def level_in(role: str, rows: list[WorkspaceAccess], workspace: str) -> LevelIn:
    """Whether the user is a member of `workspace`; admins are members of every workspace without rows, and so is
    an account still on the old `learner` role (its migration failed): it keeps what it had until it is moved."""
    if role in ("admin", "learner"):
        return "member"
    return "member" if any(r.workspace == workspace for r in rows) else "none"


def usable(role: str, rows: list[WorkspaceAccess]) -> list[str]:
    """The workspaces the user may open, in registry order."""
    return [code for code in exams.EXAMS if level_in(role, rows, code) != "none"]


def current_workspace(role: str, rows: list[WorkspaceAccess], saved: str | None) -> str | None:
    """The saved workspace when the user may use it, else the first one they may, else None (they must pick)."""
    allowed = usable(role, rows)
    if saved in allowed:
        return saved
    if role == "admin" and exams.DEFAULT_EXAM in allowed:
        return exams.DEFAULT_EXAM
    return allowed[0] if allowed else None
