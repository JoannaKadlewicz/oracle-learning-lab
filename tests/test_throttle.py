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
