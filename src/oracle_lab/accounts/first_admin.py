"""The first administrator, and the one-time import of the single-user app's progress and notes."""

from __future__ import annotations

import logging
from collections.abc import Callable

from oracle_lab.accounts.repositories import AppStores
from oracle_lab.auth.audit import AuditLog
from oracle_lab.auth.models import Identity, User
from oracle_lab.auth.passwords import hash_password
from oracle_lab.auth.tokens import new_id
from oracle_lab.config import Settings
from oracle_lab.services import Clock
from oracle_lab.study.notes import PersonalNotes
from oracle_lab.study.state import StateStore, new_state

log = logging.getLogger(__name__)

LEGACY_IMPORTED = "legacy_imported"
ADMIN_EMAIL_CLAIM = "admin_email_claim"
_NO_SUCH_TABLE = "ORA-00942"


def first_user_is_admin(settings: Settings) -> bool:
    """Without STUDY_ADMIN_EMAIL the first account to register becomes the admin."""
    return settings.admin_email is None


def ensure_first_admin(stores: AppStores, settings: Settings, clock: Clock, audit: AuditLog,
                       on_user_created: Callable[[User], None] = lambda user: None) -> None:
    """Runs at start-up. Does nothing once any account exists or without STUDY_ADMIN_EMAIL.
    With STUDY_ADMIN_PASSWORD the admin is created now; otherwise the email is reserved so that the
    account signing in with Google under it becomes the admin."""
    email = settings.admin_email
    if email is None or stores.users.count() > 0:
        return
    if settings.admin_password is None:
        if not stores.settings.get(ADMIN_EMAIL_CLAIM) and stores.users.by_email(email) is None:
            stores.settings.set(ADMIN_EMAIL_CLAIM, email)
        return
    uid = new_id()
    now = clock()
    user = User(id=uid, email=email, display_name=email.split("@")[0], role="admin", status="active",
                created_at=now, last_login_at=None, password_changed_at=now)
    stores.users.add(user, Identity("password", uid, uid, hash_password(settings.admin_password.reveal())))
    audit.record("admin_bootstrapped", "ok", user_id=uid, email=email)
    on_user_created(user)


def import_legacy(stores: AppStores, user_id: str, legacy_state: StateStore | None,
                  legacy_notes: PersonalNotes | None) -> bool:
    """Copies the single-user progress and personal notes into the account, once (setting `legacy_imported`).
    The sources are left alone. A source that does not exist, such as the LAB_STATE and LAB_NOTES tables of
    a fresh Oracle install (ORA-00942), counts as empty. Returns False when the import was done before."""
    if stores.settings.get(LEGACY_IMPORTED) == "1":
        return False
    state = _read(legacy_state.load, new_state()) if legacy_state is not None else new_state()
    if state != new_state():
        with stores.states.for_user(user_id).transaction() as target:
            target.clear()
            target.update(state)
    if legacy_notes is not None:
        target_notes = stores.notes.for_user(user_id)
        for name, title in _read(legacy_notes.entries, []):
            text = legacy_notes.read(name)
            if text is not None:
                target_notes.add(name.removesuffix(".md"), title, text)
    stores.settings.set(LEGACY_IMPORTED, "1")
    return True


def legacy_hook(stores: AppStores, legacy_state: StateStore | None,
                legacy_notes: PersonalNotes | None) -> Callable[[User], None]:
    """The on_user_created hook: the first admin receives the legacy data."""
    def on_user_created(user: User) -> None:
        if user.role == "admin" and import_legacy(stores, user.id, legacy_state, legacy_notes):
            log.info("imported the single-user progress and notes into %s", user.id)
    return on_user_created


def _read(read: Callable, default):
    try:
        return read()
    except Exception as exc:  # noqa: BLE001 - oracledb is optional here; only "table missing" is tolerated
        if _NO_SUCH_TABLE in str(exc):
            return default
        raise
