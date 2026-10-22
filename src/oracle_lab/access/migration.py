"""Start-up migration from account roles to workspace access. Accounts with the old roles become users:
`learner` with a subscription to every workspace (nobody loses anything), `free` with free access to the
workspace they had chosen. Idempotent: only accounts still holding an old role are touched."""

from __future__ import annotations

from oracle_lab import exams
from oracle_lab.access.models import WorkspaceAccess
from oracle_lab.accounts.repositories import AppStores
from oracle_lab.auth.audit import AuditLog
from oracle_lab.services import Clock
from oracle_lab.study.tracks import exam_code

OLD_ROLES = ("learner", "free")


def migrate_roles(stores: AppStores, clock: Clock, audit: AuditLog) -> int:
    """Moves every account with an old role; returns how many were moved."""
    moved = 0
    for user in stores.users.all():
        if user.role not in OLD_ROLES:
            continue
        now = clock()
        if user.role == "learner":
            grants = [(code, "subscribed") for code in exams.EXAMS]
        else:
            grants = [(exam_code(stores.states.for_user(user.id).load()), "free")]
        for code, level in grants:
            stores.access.put(WorkspaceAccess(user.id, code, level, "migration", now))
        stores.users.set_role(user.id, "user")
        audit.record("role_migrated", "ok", user_id=user.id, old_role=user.role,
                     workspaces=",".join(code for code, _ in grants))
        moved += 1
    return moved
