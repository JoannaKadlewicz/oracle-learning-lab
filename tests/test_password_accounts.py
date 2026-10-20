from __future__ import annotations

import dataclasses
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
    WeakPassword,
)
from oracle_lab.auth.passwords import PasswordPolicy
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
        settings=AccountSettings(stores, policy, sessions, audit, clock),
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
    assert register(app, "two@example.org", "2.2.2.2").user.role == "learner"


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
    assert app.settings.profile(p) == {"email": "me@example.org", "display_name": "me", "role": "admin",
                                       "methods": ["password"]}


def test_audit_records_register_login_fail_logout(app):
    r = register(app)
    with pytest.raises(InvalidCredentials):
        app.login.login("me@example.org", "wrong wrong wrong", "ip", "ua")
    app.login.logout(r.token)
    events = {(e.event, e.outcome) for e in app.stores.audit.recent()}
    assert {("register", "ok"), ("login", "fail"), ("logout", "ok")} <= events
    assert PW not in repr(app.stores.audit.recent())
