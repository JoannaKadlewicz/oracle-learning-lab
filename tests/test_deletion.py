import json

import pytest

from conftest import PASSWORD
from oracle_lab.accounts.deletion import AccountDeletion
from oracle_lab.accounts.memory import memory_stores
from oracle_lab.auth.audit import AuditLog
from oracle_lab.auth.models import AuthError, Identity, PracticeSchema, User
from oracle_lab.auth.sessions import SessionManager


def test_delete_removes_everything_and_ends_sessions():
    stores = memory_stores()
    sessions = SessionManager(stores.sessions, lambda: 1.0)
    stores.users.add(User("u1", "a@example.org", "A", "user", "active", 1.0, None, None),
                     Identity("password", "u1", "u1", "h"))
    stores.users.add(User("u2", "b@example.org", "B", "user", "active", 1.0, None, None),
                     Identity("password", "u2", "u2", "h"))
    with stores.states.for_user("u2").transaction() as s:
        s["settings"]["keep"] = 1
    stores.notes.for_user("u2").add("m", "M", "kept")
    token, _ = sessions.start("u1", "ip", "ua")
    other, _ = sessions.start("u2", "ip", "ua")
    with stores.states.for_user("u1").transaction() as s:
        s["settings"]["x"] = 1
    stores.notes.for_user("u1").add("n", "N", "text")
    stores.schemas.put(PracticeSchema("u1", "default", "U1_SCHEMA", "ready", 1.0))
    dropped = []
    AccountDeletion(stores, sessions, AuditLog(stores.audit, lambda: 1.0), dropped.append).delete("u1", "admin-9")

    assert dropped == ["u1"]
    assert stores.users.get("u1") is None and stores.users.identities("u1") == []
    assert sessions.resolve(token) is None and sessions.resolve(other) is not None
    assert stores.states.for_user("u1").load()["settings"] == {} and stores.notes.for_user("u1").entries() == []
    assert stores.schemas.for_user("u1") == [] and stores.users.get("u2")
    assert stores.states.for_user("u2").load()["settings"] == {"keep": 1}
    assert stores.notes.for_user("u2").read("m.md") == "kept"
    (event,) = stores.audit.recent(event="account_deleted")
    assert event.detail["actor"] == "admin-9"


def _admin(stores):
    stores.users.add(User("boss", "boss@example.org", "Boss", "admin", "active", 1.0, None, None),
                     Identity("password", "boss", "boss", "h"))


def test_delete_needs_password_or_recent_reauth(tmp_path, serve):
    from conftest import settings_for
    stores = memory_stores()
    _admin(stores)
    http = serve(settings_for(tmp_path), stores=stores).sign_in("me@example.org")
    post = lambda data: http("/api/account/delete", data)  # noqa: E731

    status, _, body = post({"password": "wrong password!"})
    assert status == 401 and json.loads(body)["error"] == "Your password is incorrect."
    assert stores.users.by_email("me@example.org")
    status, headers, body = post({"password": PASSWORD})
    assert status == 200 and json.loads(body) == {"ok": True}
    assert "Max-Age=0" in "".join(headers.get_all("Set-Cookie"))
    assert stores.users.by_email("me@example.org") is None


def test_google_only_account_needs_recent_reauth(tmp_path, serve):
    from conftest import settings_for
    stores = memory_stores()
    _admin(stores)
    http = serve(settings_for(tmp_path), stores=stores).sign_in("g@example.org")
    user = stores.users.by_email("g@example.org")
    stores.users.add_identity(Identity("google", "sub-g", user.id, None))
    stores.users.remove_identity(user.id, "password")
    status, _, body = http("/api/account/delete", {})
    assert status == 403 and json.loads(body)["error"] == "Confirm with Google first."
    (rec,) = stores.sessions.for_user(user.id)
    stores.sessions.set_reauth(rec.token_hash, 1_800_000_000 + 300)
    assert http("/api/account/delete", {})[0] == 200
    assert stores.users.get(user.id) is None


def test_the_only_admin_cannot_be_deleted():
    stores = memory_stores()
    sessions = SessionManager(stores.sessions, lambda: 1.0)
    for uid, role in (("a1", "admin"), ("a2", "admin")):
        stores.users.add(User(uid, f"{uid}@example.org", uid, role, "active", 1.0, None, None),
                         Identity("password", uid, uid, "h"))
    deletion = AccountDeletion(stores, sessions, AuditLog(stores.audit, lambda: 1.0))
    deletion.delete("a1", "a2")
    with pytest.raises(AuthError, match="only admin"):
        deletion.delete("a2", "a2")
    assert stores.users.get("a2")


def test_a_locked_admin_does_not_keep_the_only_active_admin_deletable():
    stores = memory_stores()
    sessions = SessionManager(stores.sessions, lambda: 1.0)
    for uid, status in (("a1", "active"), ("a2", "locked")):
        stores.users.add(User(uid, f"{uid}@example.org", uid, "admin", status, 1.0, None, None),
                         Identity("password", uid, uid, "h"))
    deletion = AccountDeletion(stores, sessions, AuditLog(stores.audit, lambda: 1.0))
    with pytest.raises(AuthError, match="You can't delete the only admin account."):
        deletion.delete("a1", "a1")  # self-service: a1 is the only ACTIVE admin
    assert stores.users.get("a1")
    deletion.delete("a2", "a1")  # the locked admin can go


def test_two_admins_deleting_themselves_at_once_leave_one():
    import threading

    stores = memory_stores()
    sessions = SessionManager(stores.sessions, lambda: 1.0)
    for uid in ("a1", "a2"):
        stores.users.add(User(uid, f"{uid}@example.org", uid, "admin", "active", 1.0, None, None),
                         Identity("password", uid, uid, "h"))
    both_checked = threading.Barrier(2, timeout=1)

    def slow_drop(user_id):  # inside the guard: without it, both would pass the check before either deletes
        try:
            both_checked.wait()
        except threading.BrokenBarrierError:
            pass

    deletion = AccountDeletion(stores, sessions, AuditLog(stores.audit, lambda: 1.0), slow_drop)
    outcomes = []

    def delete_self(uid):
        try:
            deletion.delete(uid, uid)
            outcomes.append("ok")
        except AuthError:
            outcomes.append("refused")

    threads = [threading.Thread(target=delete_self, args=(uid,)) for uid in ("a1", "a2")]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    assert sorted(outcomes) == ["ok", "refused"]
    assert len([u for u in stores.users.all() if u.role == "admin"]) == 1

