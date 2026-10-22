from __future__ import annotations

import base64
import dataclasses
import threading
from types import SimpleNamespace

import pytest

from oracle_lab.accounts.memory import memory_stores
from oracle_lab.auth.account_settings import AccountSettings
from oracle_lab.auth.audit import AuditLog
from oracle_lab.auth.login import PasswordLogin
from oracle_lab.auth.models import (
    AuthError,
    EmailTaken,
    Identity,
    InvalidCredentials,
    Principal,
    ReauthRequired,
    RegistrationClosed,
    ResetToken,
    Throttled,
    WeakPassword,
)
from oracle_lab.auth.passwords import PasswordPolicy, _scrypt, needs_rehash
from oracle_lab.auth.registration import Registration, RegistrationPolicy
from oracle_lab.auth.sessions import SessionManager
from oracle_lab.auth.throttle import Throttle
from oracle_lab.auth.tokens import token_hash

PW = "a fine long passphrase"


@pytest.fixture
def app():
    t = [1000.0]
    clock = lambda: t[0]  # noqa: E731
    stores = memory_stores()
    sessions = SessionManager(stores.sessions, clock)
    throttle = Throttle(stores.throttle, clock)
    audit = AuditLog(stores.audit, clock)
    policy = PasswordPolicy(frozenset({"password1234567"}))
    reg_policy = RegistrationPolicy(stores.settings, stores.users, True, 100)
    created = []
    return SimpleNamespace(
        t=t, stores=stores, sessions=sessions, reg_policy=reg_policy, created=created,
        registration=Registration(stores, policy, reg_policy, sessions, throttle, audit, clock,
                                  created.append, first_user_is_admin=True),
        login=PasswordLogin(stores, sessions, throttle, audit, clock),
        settings=AccountSettings(stores, policy, sessions, audit, clock, throttle),
    )


def principal(app, result):
    rec = app.sessions.resolve(result.token)
    return Principal(result.user.id, result.user.email, result.user.role, rec.token_hash, rec.csrf_token,
                     rec.reauth_until)


def register(app, email="me@example.org", ip="1.1.1.1"):
    return app.registration.with_password(email, PW, ip, "ua")


def test_register_then_login(app):
    r = register(app)
    assert r.user.role == "admin"  # first user
    assert app.sessions.resolve(r.token)
    assert app.created == [r.user]
    assert app.login.login("me@example.org", PW, "1.1.1.1", "ua").user.id == r.user.id
    assert register(app, "two@example.org", "2.2.2.2").user.role == "user"


def test_email_is_normalised_everywhere(app):
    register(app, " Joanna@Gmail.com")
    assert app.login.login("joanna@gmail.com", PW, "ip", "ua")
    with pytest.raises(EmailTaken):
        app.registration.with_password("JOANNA@gmail.com", "another long passphrase", "ip2", "ua")


def test_invalid_email_rejected(app):
    with pytest.raises(AuthError, match="Enter a valid email address."):
        register(app, "not-an-email")


def test_failures_look_the_same(app):
    register(app)
    msgs = set()
    for email, pw in (("me@example.org", "wrong wrong wrong"), ("nobody@example.org", "whatever whatever")):
        with pytest.raises(InvalidCredentials) as e:
            app.login.login(email, pw, "ip", "ua")
        msgs.add(str(e.value))
    assert msgs == {"Email or password is incorrect."}


def test_locked_user_cannot_log_in(app):
    r = register(app)
    app.stores.users.update(dataclasses.replace(r.user, status="locked"))
    with pytest.raises(InvalidCredentials, match="Email or password is incorrect."):
        app.login.login("me@example.org", PW, "1.1.1.1", "ua")


def test_registration_closed_and_cap(app):
    app.reg_policy.set(open=None, max_users=1)
    register(app)
    with pytest.raises(RegistrationClosed, match="Registration is closed."):
        register(app, "two@example.org")
    app.reg_policy.set(open=False, max_users=10)
    with pytest.raises(RegistrationClosed):
        register(app, "two@example.org")
    app.reg_policy.set(open=True, max_users=None)
    assert register(app, "two@example.org")


def test_weak_password_lists_problems(app):
    with pytest.raises(WeakPassword) as e:
        app.registration.with_password("me@example.org", "short", "ip", "ua")
    assert str(e.value) == "Choose a stronger password." and e.value.problems


def test_change_password_rotates_and_ends_other_sessions(app):
    r = register(app)
    other = app.login.login("me@example.org", PW, "9.9.9.9", "other")
    p = principal(app, r)
    with pytest.raises(InvalidCredentials, match="Your current password is incorrect."):
        app.settings.change_password(p, "nope nope nope nope", "brand new passphrase", r.token)
    new = app.settings.change_password(p, PW, "brand new passphrase", r.token)
    assert new.token != r.token
    assert app.sessions.resolve(new.token)
    assert app.sessions.resolve(r.token) is None and app.sessions.resolve(other.token) is None
    with pytest.raises(InvalidCredentials):
        app.login.login("me@example.org", PW, "ip", "ua")
    assert app.login.login("me@example.org", "brand new passphrase", "ip", "ua")


def test_set_password_requires_reauth(app):
    r = register(app)
    app.stores.users.add_identity(Identity("google", "g1", r.user.id))
    app.stores.users.remove_identity(r.user.id, "password")
    p = principal(app, r)
    with pytest.raises(ReauthRequired, match="Confirm with Google first."):
        app.settings.set_password(p, "brand new passphrase", r.token)
    app.sessions.mark_reauth(r.token)
    p = principal(app, r)
    new = app.settings.set_password(p, "brand new passphrase", r.token)
    assert app.sessions.resolve(new.token) and app.sessions.resolve(r.token) is None
    assert app.settings.profile(principal(app, new))["methods"] == ["google", "password"]
    assert app.login.login("me@example.org", "brand new passphrase", "ip", "ua")


def test_reset_token_is_single_use_and_ends_sessions(app):
    r = register(app)
    app.stores.resets.add(ResetToken(token_hash("tok"), r.user.id, "admin", app.t[0] + 600))
    app.settings.reset_with_token("tok", "brand new passphrase", "ip", "ua")
    assert app.sessions.resolve(r.token) is None
    with pytest.raises(AuthError, match="This reset link is invalid or has expired."):
        app.settings.reset_with_token("tok", "yet another passphrase", "ip", "ua")
    assert app.login.login("me@example.org", "brand new passphrase", "ip", "ua")


def test_session_listing_leaves_out_expired_sessions(app):
    r = register(app)
    app.t[0] += 6 * 86400
    app.login.login("me@example.org", PW, "9.9.9.9", "fresh")
    app.t[0] += 2 * 86400  # the first session is now idle for 8 days: past the 7-day idle limit
    fresh = app.login.login("me@example.org", PW, "9.9.9.9", "fresher")
    listed = app.settings.sessions(principal(app, fresh))
    assert [s["user_agent"] for s in listed] == ["fresh", "fresher"]
    assert token_hash(r.token) not in {s["id"] for s in listed}


def test_session_listing_and_ending(app):
    r = register(app)
    other = app.login.login("me@example.org", PW, "9.9.9.9", "other")
    stranger = register(app, "x@example.org", "3.3.3.3")
    p = principal(app, r)
    listed = app.settings.sessions(p)
    assert len(listed) == 2 and [s["current"] for s in listed].count(True) == 1
    app.settings.end_session(p, token_hash(stranger.token))  # not ours: no-op
    assert app.sessions.resolve(stranger.token)
    app.settings.end_other_sessions(p)
    assert app.sessions.resolve(other.token) is None and app.sessions.resolve(r.token)
    assert app.settings.profile(p) == {"id": p.user_id, "email": "me@example.org", "display_name": "me", "role": "admin",
                                       "methods": ["password"]}


def test_audit_records_register_login_fail_logout(app):
    r = register(app)
    with pytest.raises(InvalidCredentials):
        app.login.login("me@example.org", "wrong wrong wrong", "ip", "ua")
    app.login.logout(r.token)
    events = {(e.event, e.outcome) for e in app.stores.audit.recent()}
    assert {("register", "ok"), ("login", "fail"), ("logout", "ok")} <= events
    assert PW not in repr(app.stores.audit.recent())


def reasons(app, event="login"):
    return [e.detail.get("reason") for e in app.stores.audit.recent(event=event) if e.outcome == "fail"]


def test_each_login_failure_is_audited_with_its_reason(app):
    r = register(app)
    app.stores.users.add(*_google_only_user())
    with pytest.raises(InvalidCredentials):
        app.login.login("nobody@example.org", "whatever whatever", "ip", "ua")
    with pytest.raises(InvalidCredentials):
        app.login.login("g@example.org", "whatever whatever", "ip", "ua")
    with pytest.raises(InvalidCredentials):
        app.login.login("me@example.org", "whatever whatever", "ip", "ua")
    app.stores.users.update(dataclasses.replace(r.user, status="locked"))
    with pytest.raises(InvalidCredentials):
        app.login.login("me@example.org", PW, "ip", "ua")
    assert sorted(reasons(app)) == ["bad_password", "locked", "no_password", "unknown_email"]


def _google_only_user():
    from oracle_lab.auth.models import Identity, User
    u = User("g1", "g@example.org", "g", "user", "active", 0.0, None, None)
    return u, Identity("google", "gsub", "g1")


def test_email_taken_is_audited(app):
    register(app)
    with pytest.raises(EmailTaken):
        register(app, ip="2.2.2.2")
    assert reasons(app, "register") == ["email_taken"]


def test_old_hash_is_rehashed_on_login(app):
    r = register(app)
    salt = b"0" * 16
    b64 = lambda raw: base64.b64encode(raw).decode()  # noqa: E731
    old = f"scrypt$1024$8$1${b64(salt)}${b64(_scrypt(PW, salt, 1024, 8, 1))}"
    app.stores.users.set_password(r.user.id, old, 5.0)
    result = app.login.login("me@example.org", PW, "ip", "ua")
    stored = app.stores.users.identities(r.user.id)[0].password_hash
    assert stored != old and not needs_rehash(stored)
    assert app.login.login("me@example.org", PW, "ip", "ua")
    assert result.user.last_login_at == app.t[0]


def test_login_does_not_undo_a_concurrent_lock(app):
    r = register(app)
    real = app.stores.users.record_login

    def lock_then_record(user_id, t):
        app.stores.users.update(dataclasses.replace(app.stores.users.get(user_id), status="locked"))
        real(user_id, t)

    app.stores.users.record_login = lock_then_record
    app.login.login("me@example.org", PW, "ip", "ua")
    assert app.stores.users.get(r.user.id).status == "locked"


def test_login_is_throttled_after_repeated_failures(app):
    register(app)
    for _ in range(5):
        with pytest.raises(InvalidCredentials):
            app.login.login("me@example.org", "wrong wrong wrong", "ip", "ua")
    with pytest.raises(Throttled):
        app.login.login("me@example.org", PW, "ip", "ua")


def test_locked_user_with_correct_password_counts_as_a_failure(app):
    r = register(app)
    app.stores.users.update(dataclasses.replace(r.user, status="locked"))
    for _ in range(5):
        with pytest.raises(InvalidCredentials):
            app.login.login("me@example.org", PW, "ip", "ua")
    with pytest.raises(Throttled):
        app.login.login("me@example.org", PW, "ip", "ua")


def test_taken_email_probing_is_throttled_per_ip(app):
    register(app)
    for _ in range(3):
        with pytest.raises(EmailTaken):
            register(app, ip="8.8.8.8")
    with pytest.raises(Throttled):
        register(app, ip="8.8.8.8")


def test_concurrent_signups_respect_the_cap(app):
    app.reg_policy.set(open=True, max_users=3)
    outcomes = []

    def go(i):
        try:
            register(app, f"u{i}@example.org", f"10.0.0.{i}")
            outcomes.append("ok")
        except RegistrationClosed:
            outcomes.append("closed")

    threads = [threading.Thread(target=go, args=(i,)) for i in range(10)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert outcomes.count("ok") == 3 and app.stores.users.count() == 3


def test_concurrent_first_signups_make_exactly_one_admin(app):
    results = []

    def go(i):
        results.append(register(app, f"u{i}@example.org", f"10.0.0.{i}"))

    threads = [threading.Thread(target=go, args=(i,)) for i in range(2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(r.user.role for r in results) == ["admin", "user"]


def test_weak_reset_password_does_not_burn_the_link(app):
    r = register(app)
    app.stores.resets.add(ResetToken(token_hash("tok"), r.user.id, "admin", app.t[0] + 600))
    with pytest.raises(WeakPassword):
        app.settings.reset_with_token("tok", "short", "ip", "ua")
    app.settings.reset_with_token("tok", "brand new passphrase", "ip", "ua")


def test_reset_for_a_missing_user_is_audited(app):
    app.stores.resets.add(ResetToken(token_hash("tok"), "ghost", "admin", app.t[0] + 600))
    with pytest.raises(AuthError):
        app.settings.reset_with_token("tok", "brand new passphrase", "ip", "ua")
    assert reasons(app, "password_reset") == ["user_missing"]


def test_wrong_current_password_guesses_are_throttled(app):
    r = register(app)
    p = principal(app, r)
    for _ in range(5):
        with pytest.raises(InvalidCredentials):
            app.settings.change_password(p, "nope nope nope nope", "brand new passphrase", r.token, ip="ip")
    with pytest.raises(Throttled):
        app.settings.change_password(p, PW, "brand new passphrase", r.token, ip="ip")


def test_session_endings_are_audited(app):
    r = register(app)
    other = app.login.login("me@example.org", PW, "9.9.9.9", "other")
    p = principal(app, r)
    app.settings.end_session(p, token_hash(other.token))
    app.settings.end_other_sessions(p)
    events = {e.event for e in app.stores.audit.recent()}
    assert {"session_ended", "other_sessions_ended"} <= events
