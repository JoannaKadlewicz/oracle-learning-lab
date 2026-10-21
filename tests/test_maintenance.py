"""The periodic purge of expired sessions, sign-in flows, throttle counters and old audit events."""

import threading

from oracle_lab.accounts.maintenance import Maintenance
from oracle_lab.accounts.memory import memory_stores
from oracle_lab.auth.audit import AuditLog
from oracle_lab.auth.models import AuditEvent, LoginFlow, SessionRecord

NOW = 1_800_000_000.0
DAY = 86400


def _filled():
    stores = memory_stores()
    for name, expires in (("old", NOW - 1), ("live", NOW + DAY)):
        stores.sessions.add(SessionRecord(name, "u1", "c", NOW - 2 * DAY, NOW - 1, expires, "ip", "ua"))
        stores.flows.add(LoginFlow(name, "s", "n", "v", "login", None, "/", expires))
    stores.throttle.record("login:ip:1", NOW - 3 * 3600)
    stores.throttle.record("login:ip:2", NOW - 600)
    stores.audit.add(AuditEvent(NOW - 91 * DAY, "login", "ok", "u1", "", ""))
    stores.audit.add(AuditEvent(NOW - 89 * DAY, "logout", "ok", "u1", "", ""))
    return stores


def _check_purged(stores):
    assert stores.sessions.get("old") is None and stores.sessions.get("live") is not None
    assert stores.flows.take("old") is None and stores.flows.take("live") is not None
    assert stores.throttle.last("login:ip:1") is None and stores.throttle.last("login:ip:2") == NOW - 600
    assert [e.event for e in stores.audit.recent()] == ["logout"]


def test_run_once_purges_each_kind():
    stores = _filled()
    Maintenance(stores, AuditLog(stores.audit, lambda: NOW), lambda: NOW).run_once()
    _check_purged(stores)


def test_a_failing_step_does_not_skip_the_others(caplog):
    stores = _filled()

    def broken(now):
        raise RuntimeError("database down")
    stores.sessions.purge = broken
    Maintenance(stores, AuditLog(stores.audit, lambda: NOW), lambda: NOW).run_once()
    assert stores.flows.take("old") is None and [e.event for e in stores.audit.recent()] == ["logout"]
    assert "purging expired sessions failed" in caplog.text


def test_the_thread_runs_soon_after_start_and_stops():
    stores = _filled()
    ran = threading.Event()
    maintenance = Maintenance(stores, AuditLog(stores.audit, lambda: NOW), lambda: NOW, first_run_after=0.01,
                              interval=3600)
    original = maintenance.run_once
    maintenance.run_once = lambda: (original(), ran.set())
    maintenance.start()
    assert ran.wait(5)
    maintenance.stop()
    maintenance._thread.join(5)
    assert not maintenance._thread.is_alive()
    _check_purged(stores)
