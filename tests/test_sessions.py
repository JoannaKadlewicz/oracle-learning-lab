from __future__ import annotations

from oracle_lab.accounts.memory import memory_stores
from oracle_lab.auth.sessions import DAY, SessionManager
from oracle_lab.auth.tokens import token_hash
from oracle_lab.web.cookies import CookiePolicy
from oracle_lab.web.http import Request


def test_session_expires_idle_and_absolute():
    t = [1000.0]
    m = SessionManager(memory_stores().sessions, lambda: t[0])
    token, _ = m.start("u1", "1.2.3.4", "ua")
    t[0] += 6 * DAY
    assert m.resolve(token)
    t[0] += 6 * DAY
    assert m.resolve(token)
    t[0] = 1000 + 30 * DAY + 1
    assert m.resolve(token) is None


def test_idle_expiry_deletes_the_record():
    t = [0.0]
    stores = memory_stores()
    m = SessionManager(stores.sessions, lambda: t[0])
    token, rec = m.start("u1", "", "")
    t[0] = 7 * DAY
    assert m.resolve(token) is None
    assert stores.sessions.get(rec.token_hash) is None


def test_unknown_token_resolves_to_none():
    assert SessionManager(memory_stores().sessions, lambda: 0).resolve("nope") is None


def test_touch_only_when_older_than_a_minute():
    t = [100.0]
    m = SessionManager(memory_stores().sessions, lambda: t[0])
    token, _ = m.start("u1", "", "")
    t[0] = 130.0
    assert m.resolve(token).last_seen_at == 100.0
    t[0] = 161.0
    assert m.resolve(token).last_seen_at == 161.0


def test_only_the_hash_is_stored():
    stores = memory_stores()
    m = SessionManager(stores.sessions, lambda: 0)
    token, rec = m.start("u1", "", "")
    assert rec.token_hash == token_hash(token) and stores.sessions.get(token) is None
    assert rec.csrf_token and rec.csrf_token != token


def test_user_agent_is_truncated():
    _, rec = SessionManager(memory_stores().sessions, lambda: 0).start("u1", "", "x" * 500)
    assert len(rec.user_agent) == 200


def test_end_and_mark_reauth():
    t = [10.0]
    stores = memory_stores()
    m = SessionManager(stores.sessions, lambda: t[0])
    token, _ = m.start("u1", "", "")
    m.mark_reauth(token)
    assert m.resolve(token).reauth_until == 310.0
    m.end(token)
    assert m.resolve(token) is None


def test_end_all_keeps_the_current_one():
    m = SessionManager(memory_stores().sessions, lambda: 0)
    a, _ = m.start("u1", "", "")
    b, _ = m.start("u1", "", "")
    other, _ = m.start("u2", "", "")
    m.end_all("u1", keep_token=a)
    assert m.resolve(a) and m.resolve(b) is None and m.resolve(other)
    m.end_all("u1")
    assert m.resolve(a) is None


def test_cookie_attributes():
    c = CookiePolicy(secure=True).set_session("abc", 3600)
    assert c.startswith("__Host-oll_session=abc;")
    assert all(p in c for p in ("HttpOnly", "Secure", "SameSite=Lax", "Path=/", "Max-Age=3600"))
    plain = CookiePolicy(secure=False)
    assert "Secure" not in plain.set_session("abc", 1)
    assert plain.session_name == "oll_session" and plain.flow_name == "oll_flow"
    assert CookiePolicy(secure=True).flow_name == "__Host-oll_flow"


def test_flow_and_clear_cookies():
    p = CookiePolicy(secure=True)
    assert "Max-Age=600" in p.set_flow("f1")
    assert p.clear_session().startswith("__Host-oll_session=;") and "Max-Age=0" in p.clear_session()
    assert p.clear_flow().startswith("__Host-oll_flow=;") and "Max-Age=0" in p.clear_flow()


def _req(cookie: str) -> Request:
    return Request("GET", "/", {"cookie": cookie})


def test_read_cookie():
    p = CookiePolicy(secure=False)
    assert p.read(_req("a=1; oll_session=tok-_9"), "oll_session") == "tok-_9"
    assert p.read(_req("a=1"), "oll_session") is None
    assert p.read(Request("GET", "/", {}), "oll_session") is None
    assert p.read(_req(";;==\x00"), "oll_session") is None
    assert p.read(_req('oll_session="a.b"'), "oll_session") is None
