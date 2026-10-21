"""Shared fixtures. Tests that need Oracle take the `database` fixture and are skipped without one.

The database comes from the same STUDY_* settings as the app (see oracle_lab.config). The tests of
the Oracle state store take `state_database`, a user of its own that they empty: STUDY_TEST_STATE_USER
and STUDY_TEST_STATE_PASSWORD[_FILE], on STUDY_TEST_STATE_DSN (default: STUDY_DSN). Never point it at
the user that keeps your progress.

The practice-schema tests take `provisioner_database`: STUDY_TEST_PROVISIONER_USER and
STUDY_TEST_PROVISIONER_PASSWORD[_FILE] (may create and drop users), and STUDY_TEST_GATEWAY_USER and
STUDY_TEST_GATEWAY_PASSWORD[_FILE] (CREATE SESSION only), on STUDY_DSN. They only ever drop the
OLL_U* users they created.
"""

import http.client
import json
import os
import threading
import urllib.error
import urllib.request

import pytest

from oracle_lab.bootstrap import build_app
from oracle_lab.config import DatabaseTarget, PracticeTarget, Settings
from oracle_lab.credentials import resolve_secret
from oracle_lab.database.connection import OracleDatabase
from oracle_lab.web.server import create_server


@pytest.fixture(scope="session")
def database():
    db = OracleDatabase(Settings.from_env().database)
    try:
        db.connect().close()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"database not reachable: {exc}")
    return db


@pytest.fixture(scope="session")
def state_database():
    user, password = os.environ.get("STUDY_TEST_STATE_USER"), resolve_secret("STUDY_TEST_STATE_PASSWORD")
    if not user or password is None:
        pytest.skip("STUDY_TEST_STATE_USER / STUDY_TEST_STATE_PASSWORD not set")
    dsn = os.environ.get("STUDY_TEST_STATE_DSN") or Settings.from_env().database.dsn
    db = OracleDatabase(DatabaseTarget(user, dsn, password))
    try:
        db.connect().close()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"state database not reachable: {exc}")
    return db


@pytest.fixture(scope="session")
def provisioner_database():
    """A PracticeTarget for the test provisioner and gateway users (tablespace USERS, 50 MB quota)."""
    users = {}
    for role in ("PROVISIONER", "GATEWAY"):
        user, password = os.environ.get(f"STUDY_TEST_{role}_USER"), resolve_secret(f"STUDY_TEST_{role}_PASSWORD")
        if not user or password is None:
            pytest.skip(f"STUDY_TEST_{role}_USER / STUDY_TEST_{role}_PASSWORD not set")
        users[role] = DatabaseTarget(user, Settings.from_env().database.dsn, password)
    try:
        OracleDatabase(users["PROVISIONER"]).connect().close()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"provisioner database not reachable: {exc}")
    return PracticeTarget(provisioner=users["PROVISIONER"], gateway=users["GATEWAY"], tablespace="USERS", quota_mb=50)


# --- the web app over a real socket (test_web.py, test_auth_web.py) ---

NOW = 1_800_000_000
PASSWORD = "a fine long passphrase"


def settings_for(tmp_path, **env):
    return Settings.from_env({"STUDY_DATA_DIR": str(tmp_path), "STUDY_PASSWORD": "unused", **env})


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


_opener = urllib.request.build_opener(_NoRedirect)


def session_cookie(headers) -> str:
    """The `name=value` of the session cookie a response sets."""
    for value in headers.get_all("Set-Cookie") or []:
        pair = value.split(";", 1)[0]
        if pair.split("=", 1)[0].endswith("oll_session"):
            return pair
    raise AssertionError("no session cookie in the response")


class Client:
    """request(path, data=None, headers=None) -> (status, headers, body); redirects are not followed.
    `headers` set on the client (by sign_in) go with every request."""

    def __init__(self, port: int):
        self.port = port
        self.base = f"http://127.0.0.1:{port}"
        self.origin = self.base
        self.headers: dict[str, str] = {}

    def __call__(self, path, data=None, headers=None):
        body = json.dumps(data).encode() if isinstance(data, dict) else data
        req = urllib.request.Request(self.base + path, data=body, headers={**self.headers, **(headers or {})})
        try:
            resp = _opener.open(req)
        except urllib.error.HTTPError as exc:  # also a 302, without the redirect handler
            resp = exc
        with resp:
            return resp.status, resp.headers, resp.read()

    def raw(self, method, target, headers=None):
        """Sends `target` verbatim (no client-side normalisation); returns (status, headers, body)."""
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request(method, target, headers={**self.headers, **(headers or {})})
            resp = conn.getresponse()
            return resp.status, resp.headers, resp.read()
        finally:
            conn.close()

    def sign_in(self, email="learner@example.org", password=PASSWORD):
        """Registers an account and keeps its cookie, CSRF token and Origin for the next requests."""
        status, headers, body = self("/api/auth/register", {"email": email, "password": password},
                                     headers={"Origin": self.origin})
        assert status == 200, body
        cookie = session_cookie(headers)
        me = json.loads(self("/api/auth/me", headers={"Cookie": cookie})[2])
        self.headers = {"Cookie": cookie, "X-CSRF-Token": me["csrf_token"], "Origin": self.origin}
        return self


@pytest.fixture
def serve(tmp_path):
    """serve(settings=None, **build_app_kwargs) starts the app on a free port and returns a Client.
    Progress and notes belong to the signed-in user: pass stores=memory_stores() to look at them."""
    servers = []

    def start(settings=None, **kwargs):
        kwargs.setdefault("maintenance", False)  # no purge thread outliving the test
        app = build_app(settings or settings_for(tmp_path), clock=lambda: NOW, **kwargs)
        httpd = create_server(app, "127.0.0.1", 0)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        servers.append(httpd)
        return Client(httpd.server_port)

    yield start
    for httpd in servers:
        httpd.shutdown()
        httpd.server_close()
