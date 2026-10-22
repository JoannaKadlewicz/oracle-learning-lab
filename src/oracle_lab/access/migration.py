"""Start-up migration from account roles to workspace access. Accounts with the old roles become users:
`learner` with a subscription to every workspace (nobody loses anything), `free` with free access to the
workspace they had chosen. Idempotent: only accounts still holding an old role are touched."""

from __future__ import annotations

import logging

from oracle_lab import exams
from oracle_lab.access.models import WorkspaceAccess
from oracle_lab.accounts.repositories import AppStores
from oracle_lab.auth.audit import AuditLog
from oracle_lab.auth.models import User
from oracle_lab.services import Clock
from oracle_lab.study.tracks import exam_code

OLD_ROLES = ("learner", "free")
log = logging.getLogger(__name__)


def migrate_roles(stores: AppStores, clock: Clock, audit: AuditLog) -> int:
    """Moves every account with an old role; returns how many were moved."""
    moved = 0
    for user in stores.users.all():
        if user.role not in OLD_ROLES:
            continue
        try:
            _migrate(stores, clock, audit, user)
        except Exception:  # noqa: BLE001 - one bad account must not keep the others on their old roles
            log.exception("moving account %s from role %s to workspace access failed", user.id, user.role)
            continue
        moved += 1
    return moved


def _migrate(stores: AppStores, clock: Clock, audit: AuditLog, user: User) -> None:
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


def migrate_plans(stores: AppStores, clock: Clock, audit: AuditLog) -> int:
    """From per-workspace levels to account plans: a user subscribed anywhere becomes pro; every access row becomes
    a plain membership. Per account, like migrate_roles; returns how many accounts changed."""
    changed = 0
    for user in stores.users.all():
        rows = stores.access.for_user(user.id)
        old = [r for r in rows if r.level != "member"]
        if not old:
            continue
        try:
            # The plan first: rewriting the rows erases what it is decided from, so a failure must not come between.
            if user.role == "user" and any(r.level == "subscribed" for r in old):
                stores.users.set_role(user.id, "pro")
                audit.record("role_migrated", "ok", user_id=user.id, old_role="user", new_role="pro")
            for r in old:
                stores.access.put(WorkspaceAccess(r.user_id, r.workspace, "member", r.granted_by, r.granted_at))
        except Exception:  # noqa: BLE001
            log.exception("moving account %s to plans failed", user.id)
            continue
        changed += 1
    return changed
