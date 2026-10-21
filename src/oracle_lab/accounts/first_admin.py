"""The first administrator, and the one-time import of the single-user app's progress and notes."""

from __future__ import annotations

import logging
from collections.abc import Callable
from urllib.parse import urlsplit

from oracle_lab.accounts.repositories import AppStores
from oracle_lab.auth.audit import AuditLog
from oracle_lab.auth.models import Identity, User
from oracle_lab.auth.passwords import hash_password
from oracle_lab.auth.registration import ADMIN_EMAIL_CLAIM
from oracle_lab.auth.tokens import new_id
from oracle_lab.config import Settings
from oracle_lab.services import Clock
from oracle_lab.study.notes import PersonalNotes
from oracle_lab.study.state import StateStore, new_state

log = logging.getLogger(__name__)

LEGACY_IMPORTED = "legacy_imported"
_NO_SUCH_TABLE = "ORA-00942"
_LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1")
NOT_IMPORTED = "legacy progress not imported: set STUDY_ADMIN_EMAIL to receive it"


def first_user_is_admin(settings: Settings) -> bool:
    """Without STUDY_ADMIN_EMAIL the first account to register becomes the admin."""
    return settings.admin_email is None


def is_local(public_url: str) -> bool:
    """The app is reached on this machine only (the single-user setup), not as a hosted site."""
    return urlsplit(public_url).hostname in _LOCAL_HOSTS


def receives_legacy(user: User, settings: Settings) -> bool:
    """Who may receive the single-user progress: the admin created from STUDY_ADMIN_EMAIL (password bootstrap or
    Google claim); without it, a self-registered first admin only on a local install. On a hosted site whoever
    registers first could be a stranger, so the progress waits for STUDY_ADMIN_EMAIL there."""
    if user.role != "admin":
        return False
    if settings.admin_email is not None:
        return user.email == settings.admin_email
    return is_local(settings.public_url)


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


Sources = Callable[[], tuple[StateStore | None, PersonalNotes | None]]


def import_legacy(stores: AppStores, user_id: str, legacy_state: StateStore | None,
                  legacy_notes: PersonalNotes | None) -> bool:
    """Copies the single-user progress and personal notes into the account, once (setting `legacy_imported`).
    The sources are left alone. A source that does not exist, such as the LAB_STATE and LAB_NOTES tables of
    a fresh Oracle install (ORA-00942), counts as empty. Returns False when the import was done before.
    When copying fails the account's state and notes are emptied again (it must have had none), so a
    retry starts clean, and the error is re-raised."""
    if stores.settings.get(LEGACY_IMPORTED) == "1":
        return False
    try:
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
    except Exception:
        try:
            stores.states.delete(user_id)
            stores.notes.delete(user_id)
        except Exception:  # noqa: BLE001
            log.exception("could not undo the partial legacy import for %s", user_id)
        raise
    stores.settings.set(LEGACY_IMPORTED, "1")
    return True


def _try_import(stores: AppStores, audit: AuditLog, user: User, sources: Sources) -> None:
    """Never raises: a failure is logged and audited, and the import is retried at the next start."""
    try:
        state, notes = sources()
        if import_legacy(stores, user.id, state, notes):
            log.info("imported the single-user progress and notes into %s", user.id)
    except Exception as exc:  # noqa: BLE001 - sign-up and start-up must complete
        log.exception("importing the single-user progress into %s failed", user.id)
        try:
            audit.record("legacy_import", "fail", user_id=user.id, reason=type(exc).__name__)
        except Exception:  # noqa: BLE001
            log.exception("could not audit the failed legacy import")


def _has_legacy_data(sources: Sources) -> bool:
    """True unless the sources are known to be empty (an unreadable source counts as data, to be safe)."""
    try:
        state, notes = sources()
        if state is not None and _read(state.load, new_state()) != new_state():
            return True
        return notes is not None and bool(_read(notes.entries, []))
    except Exception:  # noqa: BLE001
        log.exception("could not read the single-user progress")
        return True


def _withhold(stores: AppStores, sources: Sources) -> None:
    """The legacy data has nobody to go to (yet): marked done when there is nothing to import, else warned about
    and left pending for a later STUDY_ADMIN_EMAIL admin."""
    if _has_legacy_data(sources):
        log.warning(NOT_IMPORTED)
    else:
        stores.settings.set(LEGACY_IMPORTED, "1")


def legacy_hook(stores: AppStores, sources: Sources, audit: AuditLog,
                settings: Settings) -> Callable[[User], None]:
    """The on_user_created hook: the admin that receives_legacy() gets the legacy data. `sources` is called lazily."""
    def on_user_created(user: User) -> None:
        if user.role != "admin" or stores.settings.get(LEGACY_IMPORTED) == "1":
            return
        if receives_legacy(user, settings):
            _try_import(stores, audit, user, sources)
        else:
            _withhold(stores, sources)
    return on_user_created


def retry_legacy_import(stores: AppStores, sources: Sources, audit: AuditLog, settings: Settings) -> None:
    """At start-up: a pending import goes to the admin with STUDY_ADMIN_EMAIL, or without it to the earliest admin
    on a local install only, and only while that account has no progress and no notes (a retry can neither
    overwrite nor duplicate); else it is marked done. Without a receiving admin it stays pending."""
    try:
        if stores.settings.get(LEGACY_IMPORTED) == "1":
            return
        admins = [u for u in stores.users.all() if u.role == "admin"]
        if not admins:
            return
        if settings.admin_email is not None:
            admin = next((u for u in admins if u.email == settings.admin_email), None)
        else:
            admin = min(admins, key=lambda u: u.created_at)
        if admin is None or not receives_legacy(admin, settings):
            _withhold(stores, sources)
            return
        if stores.states.for_user(admin.id).load() != new_state() or stores.notes.for_user(admin.id).entries():
            stores.settings.set(LEGACY_IMPORTED, "1")
            log.warning("legacy import skipped: the admin account %s already has progress or notes", admin.id)
            return
    except Exception:  # noqa: BLE001 - e.g. the state database is not reachable yet; the next start retries
        log.exception("could not check whether the legacy import is pending")
        return
    _try_import(stores, audit, admin, sources)


def _read(read: Callable, default):
    try:
        return read()
    except Exception as exc:  # noqa: BLE001 - oracledb is optional here; only "table missing" is tolerated
        if _NO_SUCH_TABLE in str(exc):
            return default
        raise
