import json

from conftest import PASSWORD
from oracle_lab.accounts.deletion import AccountDeletion
from oracle_lab.accounts.memory import memory_stores
from oracle_lab.auth.audit import AuditLog
from oracle_lab.auth.models import Identity, PracticeSchema, User
from oracle_lab.auth.sessions import SessionManager


def test_delete_removes_everything_and_ends_sessions():
    stores = memory_stores()
    sessions = SessionManager(stores.sessions, lambda: 1.0)
    stores.users.add(User("u1", "a@example.org", "A", "learner", "active", 1.0, None, None),
                     Identity("password", "u1", "u1", "h"))
    stores.users.add(User("u2", "b@example.org", "B", "learner", "active", 1.0, None, None),
                     Identity("password", "u2", "u2", "h"))
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
    (event,) = stores.audit.recent(event="account_deleted")
    assert event.detail["actor"] == "admin-9"


def test_delete_needs_password_or_recent_reauth(tmp_path, serve):
    from conftest import settings_for
    stores = memory_stores()
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
