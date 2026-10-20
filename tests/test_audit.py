import logging

from oracle_lab.accounts.memory import memory_stores
from oracle_lab.auth.audit import AuditLog


def test_audit_writes_store_and_log(caplog):
    stores = memory_stores()
    log = AuditLog(stores.audit, lambda: 5.0)
    with caplog.at_level(logging.INFO, logger="oracle_lab.audit"):
        log.record("login", "fail", ip="1.2.3.4", email="a@b.c", reason="bad password")
    assert "event=login outcome=fail user=- ip=1.2.3.4 email=a@b.c reason='bad password'" in caplog.text
    assert "password=" not in caplog.text
    [ev] = stores.audit.recent()
    assert ev.t == 5.0 and ev.detail == {"email": "a@b.c", "reason": "bad password"}


def test_log_injection_and_user_agent_are_neutralised(caplog):
    log = AuditLog(memory_stores().audit, lambda: 1.0)
    with caplog.at_level(logging.INFO, logger="oracle_lab.audit"):
        log.record("login", "ok", user_id="u1", ip="1.1.1.1\nevent=admin", user_agent="x" * 200, reason="a\r\nb")
    assert len(caplog.records) == 1
    msg = caplog.records[0].getMessage()
    assert "\n" not in msg and "\r" not in msg
    assert "user=u1" in msg and "x" * 81 not in msg
    assert "ua=" in msg


def test_empty_value_is_quoted(caplog):
    log = AuditLog(memory_stores().audit, lambda: 1.0)
    with caplog.at_level(logging.INFO, logger="oracle_lab.audit"):
        log.record("e", "ok", a="", b="x=y")
    assert "a='' b='x=y'" in caplog.text


def test_purge_removes_old_events():
    stores = memory_stores()
    t = [0.0]
    log = AuditLog(stores.audit, lambda: t[0])
    log.record("old", "ok")
    t[0] = 100 * 86400.0
    log.record("new", "ok")
    log.purge()
    assert [e.event for e in stores.audit.recent()] == ["new"]
