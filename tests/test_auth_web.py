"""Login required everywhere, CSRF, and the auth and account endpoints, over a real socket."""

import base64
import dataclasses
import json
from urllib.parse import parse_qs, urlsplit

import pytest

from conftest import NOW, PASSWORD, session_cookie, settings_for
from oracle_lab import cli
from oracle_lab.accounts.memory import memory_stores
from oracle_lab.accounts.oracle_store import OracleUserNotes, OracleUsers, OracleUserStates
from oracle_lab.auth.models import Identity, LoginRequired, Principal, Throttled, WeakPassword
from oracle_lab.bootstrap import build_app, build_app_stores
from oracle_lab.web.http import HttpError, Request, Response
from oracle_lab.web.middleware import csrf, error_boundary, safe_next

GOOGLE_ENV = {"STUDY_GOOGLE_CLIENT_ID": "client-1", "STUDY_GOOGLE_CLIENT_SECRET": "shh"}


def register(http, email="a@example.org", password=PASSWORD, **extra):
    return http("/api/auth/register", {"email": email, "password": password, **extra}, headers={"Origin": http.origin})


def csrf_of(http, cookie):
    return json.loads(http("/api/auth/me", headers={"Cookie": cookie})[2])["csrf_token"]


def test_logged_out_html_redirects_to_login_with_next(serve):
    status, headers, _ = serve()("/progress?tab=2")
    assert status == 302 and headers["Location"] == "/login?next=%2Fprogress%3Ftab%3D2"


def test_logged_out_api_is_401_and_public_paths_are_open(serve):
    http = serve()
    status, _, body = http("/api/progress")
    assert status == 401 and json.loads(body) == {"error": "Login required"}
    assert http("/healthz")[0] == 200 and http("/login")[0] == 200 and http("/css/app.css")[0] == 200
    assert http("/register")[0] == 200 and http("/reset")[0] == 200
    assert http("/js/main.js")[0] == 401  # not a public prefix
    assert http("/admin")[0] == 302


def test_auth_pages_have_their_forms(serve):
    http = serve()
    for path, form in (("/login", "login-form"), ("/register", "register-form"), ("/reset", "reset-form")):
        status, headers, body = http(path)
        assert status == 200 and headers["Content-Type"].startswith("text/html") and f'id="{form}"'.encode() in body


def test_register_login_me_logout(serve):
    http = serve(stores=memory_stores())
    status, headers, body = register(http)
    assert status == 200 and json.loads(body) == {"ok": True, "next": "/"}
    assert "HttpOnly" in headers["Set-Cookie"] and f"Max-Age={30 * 86400}" in headers["Set-Cookie"]
    cookie = session_cookie(headers)
    me = json.loads(http("/api/auth/me", headers={"Cookie": cookie})[2])
    assert me["user"]["email"] == "a@example.org" and me["csrf_token"]
    status, headers, _ = http("/api/auth/logout", {}, headers={"Cookie": cookie, "X-CSRF-Token": me["csrf_token"],
                                                               "Origin": http.origin})
    assert status == 200 and "Max-Age=0" in headers["Set-Cookie"]
    assert http("/api/auth/me", headers={"Cookie": cookie})[0] == 401

    status, headers, body = http("/api/auth/login", {"email": "A@example.org", "password": PASSWORD, "next": "/quiz"},
                                 headers={"Origin": http.origin})
    assert status == 200 and json.loads(body)["next"] == "/quiz"
    assert http("/api/auth/me", headers={"Cookie": session_cookie(headers)})[0] == 200


def test_signed_in_html_routes_get_the_app_shell(serve):
    http = serve().sign_in()
    assert http("/")[0] == 200 and http("/js/main.js")[0] == 200
    status, _, body = http("/admin")
    assert status == 200 and b"<html" in body.lower()


def test_login_ends_the_session_of_the_cookie_it_replaces(serve):
    http = serve(stores=memory_stores())
    old = session_cookie(register(http)[1])
    status, headers, _ = http("/api/auth/login", {"email": "a@example.org", "password": PASSWORD},
                              headers={"Cookie": old, "X-CSRF-Token": csrf_of(http, old), "Origin": http.origin})
    assert status == 200
    assert http("/api/auth/me", headers={"Cookie": old})[0] == 401
    assert http("/api/auth/me", headers={"Cookie": session_cookie(headers)})[0] == 200


def test_bad_login_and_weak_password_errors(serve):
    http = serve(stores=memory_stores())
    status, _, body = register(http, password="short")
    assert status == 400 and json.loads(body)["problems"] == ["Use at least 12 characters."]
    register(http)
    status, _, body = http("/api/auth/login", {"email": "a@example.org", "password": "wrong password!"},
                           headers={"Origin": http.origin})
    assert status == 401 and json.loads(body) == {"error": "Email or password is incorrect."}


def test_post_without_csrf_token_is_403(serve):
    http = serve()
    cookie = session_cookie(register(http)[1])
    for token in (None, "not-the-token"):
        headers = {"Cookie": cookie, "Origin": http.origin, **({"X-CSRF-Token": token} if token else {})}
        status, _, body = http("/api/reset-progress", {}, headers=headers)
        assert status == 403 and json.loads(body) == {"error": "Invalid CSRF token"}


def test_next_parameter_cannot_leave_the_site():
    assert safe_next("//evil.com") == "/" and safe_next("/\\evil") == "/"
    assert safe_next("https://evil.com") == "/" and safe_next("/a\r\nSet-Cookie: x=1") == "/"
    assert safe_next("/quiz?tab=2") == "/quiz?tab=2"


def test_redirect_next_is_encoded(serve):
    status, headers, _ = serve()("/x%0d%0aSet-Cookie:%20a=b")
    assert status == 302 and "\r" not in headers["Location"] and headers["Location"].startswith("/login?next=%2F")


def test_login_page_redirects_home_when_logged_in(serve):
    http = serve().sign_in()
    for path in ("/login", "/register"):
        status, headers, _ = http(path)
        assert status == 302 and headers["Location"] == "/"


def test_locked_user_is_logged_out(serve):
    stores = memory_stores()
    http = serve(stores=stores).sign_in()
    user = stores.users.by_email("learner@example.org")
    stores.users.update(dataclasses.replace(user, status="locked"))
    assert http("/api/auth/me")[0] == 401
    assert stores.sessions.for_user(user.id) == []


def test_throttled_login_returns_429_with_retry_after(serve):
    http = serve(stores=memory_stores())
    register(http)
    attempt = {"email": "a@example.org", "password": "wrong password!"}
    for _ in range(5):
        assert http("/api/auth/login", attempt, headers={"Origin": http.origin})[0] == 401
    status, headers, body = http("/api/auth/login", attempt, headers={"Origin": http.origin})
    assert status == 429 and headers["Retry-After"] == "1" and "Too many attempts" in json.loads(body)["error"]


def test_auth_config(serve, tmp_path):
    assert json.loads(serve()("/api/auth/config")[2]) == {"google": False, "registration_open": True}
    closed = serve(settings_for(tmp_path, STUDY_REGISTRATION="closed", **GOOGLE_ENV), stores=memory_stores())
    assert json.loads(closed("/api/auth/config")[2]) == {"google": True, "registration_open": False}
    assert register(closed)[0] == 403


def test_account_password_change_rotates_the_session(serve):
    stores = memory_stores()
    http = serve(stores=stores).sign_in()
    old_cookie = http.headers["Cookie"]
    status, _, body = http("/api/account/password", {"current": "wrong password!", "new": "another long passphrase"})
    assert status == 401
    status, headers, _ = http("/api/account/password", {"current": PASSWORD, "new": "another long passphrase"})
    assert status == 200
    assert http("/api/auth/me", headers={"Cookie": old_cookie})[0] == 401
    assert http("/api/auth/me", headers={"Cookie": session_cookie(headers)})[0] == 200
    failures = [e for e in stores.audit.recent() if e.event == "password_changed" and e.outcome == "fail"]
    assert failures and failures[0].ip == "127.0.0.1"


def test_account_sessions_and_unlink(serve):
    stores = memory_stores()
    http = serve(stores=stores).sign_in()
    login = {"email": "learner@example.org", "password": PASSWORD}
    other = session_cookie(http("/api/auth/login", login, headers={"Cookie": ""})[1])  # a second device
    sessions = json.loads(http("/api/account/sessions")[2])["sessions"]
    assert len(sessions) == 2 and sum(s["current"] for s in sessions) == 1
    other_id = next(s["id"] for s in sessions if not s["current"])
    assert http("/api/account/sessions/end", {"id": other_id})[0] == 200
    assert http("/api/auth/me", headers={"Cookie": other})[0] == 401
    assert http("/api/account/sessions/end-others", {})[0] == 200

    user = stores.users.by_email("learner@example.org")
    stores.users.add_identity(Identity("google", "sub-1", user.id))
    assert http("/api/account/google/unlink", {})[0] == 200
    assert [i.provider for i in stores.users.identities(user.id)] == ["password"]
    assert http("/api/account/set-password", {"new": "another long passphrase"})[0] == 400  # already has one
    assert http("/api/account/delete", {"password": PASSWORD})[0] == 501


def test_unlink_is_refused_without_a_password(serve, tmp_path):
    stores = memory_stores()
    endpoint = FakeGoogle()
    http = serve(settings_for(tmp_path, **GOOGLE_ENV), stores=stores, google_endpoint=endpoint)
    cookie = google_sign_in(http, endpoint)
    status, _, body = http("/api/account/google/unlink", {},
                           headers={"Cookie": cookie, "X-CSRF-Token": csrf_of(http, cookie), "Origin": http.origin})
    assert status == 400 and "password" in json.loads(body)["error"]


def test_password_reset_with_a_bad_token(serve):
    status, _, body = serve()("/api/auth/reset", {"token": "nope", "password": "another long passphrase"})
    assert status == 400 and "invalid" in json.loads(body)["error"]


def test_google_endpoints_404_without_configuration(serve):
    http = serve()
    assert http("/auth/google/start")[0] == 404
    assert http("/auth/google/callback?state=x&code=y")[0] == 404


class FakeGoogle:
    """The token endpoint: answers with an ID token for the nonce of the last start."""

    def __init__(self, sub="google-sub-1", email="g@example.org"):
        self.sub, self.email, self.nonce = sub, email, ""

    def exchange(self, code, code_verifier, redirect_uri):
        claims = {"iss": "https://accounts.google.com", "aud": "client-1", "exp": NOW + 3600, "nonce": self.nonce,
                  "email_verified": True, "sub": self.sub, "email": self.email}
        payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
        return {"id_token": f"e30.{payload}.sig"}


def google_sign_in(http, endpoint, next_path="/quiz"):
    status, headers, _ = http(f"/auth/google/start?intent=login&next={next_path}")
    assert status == 302 and headers["Location"].startswith("https://accounts.google.com/")
    query = parse_qs(urlsplit(headers["Location"]).query)
    endpoint.nonce = query["nonce"][0]
    flow = next(v.split(";", 1)[0] for v in headers.get_all("Set-Cookie") if "oll_flow=" in v)
    status, headers, _ = http(f"/auth/google/callback?state={query['state'][0]}&code=c", headers={"Cookie": flow})
    assert status == 302 and headers["Location"] == next_path
    assert any("oll_flow=;" in v for v in headers.get_all("Set-Cookie"))
    return session_cookie(headers)


def test_google_round_trip_with_fake_endpoint(serve, tmp_path):
    endpoint = FakeGoogle()
    http = serve(settings_for(tmp_path, **GOOGLE_ENV), stores=memory_stores(), google_endpoint=endpoint)
    cookie = google_sign_in(http, endpoint)
    assert json.loads(http("/api/auth/me", headers={"Cookie": cookie})[2])["user"]["email"] == "g@example.org"


def test_google_callback_failure_goes_back_to_login(serve, tmp_path):
    http = serve(settings_for(tmp_path, **GOOGLE_ENV), stores=memory_stores(), google_endpoint=FakeGoogle())
    status, headers, _ = http("/auth/google/callback?state=x&code=y")
    assert status == 302 and headers["Location"] == "/login?error=google"
    assert http("/auth/google/start?intent=link")[0] == 401
    assert http("/auth/google/start?intent=teleport")[0] == 400


@pytest.mark.parametrize("path", ["/api/account/sessions", "/api/auth/me"])
def test_private_auth_endpoints_need_a_login(serve, path):
    assert serve()(path)[0] == 401


def test_oracle_mode_keeps_accounts_progress_and_notes_in_oracle(tmp_path):
    settings = settings_for(tmp_path, STUDY_STATE_USER="appdata", STUDY_STATE_PASSWORD="pw")
    stores = build_app_stores(settings)  # the pool connects on first use: no database needed here
    assert isinstance(stores.users, OracleUsers) and isinstance(stores.states, OracleUserStates)
    assert isinstance(stores.notes, OracleUserNotes)
    assert build_app(settings) is not None
    assert not (tmp_path / "app.db").exists() and not (tmp_path / "progress.json").exists()


def test_accounts_default_to_sqlite_in_the_data_dir(serve, tmp_path):
    serve().sign_in()
    assert (tmp_path / "app.db").is_file()


def test_serve_warns_about_the_old_basic_auth_password(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr("oracle_lab.web.server.serve", lambda *args: None)
    monkeypatch.setattr("oracle_lab.bootstrap.build_app", lambda settings: None)
    cli._serve(settings_for(tmp_path, STUDY_AUTH_PASSWORD="old"), None)
    assert "STUDY_AUTH_PASSWORD is set but ignored: the app now has its own login." in caplog.text


@pytest.mark.parametrize("target", [
    "/css/../js/main.js", "/js/auth/../main.js", "/js/core/dom.js/../../main.js", "/css/../index.html",
    "/css/%2e%2e/js/main.js", "/css/..%2fjs/main.js", "/css/%2E%2E%5Cjs/main.js", "/css/./app.css", "/css//app.css",
    "/css\\..\\js/main.js", "/js/core/dom.jsx", "/css/../api/progress",
])
def test_public_prefixes_cannot_be_escaped(serve, target):
    status, _, body = serve().raw("GET", target)
    assert status in (401, 404) and b"<html" not in body.lower() and b"import" not in body


def test_public_assets_stay_public(serve):
    http = serve()
    assert http.raw("GET", "/js/core/dom.js")[0] == 200 and http.raw("GET", "/css/app.css")[0] == 200


def test_csrf_is_checked_on_every_method_but_get():
    principal = Principal("u1", "a@example.org", "learner", "hash", "the-token", 0.0)
    for method in ("HEAD", "POST", "DELETE"):
        with pytest.raises(HttpError) as err:
            csrf(Request(method, "/api/state", {"x-csrf-token": "wrong"}, principal=principal), lambda _: Response())
        assert err.value.status == 403
    assert csrf(Request("GET", "/api/state", {}, principal=principal), lambda _: Response()).status == 200


def test_auth_errors_are_mapped_by_the_error_boundary():
    def raising(exc):
        return error_boundary(Request("POST", "/any", {}), lambda _: (_ for _ in ()).throw(exc))

    throttled = raising(Throttled("Too many attempts.", retry_after=7))
    assert (throttled.status, throttled.headers["Retry-After"]) == (429, "7")
    weak = raising(WeakPassword("Choose a stronger password.", ["Use at least 12 characters."]))
    assert weak.status == 400 and json.loads(weak.body) == {"error": "Choose a stronger password.",
                                                            "problems": ["Use at least 12 characters."]}
    assert json.loads(raising(LoginRequired("Login required")).body) == {"error": "Login required"}


def test_failed_google_link_returns_to_the_page_with_a_flag(serve, tmp_path):
    endpoint = FakeGoogle()
    http = serve(settings_for(tmp_path, **GOOGLE_ENV), stores=memory_stores(), google_endpoint=endpoint).sign_in()
    status, headers, _ = http("/auth/google/start?intent=link&next=/settings")
    flow = next(v.split(";", 1)[0] for v in headers.get_all("Set-Cookie") if "oll_flow=" in v)
    status, headers, _ = http("/auth/google/callback?state=wrong&code=c",
                              headers={"Cookie": http.headers["Cookie"] + "; " + flow})
    assert status == 302 and headers["Location"] == "/settings?google_error=1"
    assert any("oll_flow=;" in v for v in headers.get_all("Set-Cookie"))


def test_flow_cookie_is_cleared_when_the_callback_raises(serve, tmp_path):
    endpoint = FakeGoogle()
    endpoint.exchange = lambda *args: (_ for _ in ()).throw(Throttled("Too many attempts.", retry_after=3))
    http = serve(settings_for(tmp_path, **GOOGLE_ENV), stores=memory_stores(), google_endpoint=endpoint)
    _, headers, _ = http("/auth/google/start")
    state = parse_qs(urlsplit(headers["Location"]).query)["state"][0]
    flow = next(v.split(";", 1)[0] for v in headers.get_all("Set-Cookie") if "oll_flow=" in v)
    status, headers, _ = http(f"/auth/google/callback?state={state}&code=c", headers={"Cookie": flow})
    assert status == 429 and any("oll_flow=;" in v for v in headers.get_all("Set-Cookie") or [])
