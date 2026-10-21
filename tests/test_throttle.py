import pytest

from oracle_lab.accounts.memory import memory_stores
from oracle_lab.auth.models import Throttled
from oracle_lab.auth.throttle import Throttle


def make():
    t = [0.0]
    return t, Throttle(memory_stores().throttle, lambda: t[0])


def test_login_delay_grows_after_five_failures():
    t, th = make()
    for _ in range(5):
        th.check_login("a@b.c", "ip")
        th.login_failed("a@b.c", "ip")
    with pytest.raises(Throttled) as e:
        th.check_login("a@b.c", "ip")
    assert e.value.retry_after == 1
    t[0] += 1
    th.check_login("a@b.c", "ip")
    th.login_failed("a@b.c", "ip")
    with pytest.raises(Throttled) as e:
        th.check_login("a@b.c", "ip")
    assert e.value.retry_after == 2
    th.login_succeeded("a@b.c")
    th.check_login("a@b.c", "ip")


def test_delay_is_capped_at_15_minutes():
    t, th = make()
    for _ in range(20):
        th.login_failed("a@b.c", "ip")
    with pytest.raises(Throttled) as e:
        th.check_login("a@b.c", "other")
    assert 1 <= e.value.retry_after <= 900


def test_email_is_normalised_and_message_is_generic():
    _, th = make()
    for _ in range(5):
        th.login_failed("  A@B.C ", "ip")
    with pytest.raises(Throttled) as e:
        th.check_login("a@b.c", "x")
    assert str(e.value) == "Too many attempts. Try again in a few minutes."


def test_ip_limit_30_in_15_minutes():
    t, th = make()
    for i in range(30):
        th.login_failed(f"u{i}@b.c", "1.1.1.1")
    th.check_login("new@b.c", "2.2.2.2")
    with pytest.raises(Throttled) as e:
        th.check_login("new@b.c", "1.1.1.1")
    assert e.value.retry_after >= 1
    t[0] += 901
    th.check_login("new@b.c", "1.1.1.1")


def test_success_clears_account_but_not_ip():
    _, th = make()
    for _ in range(30):
        th.login_failed("a@b.c", "1.1.1.1")
    th.login_succeeded("a@b.c")
    with pytest.raises(Throttled):
        th.check_login("a@b.c", "1.1.1.1")
    th.check_login("a@b.c", "3.3.3.3")


def test_three_registrations_per_ip_per_hour():
    t, th = make()
    for _ in range(3):
        th.check_register("ip")
        th.registered("ip")
    with pytest.raises(Throttled):
        th.check_register("ip")
    th.check_register("other")
    t[0] += 3601
    th.check_register("ip")


def test_google_limit_30_per_15_minutes():
    t, th = make()
    for _ in range(30):
        th.check_google("ip")
    with pytest.raises(Throttled):
        th.check_google("ip")
    t[0] += 901
    th.check_google("ip")


def test_retry_after_is_exactly_900_at_the_cap():
    _, th = make()
    for _ in range(20):
        th.login_failed("a@b.c", "ip")
    with pytest.raises(Throttled) as e:
        th.check_login("a@b.c", "other")
    assert e.value.retry_after == 900


def test_old_failures_stop_counting():
    t, th = make()
    for _ in range(5):
        th.login_failed("a@b.c", "ip")
    t[0] += 901
    th.check_login("a@b.c", "ip")


def test_ip_29_failures_pass_30_throttle():
    _, th = make()
    for i in range(29):
        th.login_failed(f"u{i}@b.c", "9.9.9.9")
    th.check_login("n@b.c", "9.9.9.9")
    th.login_failed("z@b.c", "9.9.9.9")
    with pytest.raises(Throttled):
        th.check_login("n@b.c", "9.9.9.9")


def audited():
    from oracle_lab.auth.audit import AuditLog

    t = [0.0]
    stores = memory_stores()
    clock = lambda: t[0]  # noqa: E731
    return t, stores, Throttle(stores.throttle, clock, AuditLog(stores.audit, clock))


def test_throttling_is_audited_without_the_email(caplog):
    import logging

    t, stores, th = audited()
    for _ in range(5):
        th.login_failed("Secret.Person@example.org", "1.2.3.4")
    with caplog.at_level(logging.INFO), pytest.raises(Throttled):
        th.check_login("secret.person@example.org", "1.2.3.4")
    (event,) = stores.audit.recent(event="throttled")
    assert (event.outcome, event.ip, event.user_id, event.detail) == ("denied", "1.2.3.4", None, {"kind": "login_account"})
    assert "secret.person" not in caplog.text.lower() and "secret.person" not in repr(event).lower()

    for _ in range(30):
        th.login_failed(f"u{_}@example.org", "5.6.7.8")
    with pytest.raises(Throttled):
        th.check_login("x@example.org", "5.6.7.8")
    for _ in range(3):
        th.registered("9.9.9.9")
    with pytest.raises(Throttled):
        th.check_register("9.9.9.9")
    with pytest.raises(Throttled):
        for _ in range(31):
            th.check_google("7.7.7.7")
    kinds = [e.detail["kind"] for e in reversed(stores.audit.recent(event="throttled"))]
    assert kinds == ["login_account", "login_ip", "register", "google"]


def test_throttle_audit_is_capped_at_ten_an_hour_per_key():
    t, stores, th = audited()
    for _ in range(3):
        th.registered("9.9.9.9")
    for _ in range(25):
        with pytest.raises(Throttled):
            th.check_register("9.9.9.9")
    assert len(stores.audit.recent(event="throttled")) == 10
    for _ in range(3):
        th.registered("8.8.8.8")  # another key has its own allowance
    with pytest.raises(Throttled):
        th.check_register("8.8.8.8")
    assert len(stores.audit.recent(event="throttled")) == 11
    t[0] += 3601
    for _ in range(3):
        th.registered("9.9.9.9")
    with pytest.raises(Throttled):
        th.check_register("9.9.9.9")
    assert len(stores.audit.recent(event="throttled")) == 12


def test_a_failing_audit_store_still_throttles():
    from oracle_lab.auth.audit import AuditLog

    class Broken:
        def add(self, event):
            raise OSError("down")

    stores = memory_stores()
    th = Throttle(stores.throttle, lambda: 0.0, AuditLog(Broken(), lambda: 0.0))
    for _ in range(3):
        th.registered("ip")
    with pytest.raises(Throttled):
        th.check_register("ip")
