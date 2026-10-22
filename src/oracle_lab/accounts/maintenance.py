"""The periodic clean-up of expired account data: sessions, sign-in flows, throttle counters and old audit events."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from oracle_lab.accounts.repositories import AppStores
from oracle_lab.auth.audit import AuditLog
from oracle_lab.services import Clock

log = logging.getLogger(__name__)

THROTTLE_KEEP = 2 * 3600  # the longest throttle window is one hour
AUDIT_KEEP_DAYS = 90
GUEST_IDLE_DAYS = 30  # a guest account started this long ago, with no live session, is deleted
DAY = 86400.0
FIRST_RUN_AFTER = 30.0
INTERVAL = 3600.0


class Maintenance:
    """run_once() purges each kind on its own (a failing step is logged and does not skip the others);
    start() runs it in a daemon thread shortly after start-up and then hourly, until stop()."""

    def __init__(self, stores: AppStores, audit: AuditLog, clock: Clock, first_run_after: float = FIRST_RUN_AFTER,
                 interval: float = INTERVAL):
        self._stores = stores
        self._audit = audit
        self._clock = clock
        self._first_run_after = first_run_after
        self._interval = interval
        self._stopped = threading.Event()
        self._thread: threading.Thread | None = None

    def run_once(self) -> None:
        now = self._clock()
        steps: list[tuple[str, Callable[[], None]]] = [
            ("sessions", lambda: self._stores.sessions.purge(now)),
            ("login flows", lambda: self._stores.flows.purge(now)),
            ("throttle counters", lambda: self._stores.throttle.purge(now - THROTTLE_KEEP)),
            ("audit events", lambda: self._audit.purge(AUDIT_KEEP_DAYS)),
            ("guests", lambda: self._purge_guests(now)),
        ]
        for name, step in steps:
            try:
                step()
            except Exception:  # noqa: BLE001 - the next step and the next run still happen
                log.exception("purging expired %s failed", name)

    def _purge_guests(self, now: float) -> None:
        """Guests without a live session that started more than GUEST_IDLE_DAYS ago (a guest has no way back in
        once its session is gone)."""
        for user in self._stores.users.all():
            if (user.role == "guest" and user.created_at < now - GUEST_IDLE_DAYS * DAY
                    and not self._stores.sessions.for_user(user.id)):
                self._stores.users.delete(user.id)
                self._audit.record("guest_purged", "ok", user_id=user.id)

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, name="maintenance", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stopped.set()

    def _loop(self) -> None:
        wait = self._first_run_after
        while not self._stopped.wait(wait):
            self.run_once()
            wait = self._interval
