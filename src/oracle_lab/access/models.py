"""A user's access to one workspace (an exam track of the registry). No row means no access."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Level = Literal["free", "subscribed"]
LEVELS: tuple[Level, ...] = ("free", "subscribed")


@dataclass(frozen=True)
class WorkspaceAccess:
    user_id: str
    workspace: str  # an exams.EXAMS code
    level: Level
    granted_by: str  # the user id of the admin, the user's own id for their first pick, or "migration"
    granted_at: float
