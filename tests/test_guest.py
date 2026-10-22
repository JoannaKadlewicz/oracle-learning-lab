"""Guest access: "Try it without an account" makes a guest session; registering from it keeps the progress."""

from __future__ import annotations

import json

from conftest import NOW, PASSWORD, Client, session_cookie
from oracle_lab import content
from oracle_lab.accounts.maintenance import GUEST_GRACE, Maintenance
from oracle_lab.accounts.memory import memory_stores
from oracle_lab.auth.audit import AuditLog
from oracle_lab.auth.models import Identity, User
from oracle_lab.auth.sessions import SESSION_IDLE


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


def test_a_browser_with_a_guest_session_can_try_again_from_the_landing_page(serve):
    # A guest's "Sign in" keeps the session (for its progress); a landing tile then posts with the cookie, no token.
    server = serve(stores=memory_stores())
    cookie = start_guest(Client(server.port)).headers["Cookie"]
    landing = Client(server.port)
    status, headers, body = landing("/api/auth/guest", {"workspace": "1Z0-071"},
                                    headers={"Cookie": cookie, "Origin": landing.origin})
    assert status == 200, body
    assert session_cookie(headers) != cookie


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


def maintain(stores, at):
    Maintenance(stores, AuditLog(stores.audit, lambda: at), lambda: at).run_once()


def test_a_guest_whose_session_has_lapsed_is_purged(serve):
    stores = memory_stores()
    server = serve(stores=stores)
    start_guest(Client(server.port))
    guest = next(u for u in stores.users.all() if u.role == "guest")
    maintain(stores, NOW + SESSION_IDLE - 60)  # still signed in: kept
    assert stores.users.get(guest.id) is not None
    maintain(stores, NOW + SESSION_IDLE + 60)  # idle too long: nobody can reach this guest again
    assert stores.users.get(guest.id) is None
    assert stores.audit.recent(event="guest_purged")[0].detail == {"reason": "session_ended"}


def test_a_guest_just_created_is_kept_until_its_session_exists():
    stores = memory_stores()
    stores.users.add(User("g1", "g1@guest.invalid", "Guest", "guest", "active", NOW, NOW, None),
                     Identity("guest", "g1", "g1"))
    maintain(stores, NOW + GUEST_GRACE - 60)
    assert stores.users.get("g1") is not None
    maintain(stores, NOW + GUEST_GRACE + 60)
    assert stores.users.get("g1") is None


def test_a_guest_is_deleted_when_its_browser_starts_another(serve):
    stores = memory_stores()
    server = serve(stores=stores)
    cookie = start_guest(Client(server.port)).headers["Cookie"]
    first = next(u for u in stores.users.all() if u.role == "guest")
    landing = Client(server.port)
    assert landing("/api/auth/guest", {}, headers={"Cookie": cookie, "Origin": landing.origin})[0] == 200
    guests = [u for u in stores.users.all() if u.role == "guest"]
    assert len(guests) == 1 and guests[0].id != first.id


def test_a_guest_signing_out_is_deleted(serve):
    stores = memory_stores()
    server = serve(stores=stores)
    guest = start_guest(Client(server.port))
    assert guest("/api/auth/logout", {})[0] == 200
    assert not [u for u in stores.users.all() if u.role == "guest"]
