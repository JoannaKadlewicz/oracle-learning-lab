"""Authorization matrix: every private endpoint needs a session, and one user never sees another's data."""

import json

import pytest

from conftest import Client, settings_for
from oracle_lab.accounts.memory import memory_stores
from oracle_lab.auth.models import LoginRequired, Principal
from oracle_lab.bootstrap import build_app
from oracle_lab.services.context import UserContexts
from oracle_lab.web.http import Request
from oracle_lab.web.middleware import PUBLIC_PATHS

PRIVATE = [("GET", "/api/state"), ("GET", "/api/progress"), ("GET", "/api/content"), ("GET", "/report"),
           ("POST", "/api/attempt"), ("POST", "/api/card"), ("POST", "/api/settings"), ("POST", "/api/pick"),
           ("POST", "/api/reset-progress"), ("GET", "/api/mock"), ("POST", "/api/mock/start"), ("GET", "/api/notes"),
           ("GET", "/api/note"), ("POST", "/api/notes/save"), ("POST", "/api/run"), ("POST", "/api/grade"),
           ("GET", "/api/schema"), ("POST", "/api/reset-data"), ("POST", "/api/visualize"),
           # the rest of the route table: the remaining study and mock exam actions, the account endpoints
           ("POST", "/api/lab-solution"), ("POST", "/api/mock/answer"), ("POST", "/api/mock/submit"),
           ("POST", "/api/mock/abandon"), ("GET", "/api/auth/me"), ("POST", "/api/auth/logout"),
           ("POST", "/api/account/password"), ("POST", "/api/account/set-password"),
           ("GET", "/api/account/sessions"), ("POST", "/api/account/sessions/end"),
           ("POST", "/api/account/sessions/end-others"), ("POST", "/api/account/google/unlink"),
           ("POST", "/api/account/delete"), ("GET", "/admin")]
ADMIN = [("GET", "/api/admin/users"), ("GET", "/api/admin/events"), ("GET", "/api/admin/settings"),
         ("POST", "/api/admin/reset-link"), ("POST", "/api/admin/lock"), ("POST", "/api/admin/unlock"),
         ("POST", "/api/admin/role"), ("POST", "/api/admin/delete"), ("POST", "/api/admin/recreate-schema"),
         ("POST", "/api/admin/delete-inactive"), ("POST", "/api/admin/settings")]


class User:
    """A registered, signed-in browser: get/post return the JSON body, or the status code on an error."""

    def __init__(self, http: Client):
        self.http = http

    def get(self, path):
        return self._json(self.http(path))

    def post(self, path, data):
        return self._json(self.http(path, data=data))

    @staticmethod
    def _json(response):
        status, _, body = response
        return json.loads(body) if status == 200 else (status, body)


def register(server: Client, email: str) -> User:
    return User(Client(server.port).sign_in(email))


@pytest.mark.parametrize("method,path", PRIVATE + ADMIN)
def test_every_private_endpoint_needs_a_session(serve, method, path):
    status, headers, body = serve()(path, data={} if method == "POST" else None)
    if method == "GET" and not path.startswith("/api/"):  # a page: the browser is sent to the login page
        assert status == 302 and headers["Location"].startswith("/login?next=")
    else:
        assert (status, json.loads(body)) == (401, {"error": "Login required"})


def test_the_route_table_and_the_private_list_stay_in_sync(tmp_path):
    app = build_app(settings_for(tmp_path), stores=memory_stores())
    unlisted = [route for route in app.router.routes()
                if route[1] not in PUBLIC_PATHS and route not in PRIVATE and route not in ADMIN]
    assert unlisted == []


def test_user_context_refuses_a_request_without_a_principal():
    contexts = UserContexts(memory_stores())
    with pytest.raises(LoginRequired, match="Login required") as raised:
        contexts(Request("GET", "/api/state", {}))
    assert raised.value.status == 401


def test_user_context_has_the_users_own_state_and_notes():
    stores = memory_stores()
    principal = Principal("u1", "a@x.org", "user", "hash", "csrf", None)
    ctx = UserContexts(stores)(Request("GET", "/api/state", {}, principal=principal))
    assert ctx.principal == principal and ctx.practice is None
    assert ctx.state is stores.states.for_user("u1") and ctx.notes is stores.notes.for_user("u1")


def test_users_do_not_see_each_others_progress_or_notes(serve):
    server = serve(stores=memory_stores())
    a, b = register(server, "a@x.org"), register(server, "b@x.org")
    a.post("/api/settings", {"exam_date": "2027-01-01"})
    a_note_path = a.post("/api/notes/save", {"title": "Secret", "sql": "SELECT 1 FROM dual;"})["path"]
    assert a.get("/api/state")["settings"]["exam_date"] == "2027-01-01"
    assert b.get("/api/state")["settings"].get("exam_date") is None
    assert a_note_path in [n["path"] for n in a.get("/api/notes")]
    assert not [n for n in b.get("/api/notes") if n["path"].startswith("personal/")]
    assert b.get("/api/note?path=" + a_note_path)[0] == 404


def test_progress_and_mock_exams_are_kept_per_user(serve):
    stores = memory_stores()
    server = serve(stores=stores)
    a, b = register(server, "a@x.org"), register(server, "b@x.org")
    mock = a.post("/api/mock/start", {"count": 2, "minutes": 5})["mock"]
    assert b.get("/api/mock?id=" + mock["id"])[0] == 404
    assert b.post("/api/mock/submit", {"mock_id": mock["id"]})[0] == 400  # an unknown mock, as for any bad id
    assert a.get("/api/mock?id=" + mock["id"])["report"] is None  # still open
    user_a = stores.users.by_email("a@x.org")
    assert mock["id"] in json.dumps(stores.states.for_user(user_a.id).load())
