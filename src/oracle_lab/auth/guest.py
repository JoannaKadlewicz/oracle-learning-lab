"""Guests: "Try it without an account" makes a real account with the guest plan (no e-mail, no password), so every
study path works for it; registering from a guest session moves its progress to the new account."""

from __future__ import annotations

import logging

from oracle_lab.access.models import WorkspaceAccess
from oracle_lab.accounts.repositories import AppStores, UserRepository
from oracle_lab.auth.audit import AuditLog
from oracle_lab.auth.models import Identity, SessionRecord, User
from oracle_lab.auth.sessions import SessionManager
from oracle_lab.auth.throttle import Throttle
from oracle_lab.auth.tokens import new_id
from oracle_lab.services import Clock

log = logging.getLogger(__name__)
GUEST_DOMAIN = "guest.invalid"  # a reserved domain: a guest's placeholder address can never be a real one


def accounts(users: UserRepository) -> int:
    """How many real accounts exist: guests count neither toward the user cap nor for "the first account"."""
    return sum(1 for user in users.all() if user.role != "guest")


class GuestAccess:
    def __init__(self, stores: AppStores, sessions: SessionManager, throttle: Throttle, audit: AuditLog, clock: Clock):
        self._stores = stores
        self._sessions = sessions
        self._throttle = throttle
        self._audit = audit
        self._clock = clock

    def start(self, ip: str, user_agent: str) -> tuple[str, SessionRecord]:
        """A new guest account and its session (Throttled after too many from one address)."""
        self._throttle.check_guest(ip)
        now = self._clock()
        uid = new_id()
        user = User(uid, f"{uid}@{GUEST_DOMAIN}", "Guest", "guest", "active", now, now, None)
        self._stores.users.add(user, Identity("guest", uid, uid))
        self._throttle.guest_started(ip)
        token, record = self._sessions.start(uid, ip, user_agent)
        self._audit.record("guest_started", "ok", user_id=uid, ip=ip, user_agent=user_agent)
        return token, record


def adopt_guest(stores: AppStores, guest_id: str, user_id: str, audit: AuditLog | None = None) -> None:
    """Moves a guest's progress, personal notes and workspace to the account just created from its session, then
    deletes the guest. Never raises: the new account must not fail because of the old guest."""
    guest = stores.users.get(guest_id)
    if guest is None or guest.role != "guest" or guest_id == user_id:
        return
    try:
        state = stores.states.for_user(guest_id).load()
        with stores.states.for_user(user_id).transaction() as fresh:
            fresh.clear()
            fresh.update(state)
        old, new = stores.notes.for_user(guest_id), stores.notes.for_user(user_id)
        for name, title in old.entries():
            text = old.read(name)
            if text is not None:
                new.add(name.rsplit(".", 1)[0], title, text)
        for row in stores.access.for_user(guest_id):
            stores.access.put(WorkspaceAccess(user_id, row.workspace, "member", user_id, row.granted_at))
        stores.users.delete(guest_id)
        if audit is not None:
            audit.record("guest_adopted", "ok", user_id=user_id, guest=guest_id)
    except Exception:  # noqa: BLE001
        log.exception("moving guest %s into account %s failed", guest_id, user_id)
