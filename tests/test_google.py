from __future__ import annotations

import base64
import json
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest

from oracle_lab.accounts.memory import memory_stores
from oracle_lab.auth.audit import AuditLog
from oracle_lab.auth.google import (
    AUTH_URL,
    GENERIC,
    GoogleError,
    GoogleSignIn,
    HttpTokenEndpoint,
    id_token_claims,
    validate_claims,
)
from oracle_lab.auth.models import AuthError, Identity, Principal, Throttled, User
from oracle_lab.auth.passwords import PasswordPolicy
from oracle_lab.auth.registration import Registration, RegistrationPolicy
from oracle_lab.auth.sessions import SessionManager
from oracle_lab.auth.throttle import Throttle
from oracle_lab.config import GoogleConfig
from oracle_lab.credentials import Secret

CID = "cid.apps.googleusercontent.com"
EXISTS = ("An account with this email already exists. Sign in with your password, "
          "then connect Google in Settings.")


def b64(obj) -> str:
    return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()


def id_token(claims) -> str:
    return f"{b64({'alg': 'RS256'})}.{b64(claims)}.sig"


class FakeEndpoint:
    def __init__(self):
        self.claims: dict = {}
        self.calls: list = []
        self.fail = False

    def exchange(self, code, code_verifier, redirect_uri):
        self.calls.append((code, code_verifier, redirect_uri))
        if self.fail:
            raise GoogleError("boom")
        return {"id_token": id_token(self.claims)}


@pytest.fixture
def g():
    t = [1000.0]
    clock = lambda: t[0]  # noqa: E731
    stores = memory_stores()
    sessions = SessionManager(stores.sessions, clock)
    throttle = Throttle(stores.throttle, clock)
    audit = AuditLog(stores.audit, clock)
    policy = RegistrationPolicy(stores.settings, stores.users, True, 100)
    created: list[User] = []
    reg = Registration(stores, PasswordPolicy(frozenset()), policy, sessions, throttle, audit, clock,
                       created.append)
    ep = FakeEndpoint()
    sign_in = GoogleSignIn(GoogleConfig(CID, Secret.from_value("s", "test")), "https://lab.example", ep, stores,
                           sessions, throttle, audit, clock, reg)
    ns = SimpleNamespace(t=t, stores=stores, sessions=sessions, ep=ep, g=sign_in, created=created, policy=policy,
                         audit=audit)

    def claims(**over):
        flow = next(iter(stores.flows._flows.values()))  # noqa: SLF001
        c = {"iss": "https://accounts.google.com", "aud": CID, "exp": t[0] + 600, "nonce": flow.nonce,
             "sub": "sub-1", "email": "Ann@Example.org", "email_verified": True, "name": "Ann A"}
        c.update(over)
        return c

    def run(intent="login", current=None, **over):
        url, fid = sign_in.start(intent, "/next", current, "1.1.1.1")
        ns.ep.claims = claims(**over)
        state = parse_qs(urlparse(url).query)["state"][0]
        return fid, state

    ns.run = run
    return ns


def test_start_builds_pkce_url(g):
    url, fid = g.g.start("login", "/x", None, "1.1.1.1")
    assert url.startswith(AUTH_URL + "?")
    q = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
    flow = g.stores.flows.take(fid)
    import hashlib
    challenge = base64.urlsafe_b64encode(hashlib.sha256(flow.code_verifier.encode()).digest()).rstrip(b"=").decode()
    assert q["code_challenge"] == challenge and q["code_challenge_method"] == "S256"
    assert q["redirect_uri"] == "https://lab.example/auth/google/callback"
    assert q["state"] == flow.state and q["nonce"] == flow.nonce
    assert (q["response_type"], q["scope"], q["prompt"], q["client_id"]) == (
        "code", "openid email profile", "select_account", CID)
    assert flow.expires_at == 1600.0 and flow.next_path == "/x"


def test_start_validates_intent_and_principal(g):
    with pytest.raises(ValueError):
        g.g.start("bogus", "/", None, "ip")
    for intent in ("link", "reauth"):
        with pytest.raises(AuthError) as e:
            g.g.start(intent, "/", None, "ip")
        assert e.value.status == 401


def test_start_is_throttled(g):
    with pytest.raises(Throttled):
        for _ in range(100):
            g.g.start("login", "/", None, "9.9.9.9")


def test_new_google_user_is_created_and_logged_in(g):
    fid, state = g.run()
    out = g.g.finish(fid, state, "code", "1.1.1.1", "ua", None)
    assert out.message is None and out.token and out.next_path == "/next"
    user = g.stores.users.by_identity("google", "sub-1")
    assert (user.email, user.display_name, user.role) == ("ann@example.org", "Ann A", "user")
    assert user.last_login_at == 1000.0 and [u.id for u in g.created] == [user.id]
    assert g.sessions.resolve(out.token).user_id == user.id
    assert g.ep.calls[0][0] == "code" and g.ep.calls[0][2].endswith("/auth/google/callback")
    events = [e.event for e in g.stores.audit.recent()]
    assert "google_login" in events


def test_display_name_falls_back_to_email_local_part(g):
    fid, state = g.run(name=None)
    g.g.finish(fid, state, "c", "ip", "ua", None)
    assert g.stores.users.by_identity("google", "sub-1").display_name == "ann"


def test_existing_password_email_is_not_merged(g):
    g.stores.users.add(User("u1", "ann@example.org", "Ann", "user", "active", 1.0, None, None),
                       Identity("password", "u1", "u1", "x"))
    fid, state = g.run()
    out = g.g.finish(fid, state, "c", "ip", "ua", None)
    assert out.token is None and out.message == EXISTS and out.next_path == "/login"
    assert g.stores.users.by_identity("google", "sub-1") is None


def test_flow_is_single_use(g):
    fid, state = g.run()
    assert g.g.finish(fid, state, "c", "ip", "ua", None).token
    again = g.g.finish(fid, state, "c", "ip", "ua", None)
    assert again.token is None and again.message == GENERIC and again.next_path == "/login"


@pytest.mark.parametrize("mutation", ["state", "nonce", "aud", "iss", "expired", "unverified"])
def test_wrong_state_nonce_aud_iss_expired_or_unverified_email_fail(g, mutation):
    over = {"nonce": {"nonce": "other"}, "aud": {"aud": "else"}, "iss": {"iss": "https://evil.example"},
            "expired": {"exp": 1.0}, "unverified": {"email_verified": False}}.get(mutation, {})
    fid, state = g.run(**over)
    if mutation == "state":
        state = "wrong"
    out = g.g.finish(fid, state, "c", "ip", "ua", None)
    assert out.token is None and out.message == GENERIC and out.next_path == "/login"
    assert g.stores.users.by_identity("google", "sub-1") is None
    assert any(e.event == "google_login" and e.outcome == "fail" for e in g.stores.audit.recent())


def test_expired_flow_fails(g):
    fid, state = g.run()
    g.t[0] += 601
    assert g.g.finish(fid, state, "c", "ip", "ua", None).message == GENERIC


def test_endpoint_failure_is_generic_and_audit_has_no_code(g):
    fid, state = g.run()
    g.ep.fail = True
    out = g.g.finish(fid, state, "SECRETCODE", "ip", "ua", None)
    assert out.message == GENERIC and out.token is None
    assert "SECRETCODE" not in repr(g.stores.audit.recent())


def test_malformed_claims_fail_generic(g):
    fid, state = g.run()
    g.ep.claims = {"iss": "accounts.google.com"}  # no aud/sub etc
    assert g.g.finish(fid, state, "c", "ip", "ua", None).message == GENERIC


def test_sub_not_email_identifies_the_account(g):
    fid, state = g.run()
    first = g.g.finish(fid, state, "c", "ip", "ua", None)
    uid = g.sessions.resolve(first.token).user_id
    fid, state = g.run(email="changed@example.org")
    second = g.g.finish(fid, state, "c", "ip", "ua", None)
    assert g.sessions.resolve(second.token).user_id == uid
    assert len(g.stores.users.all()) == 1


def test_locked_user_cannot_sign_in(g):
    fid, state = g.run()
    first = g.g.finish(fid, state, "c", "ip", "ua", None)
    import dataclasses
    user = g.stores.users.get(g.sessions.resolve(first.token).user_id)
    g.stores.users.update(dataclasses.replace(user, status="locked"))
    fid, state = g.run()
    out = g.g.finish(fid, state, "c", "ip", "ua", None)
    assert out.token is None and out.message == GENERIC


def test_registration_closed_blocks_google_sign_up(g):
    g.policy.set(open=False)
    fid, state = g.run()
    out = g.g.finish(fid, state, "c", "ip", "ua", None)
    assert out.token is None and out.message == "Registration is closed."
    assert g.stores.users.by_identity("google", "sub-1") is None


def test_cap_is_shared_with_password_sign_up(g):
    g.policy.set(max_users=1)
    g.stores.users.add(User("u1", "x@example.org", "x", "user", "active", 1.0, None, None),
                       Identity("password", "u1", "u1", "h"))
    fid, state = g.run()
    out = g.g.finish(fid, state, "c", "ip", "ua", None)
    assert out.token is None and out.message == "Registration is closed."
    assert g.stores.users.count() == 1


def test_admin_email_claim_makes_admin_once(g):
    g.stores.settings.set("admin_email_claim", "ann@example.org")
    fid, state = g.run()
    g.g.finish(fid, state, "c", "ip", "ua", None)
    assert g.stores.users.by_email("ann@example.org").role == "admin"
    assert not g.stores.settings.get("admin_email_claim")


def logged_in(g, email="me@example.org"):
    u = User("me", email, "Me", "user", "active", 1.0, None, None)
    g.stores.users.add(u, Identity("password", "me", "me", "h"))
    token, rec = g.sessions.start("me", "ip", "ua")
    return token, Principal("me", email, "user", rec.token_hash, rec.csrf_token, 0.0)


def test_link_and_reauth_need_the_logged_in_user(g):
    with pytest.raises(AuthError):
        g.g.start("link", "/s", None, "ip")
    token, p = logged_in(g)
    fid, state = g.run("link", p)
    out = g.g.finish(fid, state, "c", "ip", "ua", p)
    assert out.token is None and out.message is None and out.next_path == "/next"
    assert g.stores.users.by_identity("google", "sub-1").id == "me"
    # reauth with same sub
    fid, state = g.run("reauth", p)
    out = g.g.finish(fid, state, "c", "ip", "ua", p)
    assert out.message is None and out.token is None
    assert g.sessions.resolve(token).reauth_until == 1300.0


def test_link_without_current_or_other_user_fails(g):
    token, p = logged_in(g)
    fid, state = g.run("link", p)
    assert g.g.finish(fid, state, "c", "ip", "ua", None).message == GENERIC
    other = User("o", "o@example.org", "o", "user", "active", 1.0, None, None)
    g.stores.users.add(other, Identity("google", "sub-1", "o"))
    fid, state = g.run("link", p)
    out = g.g.finish(fid, state, "c", "ip", "ua", p)
    assert out.message == "This Google account is already connected to another account."
    assert out.code == "linked_elsewhere"


def test_link_rejects_current_user_mismatch(g):
    _, p = logged_in(g)
    fid, state = g.run("link", p)
    import dataclasses
    assert g.g.finish(fid, state, "c", "ip", "ua", dataclasses.replace(p, user_id="zzz")).message == GENERIC


def test_reauth_with_different_sub_fails(g):
    token, p = logged_in(g)
    g.stores.users.add_identity(Identity("google", "sub-other", "me"))
    fid, state = g.run("reauth", p)
    out = g.g.finish(fid, state, "c", "ip", "ua", p)
    assert out.message == GENERIC
    assert g.sessions.resolve(token).reauth_until == 0.0


def test_id_token_claims_parsing():
    assert id_token_claims(id_token({"a": 1})) == {"a": 1}
    for bad in ("a.b", "a.!!!.c", f"a.{b64([1])}.c", "", "a.b.c.d"):
        with pytest.raises(GoogleError):
            id_token_claims(bad)


def test_validate_claims_audience_list():
    base = {"iss": "accounts.google.com", "aud": [CID, "x"], "azp": CID, "exp": 100, "nonce": "n",
            "email_verified": True}
    validate_claims(base, CID, "n", 150)
    with pytest.raises(GoogleError):
        validate_claims({**base, "azp": "x"}, CID, "n", 150)
    with pytest.raises(GoogleError):
        validate_claims(base, CID, "n", 161)


def test_http_endpoint_posts_form(monkeypatch):
    seen = {}

    class Resp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"id_token": "x"}'

    def fake_urlopen(req, timeout=None, context=None):
        seen.update(url=req.full_url, data=req.data, ct=req.get_header("Content-type"), timeout=timeout,
                    context=context)
        return Resp()

    monkeypatch.setattr("oracle_lab.auth.google.urllib.request.urlopen", fake_urlopen)
    ep = HttpTokenEndpoint(CID, Secret.from_value("shh", "t"))
    assert ep.exchange("c", "v", "https://r") == {"id_token": "x"}
    form = parse_qs(seen["data"].decode())
    assert form["grant_type"] == ["authorization_code"] and form["client_secret"] == ["shh"]
    assert form["code_verifier"] == ["v"] and seen["timeout"] == 10
    assert seen["ct"] == "application/x-www-form-urlencoded" and seen["context"] is not None


def test_http_endpoint_errors(monkeypatch):
    import urllib.error

    def boom(req, timeout=None, context=None):
        raise urllib.error.HTTPError(req.full_url, 400, "bad", {}, None)

    monkeypatch.setattr("oracle_lab.auth.google.urllib.request.urlopen", boom)
    with pytest.raises(GoogleError) as e:
        HttpTokenEndpoint(CID, Secret.from_value("shh", "t")).exchange("c", "v", "r")
    assert "shh" not in str(e.value)


def test_admin_claim_bypasses_closed_registration_and_cap(g):
    g.policy.set(open=False, max_users=0)
    g.stores.settings.set("admin_email_claim", "ann@example.org")
    fid, state = g.run()
    assert g.g.finish(fid, state, "c", "ip", "ua", None).token
    assert g.stores.users.by_email("ann@example.org").role == "admin"
    assert not g.stores.settings.get("admin_email_claim")


def test_admin_claim_kept_when_email_taken(g):
    g.stores.users.add(User("u1", "ann@example.org", "Ann", "user", "active", 1.0, None, None),
                       Identity("password", "u1", "u1", "x"))
    g.stores.settings.set("admin_email_claim", "ann@example.org")
    fid, state = g.run()
    assert g.g.finish(fid, state, "c", "ip", "ua", None).message == EXISTS
    assert g.stores.users.get("u1").role == "user"
    assert g.stores.settings.get("admin_email_claim") == "ann@example.org"


@pytest.mark.parametrize("exc", [
    __import__("http.client").client.IncompleteRead(b"x"),
    __import__("urllib.error").error.URLError("down"),
    TimeoutError(),
])
def test_http_transport_errors_map_to_google_error(monkeypatch, exc):
    def boom(req, timeout=None, context=None):
        raise exc

    monkeypatch.setattr("oracle_lab.auth.google.urllib.request.urlopen", boom)
    with pytest.raises(GoogleError):
        HttpTokenEndpoint(CID, Secret.from_value("shh", "t")).exchange("c", "v", "r")


@pytest.mark.parametrize("status,body", [(200, b"not json"), (200, b"[1]"), (204, b"{}")])
def test_http_bad_responses_map_to_google_error(monkeypatch, status, body):
    class Resp:
        def __init__(self):
            self.status = status

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return body

    monkeypatch.setattr("oracle_lab.auth.google.urllib.request.urlopen", lambda *a, **k: Resp())
    with pytest.raises(GoogleError):
        HttpTokenEndpoint(CID, Secret.from_value("shh", "t")).exchange("c", "v", "r")


def test_endpoint_http_exception_does_not_raise_from_finish(g):
    import http.client
    fid, state = g.run()
    g.ep.exchange = lambda *a: (_ for _ in ()).throw(http.client.IncompleteRead(b""))
    assert g.g.finish(fid, state, "c", "ip", "ua", None).message == GENERIC


def test_link_refused_when_already_connected(g):
    _, p = logged_in(g)
    g.stores.users.add_identity(Identity("google", "sub-old", "me"))
    fid, state = g.run("link", p)
    out = g.g.finish(fid, state, "c", "ip", "ua", p)
    assert out.message == "This account is already connected to a Google account."
    assert g.stores.users.by_identity("google", "sub-1") is None
    assert any(e.detail.get("reason") == "already_linked" for e in g.stores.audit.recent())


@pytest.mark.parametrize("given,kept", [("/a/b?c=1", "/a/b?c=1"), ("//evil.example", "/"), ("/\\evil", "/"),
                                        ("https://evil.example", "/"), ("", "/"), ("/a\nb", "/"),
                                        ("/a\x00", "/")])
def test_start_normalises_next_path(g, given, kept):
    _, fid = g.g.start("login", given, None, "1.1.1.1")
    assert g.stores.flows.take(fid).next_path == kept


def test_overlong_email_fails(g):
    fid, state = g.run(email="a" * 250 + "@x.org")
    out = g.g.finish(fid, state, "c", "ip", "ua", None)
    assert out.message == GENERIC
    assert any(e.detail.get("reason") == "claims_email" for e in g.stores.audit.recent())


def test_azp_must_match_even_with_string_aud():
    claims = {"iss": "accounts.google.com", "aud": CID, "azp": "other", "exp": 100, "nonce": "n",
              "email_verified": True}
    with pytest.raises(GoogleError):
        validate_claims(claims, CID, "n", 100)


def test_link_session_mismatch_does_not_exchange_code(g):
    _, p = logged_in(g)
    fid, state = g.run("link", p)
    assert g.g.finish(fid, state, "c", "ip", "ua", None).message == GENERIC
    assert g.ep.calls == []


def test_raising_hook_still_counts_and_audits_password_registration():
    t = [1000.0]
    clock = lambda: t[0]  # noqa: E731
    stores = memory_stores()
    throttle = Throttle(stores.throttle, clock)
    audit = AuditLog(stores.audit, clock)

    def hook(user):
        raise RuntimeError("provisioning down")

    reg = Registration(stores, PasswordPolicy(frozenset()), RegistrationPolicy(stores.settings, stores.users, True, 9),
                       SessionManager(stores.sessions, clock), throttle, audit, clock, hook)
    with pytest.raises(RuntimeError):
        reg.with_password("me@example.org", "a fine long passphrase", "1.1.1.1", "ua")
    assert stores.throttle.count_since("register:ip:1.1.1.1", 0) == 1
    assert any(e.event == "register" and e.outcome == "ok" for e in stores.audit.recent())


def test_outcomes_carry_a_reason_code(g):
    fid, state = g.run()
    assert g.g.finish(fid, state, "c", "ip", "ua", None).code is None  # success
    fid, state = g.run()
    assert g.g.finish(fid, "wrong", "c", "ip", "ua", None).code == "failed"
    g.stores.users.add(User("u2", "bob@example.org", "Bob", "user", "active", 1.0, None, None),
                       Identity("password", "u2", "u2", "x"))
    fid, state = g.run(sub="sub-2", email="bob@example.org")
    assert g.g.finish(fid, state, "c", "ip", "ua", None).code == "exists"
    g.policy.set(open=False)
    fid, state = g.run(sub="sub-3", email="carl@example.org")
    assert g.g.finish(fid, state, "c", "ip", "ua", None).code == "closed"


def test_link_and_reauth_failures_carry_codes(g):
    _, p = logged_in(g)
    g.stores.users.add_identity(Identity("google", "sub-old", "me"))
    fid, state = g.run("link", p)
    assert g.g.finish(fid, state, "c", "ip", "ua", p).code == "already_linked"
    fid, state = g.run("reauth", p)
    assert g.g.finish(fid, state, "c", "ip", "ua", p).code == "failed"


def test_google_sign_ups_count_toward_the_per_ip_registration_limit(g):
    fid, state = g.run()
    assert g.g.finish(fid, state, "c", "ip", "ua", None).token  # one sign-up from "ip"
    assert g.stores.throttle.count_since("register:ip:ip", 0) == 1
    for _ in range(2):
        g.stores.throttle.record("register:ip:ip", g.t[0])
    fid, state = g.run(sub="sub-2", email="bob@example.org")
    out = g.g.finish(fid, state, "c", "ip", "ua", None)
    assert out.token is None and out.code == "throttled" and g.stores.users.by_email("bob@example.org") is None
    fid, state = g.run()  # signing in to the existing account is not a sign-up
    assert g.g.finish(fid, state, "c", "ip", "ua", None).token
