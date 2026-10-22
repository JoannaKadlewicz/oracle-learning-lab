"""The admin page: users, reset links, locks, roles, schemas, registration settings and security events."""

import json

import pytest

from conftest import NOW, PASSWORD, Client
from oracle_lab.accounts.deletion import AccountDeletion
from oracle_lab.accounts.memory import memory_stores
from oracle_lab.auth.audit import AuditLog
from oracle_lab.auth.models import AuthError, Identity, PracticeSchema, Principal, User
from oracle_lab.auth.registration import RegistrationPolicy
from oracle_lab.auth.sessions import SessionManager
from oracle_lab.auth.tokens import token_hash
from oracle_lab.services.admin import AdminService, NotFound
from oracle_lab.web.http import HttpError
from oracle_lab.web.middleware import require_admin
from test_isolation import ADMIN

DAY = 86400


class FakePractice:
    """Stands in for PracticeDatabases of one user: provisions on demand and reports sizes."""

    def __init__(self, user, calls, sizes):
        self.user = user
        self.calls = calls
        self.sizes = sizes
        self.provisioners = {"default": object(), "23ai": object()}

    def provision(self, key):
        self.calls.append((self.user.id, key))
        return PracticeSchema(self.user.id, key, "OLL_NEW", "ready", NOW)

    def size_mb(self, key):
        size = self.sizes.get((self.user.id, key))
        if isinstance(size, Exception):
            raise size
        return size


def _user(stores, uid, role="learner", created=NOW - 100 * DAY, last_login=None, provider="password"):
    user = User(uid, f"{uid}@example.org", uid, role, "active", created, last_login, None)
    stores.users.add(user, Identity(provider, uid, uid, "h" if provider == "password" else None))
    return user


def _actor(user_id="boss"):
    return Principal(user_id, f"{user_id}@example.org", "admin", "hash", "csrf", 0.0)


@pytest.fixture
def admin():
    stores = memory_stores()
    clock = lambda: NOW  # noqa: E731
    sessions = SessionManager(stores.sessions, clock)
    audit = AuditLog(stores.audit, clock)
    dropped = []
    deletion = AccountDeletion(stores, sessions, audit, dropped.append)
    policy = RegistrationPolicy(stores.settings, stores.users, True, 25)
    calls, sizes = [], {}
    service = AdminService(stores, deletion, sessions, policy, lambda user: FakePractice(user, calls, sizes), audit,
                           clock, "https://lab.example.org")
    _user(stores, "boss", role="admin", last_login=NOW)
    service.stores, service.sessions_, service.calls, service.sizes, service.dropped = (
        stores, sessions, calls, sizes, dropped)
    return service


# --- authorization ---------------------------------------------------------------------------------------------

def test_require_admin_hides_the_admin_area_from_everyone_else():
    assert require_admin(_actor()).user_id == "boss"
    learner = Principal("u1", "u1@example.org", "learner", "h", "c", 0.0)
    for subject in (learner, None):
        with pytest.raises(HttpError) as raised:
            require_admin(subject)
        assert (raised.value.status, raised.value.message) == (404, "Not found")


@pytest.mark.parametrize("method,path", ADMIN)
def test_learner_gets_404_on_every_admin_route(serve, method, path):
    server = serve(stores=memory_stores())
    server.sign_in("owner@example.org")  # the first account is the admin
    learner = Client(server.port).sign_in("learner@example.org")
    status, _, body = learner(path, data={} if method == "POST" else None)
    assert (status, json.loads(body)) == (404, {"error": "Not found"})


@pytest.mark.parametrize("method,path", [r for r in ADMIN if r[0] == "POST"])
def test_admin_posts_need_the_csrf_token(serve, method, path):
    owner = serve(stores=memory_stores()).sign_in("owner@example.org")
    status, _, _ = owner(path, data={}, headers={"X-CSRF-Token": "wrong"})
    assert status == 403


def test_admin_api_over_http(serve):
    stores = memory_stores()
    server = serve(stores=stores)
    owner = Client(server.port).sign_in("owner@example.org")
    Client(server.port).sign_in("learner@example.org")
    learner = stores.users.by_email("learner@example.org")

    users = json.loads(owner("/api/admin/users")[2])["users"]
    row = next(u for u in users if u["email"] == "learner@example.org")
    assert row["methods"] == ["password"] and row["role"] == "learner" and row["sessions"] == 1
    assert row["schemas"] == []
    status, _, body = owner("/api/admin/reset-link", {"user_id": learner.id})
    assert status == 200 and "/reset?token=" in json.loads(body)["link"]
    assert owner("/api/admin/lock", {"user_id": "nobody"})[0] == 404
    assert owner("/api/admin/lock", {"user_id": 5})[0] == 400
    status, _, body = owner("/api/admin/lock", {"user_id": stores.users.by_email("owner@example.org").id})
    assert (status, json.loads(body)["error"]) == (400, "You can't do that to your own account.")
    assert owner("/api/admin/role", {"user_id": learner.id, "role": "root"})[0] == 400
    assert owner("/api/admin/delete-inactive", {"days": 0})[0] == 400
    assert owner("/api/admin/delete-inactive", {"days": "7"})[0] == 400
    assert owner("/api/admin/settings", {"max_users": 0})[0] == 400
    assert owner("/api/admin/settings", {"open": "yes"})[0] == 400
    assert owner("/api/admin/recreate-schema", {"user_id": learner.id, "key": "default"})[0] == 404
    assert owner("/api/admin/events?limit=abc")[0] == 400
    events = json.loads(owner("/api/admin/events?event=reset_link_created")[2])["events"]
    assert [e["event"] for e in events] == ["reset_link_created"]
    settings = json.loads(owner("/api/admin/settings")[2])
    assert settings == {"registration_open": True, "max_users": 25, "users": 2}


# --- the service -----------------------------------------------------------------------------------------------

def test_users_lists_methods_sessions_and_schemas(admin):
    stores = admin.stores
    _user(stores, "u1")
    _user(stores, "u2", provider="google")
    stores.users.add_identity(Identity("password", "u2", "u2", "h"))
    admin.sessions_.start("u1", "ip", "ua")
    admin.sessions_.start("u1", "ip", "ua")
    stores.schemas.put(PracticeSchema("u1", "default", "OLL_A", "ready", NOW))
    stores.schemas.put(PracticeSchema("u1", "23ai", "OLL_B", "failed", NOW, "ORA-01950"))
    stores.schemas.put(PracticeSchema("u2", "default", "OLL_C", "ready", NOW))
    admin.sizes[("u1", "default")] = 12.5
    admin.sizes[("u2", "default")] = RuntimeError("no DBA_SEGMENTS")

    rows = {u["id"]: u for u in admin.users()}
    assert rows["u1"]["methods"] == ["password"] and rows["u2"]["methods"] == ["google", "password"]
    assert rows["u1"]["sessions"] == 2 and rows["u2"]["sessions"] == 0
    assert sorted(rows["u1"]["schemas"], key=lambda s: s["key"]) == [
        {"key": "23ai", "status": "failed", "size_mb": None, "error": "ORA-01950"},
        {"key": "default", "status": "ready", "size_mb": 12.5, "error": None}]
    assert rows["u2"]["schemas"] == [{"key": "default", "status": "ready", "size_mb": None, "error": None}]
    assert set(rows["boss"]) == {"id", "email", "methods", "role", "status", "created_at", "last_login_at",
                                 "sessions", "schemas"}


def test_reset_link_works_once(serve):
    stores = memory_stores()
    server = serve(stores=stores)
    owner = Client(server.port).sign_in("owner@example.org")
    Client(server.port).sign_in("learner@example.org")
    learner = stores.users.by_email("learner@example.org")

    link = json.loads(owner("/api/admin/reset-link", {"user_id": learner.id})[2])["link"]
    assert "/reset?token=" in link
    token = link.split("token=", 1)[1]
    anonymous = Client(server.port)
    reset = lambda: anonymous("/api/auth/reset", {"token": token, "password": "another long passphrase"},  # noqa: E731
                              headers={"Origin": anonymous.origin})
    assert reset()[0] == 200
    status, _, body = reset()
    assert status == 400 and "invalid or has expired" in json.loads(body)["error"]
    status, _, _ = anonymous("/api/auth/login", {"email": "learner@example.org", "password": "another long passphrase"},
                             headers={"Origin": anonymous.origin})
    assert status == 200
    (event,) = stores.audit.recent(event="reset_link_created")
    assert event.detail == {"target": learner.id}
    assert token not in json.dumps([e.detail for e in stores.audit.recent()])


def test_reset_link_expires_after_a_day(admin):
    _user(admin.stores, "u1")
    link = admin.reset_link(_actor(), "u1")
    assert link.startswith("https://lab.example.org/reset?token=")
    token = link.split("token=", 1)[1]
    assert admin.stores.resets.take(token_hash(token), NOW + DAY + 1) is None
    assert admin.stores.resets.take(token_hash(token), NOW + DAY - 1).created_by == "boss"
    with pytest.raises(NotFound):
        admin.reset_link(_actor(), "nobody")


def test_a_new_reset_link_revokes_the_earlier_ones(admin):
    _user(admin.stores, "u1")
    _user(admin.stores, "u2")
    first = admin.reset_link(_actor(), "u1").split("token=", 1)[1]
    other = admin.reset_link(_actor(), "u2").split("token=", 1)[1]
    second = admin.reset_link(_actor(), "u1").split("token=", 1)[1]
    assert admin.stores.resets.take(token_hash(first), NOW) is None
    assert admin.stores.resets.take(token_hash(second), NOW) is not None
    assert admin.stores.resets.take(token_hash(other), NOW) is not None


def test_lock_ends_sessions_and_blocks_login(serve):
    stores = memory_stores()
    server = serve(stores=stores)
    owner = Client(server.port).sign_in("owner@example.org")
    learner_http = Client(server.port).sign_in("learner@example.org")
    learner = stores.users.by_email("learner@example.org")

    assert owner("/api/admin/lock", {"user_id": learner.id})[0] == 200
    assert stores.users.get(learner.id).status == "locked" and stores.sessions.for_user(learner.id) == []
    assert learner_http("/api/auth/me")[0] == 401
    anonymous = Client(server.port)
    login = lambda: anonymous("/api/auth/login", {"email": "learner@example.org", "password": PASSWORD},  # noqa: E731
                              headers={"Origin": anonymous.origin})
    assert login()[0] == 401
    assert owner("/api/admin/unlock", {"user_id": learner.id})[0] == 200
    assert stores.users.get(learner.id).status == "active" and login()[0] == 200


def test_admin_cannot_lock_or_demote_or_delete_self(admin):
    me = _actor()
    for action in (lambda: admin.lock(me, "boss"), lambda: admin.set_role(me, "boss", "learner"),
                   lambda: admin.delete(me, "boss")):
        with pytest.raises(ValueError, match="You can't do that to your own account."):
            action()
    assert admin.stores.users.get("boss").role == "admin" and admin.stores.users.get("boss").status == "active"


def test_the_last_admin_cannot_be_demoted(admin):
    _user(admin.stores, "other", role="admin")
    admin.set_role(_actor(), "other", "learner")  # two admins: fine
    assert admin.stores.users.get("other").role == "learner"
    admin.stores.users.update(User("boss", "boss@example.org", "boss", "learner", "active", NOW, NOW, None))
    _user(admin.stores, "solo", role="admin")
    with pytest.raises(AuthError, match="You can't remove the only admin."):
        admin.set_role(_actor(), "solo", "learner")


def test_set_role_promotes_and_rejects_unknown_roles(admin):
    _user(admin.stores, "u1")
    admin.set_role(_actor(), "u1", "admin")
    assert admin.stores.users.get("u1").role == "admin"
    with pytest.raises(ValueError):
        admin.set_role(_actor(), "u1", "root")


def test_delete_drops_the_account(admin):
    _user(admin.stores, "u1")
    admin.delete(_actor(), "u1")
    assert admin.stores.users.get("u1") is None and admin.dropped == ["u1"]
    with pytest.raises(NotFound):
        admin.delete(_actor(), "u1")


def test_recreate_schema_provisions_for_that_user(admin):
    _user(admin.stores, "u1")
    result = admin.recreate_schema(_actor(), "u1", "23ai")
    assert admin.calls == [("u1", "23ai")] and result["status"] == "ready"
    with pytest.raises(NotFound):
        admin.recreate_schema(_actor(), "u1", "nope")
    with pytest.raises(NotFound):
        admin.recreate_schema(_actor(), "nobody", "default")


def test_delete_inactive_spares_admins(admin):
    stores = admin.stores
    stores.users.update(User("boss", "boss@example.org", "boss", "admin", "active", NOW - 400 * DAY,
                             NOW - 400 * DAY, None))  # the actor, long inactive
    _user(stores, "old_admin", role="admin", created=NOW - 400 * DAY)
    _user(stores, "old", last_login=NOW - 40 * DAY)
    _user(stores, "never", created=NOW - 31 * DAY)
    _user(stores, "recent", last_login=NOW - 5 * DAY, created=NOW - 400 * DAY)
    _user(stores, "new", created=NOW - DAY)

    assert admin.delete_inactive(_actor(), 30) == 2
    assert sorted(u.id for u in stores.users.all()) == ["boss", "new", "old_admin", "recent"]
    with pytest.raises(ValueError):
        admin.delete_inactive(_actor(), 0)
    (summary,) = stores.audit.recent(event="inactive_accounts_deleted")
    assert summary.detail == {"days": 30, "count": 2}


def test_registration_settings_apply_immediately(serve):
    stores = memory_stores()
    server = serve(stores=stores)
    owner = Client(server.port).sign_in("owner@example.org")

    assert json.loads(owner("/api/admin/settings", {"open": False})[2])["registration_open"] is False
    anonymous = Client(server.port)
    assert json.loads(anonymous("/api/auth/config")[2])["registration_open"] is False
    status, _, _ = anonymous("/api/auth/register", {"email": "x@example.org", "password": PASSWORD},
                             headers={"Origin": anonymous.origin})
    assert status == 403
    owner("/api/admin/settings", {"open": True, "max_users": 2})
    assert json.loads(owner("/api/admin/settings")[2]) == {"registration_open": True, "max_users": 2, "users": 1}
    Client(server.port).sign_in("second@example.org")
    status, _, _ = anonymous("/api/auth/register", {"email": "third@example.org", "password": PASSWORD},
                             headers={"Origin": anonymous.origin})
    assert status == 403


def test_update_settings_validates(admin):
    for kwargs in ({"max_users": 0}, {"max_users": True}, {"open": "yes"}):
        with pytest.raises(ValueError):
            admin.update_settings(_actor(), **kwargs)


def test_events_newest_first_with_filters(admin):
    _user(admin.stores, "u1")
    admin.lock(_actor(), "u1")
    admin.unlock(_actor(), "u1")
    events = admin.events()
    assert [e["event"] for e in events[:2]] == ["user_unlocked", "user_locked"]
    assert set(events[0]) == {"t", "event", "outcome", "user_id", "ip", "user_agent", "detail"}
    assert [e["event"] for e in admin.events(event="user_locked")] == ["user_locked"]
    assert admin.events(user_id="nobody") == []
    assert len(admin.events(limit=1)) == 1
    assert len(admin.events(limit=10_000)) <= 500


def test_every_admin_action_is_audited(admin):
    _user(admin.stores, "u1")
    _user(admin.stores, "u2")
    me = _actor()
    meta = {"ip": "203.0.113.7", "user_agent": "AdminBrowser/1"}
    admin.reset_link(me, "u1", **meta)
    admin.lock(me, "u1", **meta)
    admin.unlock(me, "u1", **meta)
    admin.set_role(me, "u1", "admin", **meta)
    admin.recreate_schema(me, "u1", "default", **meta)
    admin.update_settings(me, open=False, max_users=3, **meta)
    admin.delete(me, "u2", **meta)
    admin.delete_inactive(me, 1, **meta)
    seen = {e.event: e for e in admin.stores.audit.recent()}
    for event in ("reset_link_created", "user_locked", "user_unlocked", "role_changed", "schema_recreated",
                  "registration_settings_changed", "account_deleted", "inactive_accounts_deleted"):
        assert seen[event].user_id == "boss", event
        assert (seen[event].ip, seen[event].user_agent) == ("203.0.113.7", "AdminBrowser/1"), event
        assert seen[event].outcome == "ok", event
    assert seen["role_changed"].detail == {"target": "u1", "role": "admin"}
    assert seen["registration_settings_changed"].detail == {"open": False, "max_users": 3}
    assert seen["user_locked"].detail == {"target": "u1"}


def test_refused_admin_actions_are_audited_as_denied(admin):
    me = _actor()
    for action, event in ((lambda: admin.lock(me, "boss", ip="1.2.3.4"), "user_locked"),
                          (lambda: admin.set_role(me, "boss", "learner", ip="1.2.3.4"), "role_changed"),
                          (lambda: admin.delete(me, "boss", ip="1.2.3.4"), "account_deleted")):
        with pytest.raises(ValueError):
            action()
        (denied,) = admin.stores.audit.recent(event=event)
        assert (denied.outcome, denied.ip, denied.detail) == ("denied", "1.2.3.4", {"target": "boss", "reason": "self"})


def test_only_active_admins_count_as_the_last_admin(admin):
    stores = admin.stores
    stores.users.set_role("boss", "learner")  # e.g. demoted by another admin meanwhile
    _user(stores, "a2", role="admin")
    _user(stores, "a3", role="admin")
    stores.users.set_status("a3", "locked")
    for action, event in ((lambda: admin.set_role(_actor(), "a2", "learner"), "role_changed"),
                          (lambda: admin.lock(_actor(), "a2"), "user_locked"),
                          (lambda: admin.delete(_actor(), "a2"), "account_deleted")):
        with pytest.raises(AuthError, match="You can't remove the only admin."):
            action()
        (denied,) = stores.audit.recent(event=event)
        assert (denied.outcome, denied.detail["reason"]) == ("denied", "last_admin")
    assert stores.users.get("a2").role == "admin" and stores.users.get("a2").status == "active"
    admin.set_role(_actor(), "a3", "learner")  # a locked admin is not the last one
    assert stores.users.get("a3").role == "learner"


def test_lock_and_role_change_touch_only_their_column(admin):
    _user(admin.stores, "u1")
    admin.lock(_actor(), "u1")
    admin.stores.users.record_login("u1", NOW + 5)  # a sign-in racing the admin keeps its timestamp
    admin.set_role(_actor(), "u1", "admin")
    user = admin.stores.users.get("u1")
    assert (user.status, user.role, user.last_login_at) == ("locked", "admin", NOW + 5)


def test_a_learner_reaching_for_the_admin_api_is_audited(serve):
    stores = memory_stores()
    server = serve(stores=stores)
    server.sign_in("owner@example.org")
    learner = Client(server.port).sign_in("learner@example.org")
    assert learner("/api/admin/lock", {"user_id": "x"}, headers={"User-Agent": "Sneaky/2"})[0] == 404
    (event,) = stores.audit.recent(event="admin_denied")
    assert event.outcome == "denied" and event.user_id == stores.users.by_email("learner@example.org").id
    assert event.detail == {"path": "/api/admin/lock"} and event.user_agent == "Sneaky/2" and event.ip == "127.0.0.1"


def test_admin_actions_over_http_record_the_client(serve):
    stores = memory_stores()
    server = serve(stores=stores)
    owner = Client(server.port).sign_in("owner@example.org")
    Client(server.port).sign_in("learner@example.org")
    learner = stores.users.by_email("learner@example.org")
    owner("/api/admin/lock", {"user_id": learner.id}, headers={"User-Agent": "Owner/3"})
    owner("/api/admin/delete", {"user_id": learner.id}, headers={"User-Agent": "Owner/3"})
    for name in ("user_locked", "account_deleted"):
        (event,) = stores.audit.recent(event=name)
        assert (event.ip, event.user_agent) == ("127.0.0.1", "Owner/3"), name


def test_the_admin_page_uses_the_deletion_guard(admin):
    assert admin._guard is admin._deletion.guard  # one lock with self-service deletion


def test_admin_denied_is_recorded_at_most_ten_times_an_hour(admin):
    learner = Principal("u1", "u1@example.org", "learner", "h", "c", 0.0)
    for _ in range(15):
        admin.denied(learner, "/api/admin/users", ip="1.2.3.4", user_agent="ua")
    assert len(admin.stores.audit.recent(event="admin_denied")) == 10
    other = Principal("u2", "u2@example.org", "learner", "h", "c", 0.0)
    admin.denied(other, "/api/admin/users")  # counted per account
    assert len(admin.stores.audit.recent(event="admin_denied", user_id="u2")) == 1


def test_admin_denied_cap_over_http_still_answers_404(serve):
    stores = memory_stores()
    server = serve(stores=stores)
    server.sign_in("owner@example.org")
    learner = Client(server.port).sign_in("learner@example.org")
    statuses = [learner("/api/admin/users")[0] for _ in range(12)]
    assert statuses == [404] * 12 and len(stores.audit.recent(event="admin_denied")) == 10


def test_set_role_accepts_the_free_role(admin):
    _user(admin.stores, "u1")
    admin.set_role(_actor(), "u1", "free")
    assert admin.stores.users.get("u1").role == "free"


@pytest.mark.parametrize("method,path", [("POST", "/api/run"), ("POST", "/api/visualize"), ("GET", "/api/schema"),
                                         ("POST", "/api/reset-data"), ("POST", "/api/grade")])
def test_a_free_account_cannot_run_sql(serve, method, path):
    stores = memory_stores()
    server = serve(stores=stores)
    owner = Client(server.port).sign_in("owner@example.org")
    free = Client(server.port).sign_in("free@example.org")
    user = stores.users.by_email("free@example.org")
    assert owner("/api/admin/role", {"user_id": user.id, "role": "free"})[0] == 200
    status, _, body = free(path, {"sql": "select 1 from dual", "id": "x"} if method == "POST" else None)
    assert status == 403
    assert json.loads(body)["error"] == "Your account cannot run SQL. Ask an admin for learner access."
    assert json.loads(free("/api/progress")[2])["sql_available"] is False
    assert free("/api/admin/users")[0] == 404  # and no admin area
