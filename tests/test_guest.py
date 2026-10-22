"""Guest access: "Try it without an account" makes a guest session; registering from it keeps the progress."""

from __future__ import annotations

import json

from conftest import NOW, PASSWORD, Client, session_cookie
from oracle_lab import content
from oracle_lab.accounts.maintenance import GUEST_IDLE_DAYS, Maintenance
from oracle_lab.accounts.memory import memory_stores
from oracle_lab.auth.audit import AuditLog
from oracle_lab.study import engine


def start_guest(client: Client) -> Client:
    status, headers, body = client("/api/auth/guest", {}, headers={"Origin": client.origin})
    assert status == 200, body
    cookie = session_cookie(headers)
    me = json.loads(client("/api/auth/me", headers={"Cookie": cookie})[2])
    client.headers = {"Cookie": cookie, "X-CSRF-Token": me["csrf_token"], "Origin": client.origin}
    return client


def test_guest_start_creates_a_guest_session(serve):
    stores = memory_stores()
    server = serve(stores=stores)
    server.sign_in("admin@x.org")
    guest = start_guest(Client(server.port))
    me = json.loads(guest("/api/auth/me")[2])["user"]
    assert me["role"] == "guest"
    assert guest("/register")[0] == 200  # a guest may open the sign-up page (others are sent to the app)
    assert stores.users.count() == 2


def test_guests_do_not_count_toward_the_user_cap_or_the_first_admin(serve, tmp_path):
    from conftest import settings_for

    stores = memory_stores()
    server = serve(settings_for(tmp_path, STUDY_MAX_USERS="1"), stores=stores)
    start_guest(Client(server.port))
    first = Client(server.port).sign_in("first@x.org")  # still the first real account: the admin, under the cap
    assert json.loads(first("/api/auth/me")[2])["user"]["role"] == "admin"


def test_guest_creation_is_throttled(serve):
    server = serve(stores=memory_stores())
    statuses = [Client(server.port)("/api/auth/guest", {}, headers={"Origin": server.origin})[0] for _ in range(12)]
    assert statuses[0] == 200 and 429 in statuses


def test_registering_from_a_guest_keeps_progress_notes_and_workspace(serve):
    stores = memory_stores()
    server = serve(stores=stores)
    server.sign_in("admin@x.org")
    guest = start_guest(Client(server.port))
    guest_id = json.loads(guest("/api/auth/me")[2])["user"]["id"]
    assert guest("/api/workspaces/choose", {"workspace": "1Z0-171"})[0] == 200
    question = content.QUESTIONS[0]
    assert guest("/api/attempt", {"id": question["id"], "chosen": question["answer"]})[0] == 200
    note = json.loads(guest("/api/notes/save", {"title": "Mine", "sql": "SELECT 1 FROM dual;"})[2])["path"]
    status, headers, _ = guest("/api/auth/register", {"email": "new@x.org", "password": PASSWORD})
    assert status == 200
    user = stores.users.by_email("new@x.org")
    assert user.role == "user" and stores.users.get(guest_id) is None
    assert [r.workspace for r in stores.access.for_user(user.id)] == ["1Z0-171"]
    assert question["id"] in stores.states.for_user(user.id).load()["attempts"]
    assert len(stores.notes.for_user(user.id).entries()) == 1 and note.startswith("personal/")


def test_registering_without_a_guest_is_unchanged(serve):
    stores = memory_stores()
    server = serve(stores=stores)
    server.sign_in("admin@x.org")
    Client(server.port).sign_in("plain@x.org")
    user = stores.users.by_email("plain@x.org")
    assert user.role == "user" and stores.access.for_user(user.id) == []


def test_old_guests_are_purged(serve):
    stores = memory_stores()
    server = serve(stores=stores)
    start_guest(Client(server.port))
    guest = next(u for u in stores.users.all() if u.role == "guest")
    later = NOW + (GUEST_IDLE_DAYS + 1) * engine.DAY
    Maintenance(stores, AuditLog(stores.audit, lambda: later), lambda: later).run_once()
    assert stores.users.get(guest.id) is None
