"""Each user's practice schemas, and the guard around learner sessions (no database needed)."""

import threading

import pytest

from oracle_lab import content
from oracle_lab.accounts.deletion import AccountDeletion
from oracle_lab.accounts.memory import memory_stores
from oracle_lab.auth.audit import AuditLog
from oracle_lab.auth.models import Identity, PracticeSchema, Principal, User
from oracle_lab.auth.sessions import SessionManager
from oracle_lab.config import DatabaseTarget
from oracle_lab.credentials import Secret
from oracle_lab.database.connection import DatabaseCatalog
from oracle_lab.provisioning.guards import RunGuard
from oracle_lab.provisioning.practice import (
    FAILED,
    NOT_SET_UP,
    PREPARING,
    PracticeDatabases,
    PracticeUnavailable,
    drop_user_schemas,
    provisioning_hook,
)
from oracle_lab.provisioning.proxy import ProxyDatabase
from oracle_lab.provisioning.schemas import SCHEMA_NAME
from oracle_lab.web.http import HttpError

EXAM_23AI = "1Z0-171"
NOW = 1_800_000_000.0


class FakeDatabase:
    def __init__(self, name="shared"):
        self.target = DatabaseTarget(name, "db", Secret(lambda: "pw", "test"))

    def connect(self):
        raise AssertionError("no connection expected")


class FakeProvisioner:
    """Records create/drop calls; `fail` is an exception the next create raises (once)."""

    def __init__(self, fail=None):
        self.calls = []
        self.fail = fail
        self.release = None  # an Event create waits for, to keep provisioning "running"

    def create(self, name):
        self.calls.append(("create", name))
        if self.release is not None:
            self.release.wait(5)
        if self.fail is not None:
            exc, self.fail = self.fail, None
            raise exc

    def drop(self, name):
        self.calls.append(("drop", name))


def principal(user_id="u1", role="learner"):
    return Principal(user_id, f"{user_id}@x.org", role, "hash", "csrf", 0.0)


def gateway(key):
    return DatabaseTarget(f"gw_{key}", f"dsn_{key}", Secret(lambda: "secret", "test"))


def practice(stores, provisioners, role="learner", user_id="u1", shared=None, clock=lambda: NOW):
    return PracticeDatabases(principal(user_id, role), stores.schemas, provisioners,
                             {key: gateway(key) for key in provisioners}, shared or DatabaseCatalog(FakeDatabase()),
                             15000, clock, audit=AuditLog(stores.audit, clock))


def test_learner_without_practice_targets_gets_unavailable():
    with pytest.raises(PracticeUnavailable) as raised:
        practice(memory_stores(), {}).for_exam("1Z0-071")
    assert str(raised.value) == NOT_SET_UP == "The practice database is not set up on this server."


def test_admin_falls_back_to_shared_schema():
    shared_19, shared_23 = FakeDatabase("orastudy"), FakeDatabase("orastudy23")
    catalog = DatabaseCatalog(shared_19, {EXAM_23AI: shared_23})
    admin = practice(memory_stores(), {}, role="admin", shared=catalog)
    assert admin.for_exam("1Z0-071") is shared_19
    assert admin.for_exam(EXAM_23AI) is shared_23


def test_ready_schema_is_reached_through_the_gateway():
    stores = memory_stores()
    stores.schemas.put(PracticeSchema("u1", "default", "OLL_UABCDEFGHIJ", "ready", NOW))
    db = practice(stores, {"default": FakeProvisioner()}).for_exam("1Z0-071")
    assert isinstance(db, ProxyDatabase) and db.schema == "OLL_UABCDEFGHIJ" and db.gateway.user == "gw_default"


def test_23ai_schema_is_created_on_first_use():
    stores = memory_stores()
    stores.schemas.put(PracticeSchema("u1", "default", "OLL_UABCDEFGHIJ", "ready", NOW))
    p19, p23 = FakeProvisioner(), FakeProvisioner()
    db = practice(stores, {"default": p19, "23ai": p23}).for_exam(EXAM_23AI)

    ((call, name),) = p23.calls
    assert call == "create" and SCHEMA_NAME.fullmatch(name) and p19.calls == []
    assert isinstance(db, ProxyDatabase) and db.schema == name and db.gateway.user == "gw_23ai"
    rec = stores.schemas.get("u1", "23ai")
    assert (rec.status, rec.schema_name, rec.error) == ("ready", name, None)
    (event,) = stores.audit.recent(event="schema_provisioned")
    assert event.user_id == "u1" and event.detail["schema"] == name


def test_without_a_23ai_target_the_23ai_track_uses_the_default_schema():
    stores = memory_stores()
    stores.schemas.put(PracticeSchema("u1", "default", "OLL_UABCDEFGHIJ", "ready", NOW))
    assert practice(stores, {"default": FakeProvisioner()}).for_exam(EXAM_23AI).schema == "OLL_UABCDEFGHIJ"


def test_schema_still_being_prepared_is_unavailable():
    stores = memory_stores()
    stores.schemas.put(PracticeSchema("u1", "default", "OLL_UABCDEFGHIJ", "provisioning", NOW - 60))
    provisioner = FakeProvisioner()
    with pytest.raises(PracticeUnavailable, match="^Your practice database is being prepared. Try again in a minute.$"):
        practice(stores, {"default": provisioner}).for_exam("1Z0-071")
    assert provisioner.calls == [] and PREPARING.startswith("Your practice database is being prepared")


def test_provisioning_running_in_another_thread_is_unavailable():
    stores = memory_stores()
    provisioner = FakeProvisioner()
    provisioner.release = threading.Event()
    worker = threading.Thread(target=practice(stores, {"default": provisioner}).provision, args=("default",))
    worker.start()
    try:
        while not provisioner.calls:
            threading.Event().wait(0.01)
        stores.schemas.delete_for_user("u1")  # as if the record were not written yet: the lock alone must stop it
        with pytest.raises(PracticeUnavailable, match="being prepared"):
            practice(stores, {"default": provisioner}).for_exam("1Z0-071")
    finally:
        provisioner.release.set()
        worker.join()
    assert len(provisioner.calls) == 1


def test_stale_provisioning_is_started_again():
    stores = memory_stores()
    stores.schemas.put(PracticeSchema("u1", "default", "OLL_UABCDEFGHIJ", "provisioning", NOW - 11 * 60))
    provisioner = FakeProvisioner()
    db = practice(stores, {"default": provisioner}).for_exam("1Z0-071")
    assert provisioner.calls[0] == ("drop", "OLL_UABCDEFGHIJ")
    assert provisioner.calls[1][0] == "create" and db.schema == provisioner.calls[1][1] != "OLL_UABCDEFGHIJ"


class OraError(Exception):
    pass


def test_failed_provisioning_is_reported_and_retry_recreates():
    stores = memory_stores()
    provisioner = FakeProvisioner(fail=OraError("ORA-01950: no privileges on tablespace 'USERS'\nHelp: https://x"))
    learner = practice(stores, {"default": provisioner})

    rec = learner.provision("default")
    assert rec.status == "failed" and rec.error == "ORA-01950: no privileges on tablespace 'USERS'"
    assert stores.schemas.get("u1", "default") == rec
    (event,) = stores.audit.recent(event="schema_failed")
    assert event.outcome == "fail" and event.detail["error"] == rec.error
    with pytest.raises(PracticeUnavailable) as raised:
        learner.for_exam("1Z0-071")
    assert str(raised.value) == FAILED == "Your practice database could not be created. An admin has been notified."

    retried = learner.provision("default")
    assert retried.status == "ready" and retried.schema_name != rec.schema_name
    assert provisioner.calls == [("create", rec.schema_name), ("drop", rec.schema_name),
                                 ("create", retried.schema_name)]
    assert learner.for_exam("1Z0-071").schema == retried.schema_name


def test_drop_errors_do_not_stop_a_retry():
    stores = memory_stores()
    stores.schemas.put(PracticeSchema("u1", "default", "OLL_UABCDEFGHIJ", "failed", NOW, "ORA-1"))
    provisioner = FakeProvisioner()
    provisioner.drop = lambda name: (_ for _ in ()).throw(OraError("ORA-03113"))
    assert practice(stores, {"default": provisioner}).provision("default").status == "ready"


def test_guard_allows_one_run_per_user_and_caps_total():
    guard = RunGuard(max_concurrent=8)
    guard.wait_seconds = 0.2
    with guard.run("u1"):
        errors = []

        def again():
            try:
                with guard.run("u1"):
                    pass
            except HttpError as exc:
                errors.append(exc)

        thread = threading.Thread(target=again)
        thread.start()
        thread.join()
        (error,) = errors
        assert (error.status, error.message) == (409, "Another statement of yours is still running.")

    holding, release = threading.Barrier(9), threading.Event()
    outcomes = []

    def hold(user):
        try:
            with guard.run(user):
                outcomes.append("ran")
                holding.wait(2)
                release.wait(2)
        except HttpError as exc:
            outcomes.append(exc)

    threads = [threading.Thread(target=hold, args=(f"user{i}",)) for i in range(8)]
    for thread in threads:
        thread.start()
    holding.wait(2)  # all 8 hold a slot
    hold("user8")
    release.set()
    for thread in threads:
        thread.join()
    (busy,) = [o for o in outcomes if isinstance(o, HttpError)]
    assert (busy.status, busy.message) == (503, "The practice database is busy. Try again in a moment.")
    assert outcomes.count("ran") == 8
    with guard.run("user8"):  # slots and users are released again
        pass


def test_deleting_an_account_drops_its_schemas():
    stores = memory_stores()
    stores.users.add(User("u1", "a@x.org", "A", "learner", "active", NOW, None, None), Identity("password", "u1", "u1", "h"))
    stores.schemas.put(PracticeSchema("u1", "default", "OLL_UAAAAAAAAAA", "ready", NOW))
    stores.schemas.put(PracticeSchema("u1", "23ai", "OLL_UBBBBBBBBBB", "failed", NOW, "ORA-1"))
    stores.schemas.put(PracticeSchema("u2", "default", "OLL_UCCCCCCCCCC", "ready", NOW))
    p19, p23 = FakeProvisioner(), FakeProvisioner()
    provisioners = {"default": p19, "23ai": p23}
    audit = AuditLog(stores.audit, lambda: NOW)
    deletion = AccountDeletion(stores, SessionManager(stores.sessions, lambda: NOW), audit,
                               lambda user_id: drop_user_schemas(user_id, stores.schemas, provisioners))
    deletion.delete("u1", "admin")
    assert p19.calls == [("drop", "OLL_UAAAAAAAAAA")] and p23.calls == [("drop", "OLL_UBBBBBBBBBB")]
    assert stores.schemas.for_user("u1") == [] and stores.schemas.get("u2", "default").status == "ready"


def test_drop_all_drops_and_forgets_the_users_schemas():
    stores = memory_stores()
    stores.schemas.put(PracticeSchema("u1", "default", "OLL_UAAAAAAAAAA", "ready", NOW))
    provisioner = FakeProvisioner()
    practice(stores, {"default": provisioner}).drop_all()
    assert provisioner.calls == [("drop", "OLL_UAAAAAAAAAA")] and stores.schemas.for_user("u1") == []


def test_sign_up_hook_provisions_the_default_schema_in_the_background():
    stores = memory_stores()
    provisioner = FakeProvisioner()
    provisioner.release = threading.Event()
    hook = provisioning_hook({"default": provisioner, "23ai": FakeProvisioner()}, stores.schemas, lambda: NOW,
                             AuditLog(stores.audit, lambda: NOW))
    user = User("u1", "a@x.org", "A", "learner", "active", NOW, None, None)
    hook(user)  # returns at once, while create is still waiting
    assert stores.schemas.get("u1", "23ai") is None
    provisioner.release.set()
    for thread in threading.enumerate():
        if thread.name.startswith("provision-"):
            thread.join(5)
    assert stores.schemas.get("u1", "default").status == "ready"


def test_sign_up_hook_never_raises():
    class Broken:
        def put(self, rec):
            raise RuntimeError("store down")

        def get(self, user_id, key):
            raise RuntimeError("store down")

    hook = provisioning_hook({"default": FakeProvisioner()}, Broken(), lambda: NOW, None)
    hook(User("u1", "a@x.org", "A", "learner", "active", NOW, None, None))
    for thread in threading.enumerate():
        if thread.name.startswith("provision-"):
            thread.join(5)


class FakePractice:
    def __init__(self, user_id="u1"):
        self.principal = principal(user_id)

    def for_exam(self, code):
        raise PracticeUnavailable(PREPARING)


def test_lab_service_runs_inside_the_guard():
    from oracle_lab.services.sql_lab import SqlLabService
    from oracle_lab.study.state import MemoryStateStore

    class Ready(FakePractice):
        def for_exam(self, code):
            return FakeDatabase()

    guard = RunGuard()
    lab = SqlLabService(MemoryStateStore(), Ready(), guard, lambda: NOW)
    with guard.run("u1"), pytest.raises(HttpError) as raised:
        lab.visualize("SELECT 1 FROM dual")
    assert raised.value.status == 409
    with pytest.raises(PracticeUnavailable):
        SqlLabService(MemoryStateStore(), FakePractice(), guard, lambda: NOW).schema()


def test_learner_without_a_practice_database_gets_503_on_every_sql_route(serve):
    import json

    from conftest import PASSWORD

    server = serve(stores=memory_stores())
    server.sign_in("admin@x.org")  # the first account is the admin
    learner = type(server)(server.port).sign_in("learner@x.org", PASSWORD)
    routes = (("/api/run", {"sql": "SELECT 1 FROM dual;"}), ("/api/visualize", {"sql": "SELECT 1 FROM dual"}),
              ("/api/schema", None), ("/api/reset-data", {}), ("/api/grade", {"id": content.LABS[0]["id"], "sql": "SELECT 1"}))
    for path, data in routes:
        status, _, body = learner(path, data)
        assert status == 503, (path, body)
        assert json.loads(body) == {"error": NOT_SET_UP, "practice": "unavailable"}


def test_practice_databases_are_built_only_when_used():
    from oracle_lab.services.context import UserContexts
    from oracle_lab.web.http import Request

    built = []
    contexts = UserContexts(memory_stores(), lambda p: built.append(p) or "practice")
    ctx = contexts(Request("GET", "/api/state", {}, principal=principal()))
    assert built == [] and ctx.state is not None
    assert ctx.practice == "practice" and ctx.practice == "practice" and built == [principal()]


def _join_provisioning_threads():
    for thread in threading.enumerate():
        if thread.name.startswith("provision-"):
            thread.join(5)


def _learner(stores, user_id="u1"):
    user = User(user_id, f"{user_id}@x.org", "A", "learner", "active", NOW, None, None)
    stores.users.add(user, Identity("password", user_id, user_id, "h"))
    return user


def _deletion(stores, provisioners):
    return AccountDeletion(stores, SessionManager(stores.sessions, lambda: NOW), AuditLog(stores.audit, lambda: NOW),
                           lambda user_id: drop_user_schemas(user_id, stores.schemas, provisioners))


def test_account_deleted_while_its_schema_is_created_leaves_nothing():
    stores = memory_stores()
    user = _learner(stores)
    provisioner = FakeProvisioner()
    provisioner.release = threading.Event()
    created = {}
    original_create, original_drop = provisioner.create, provisioner.drop
    provisioner.create = lambda name: (created.__setitem__(name, True), original_create(name))[1]
    provisioner.drop = lambda name: (created.pop(name, None), original_drop(name))[1]
    exists = lambda uid: stores.users.get(uid) is not None  # noqa: E731
    provisioning_hook({"default": provisioner}, stores.schemas, lambda: NOW, None, exists)(user)
    while not provisioner.calls:
        threading.Event().wait(0.01)
    deleter = threading.Thread(target=_deletion(stores, {"default": provisioner}).delete, args=("u1", "admin"))
    deleter.start()  # waits for the provisioning lock, then drops the new schema
    threading.Event().wait(0.1)
    provisioner.release.set()
    deleter.join(5)
    _join_provisioning_threads()
    assert created == {} and stores.schemas.for_user("u1") == [] and stores.users.get("u1") is None


def test_schema_finished_after_the_account_is_gone_is_dropped_without_a_record():
    stores = memory_stores()
    user = _learner(stores)
    provisioner = FakeProvisioner()
    provisioner.release = threading.Event()
    provisioning_hook({"default": provisioner}, stores.schemas, lambda: NOW, None,
                      lambda uid: stores.users.get(uid) is not None)(user)
    while not provisioner.calls:
        threading.Event().wait(0.01)
    stores.users.delete("u1")  # gone without waiting for the lock
    provisioner.release.set()
    _join_provisioning_threads()
    (create, name), drop = provisioner.calls
    assert create == "create" and drop == ("drop", name) and stores.schemas.get("u1", "default") is None


def test_sign_up_thread_started_after_deletion_creates_nothing():
    stores = memory_stores()
    user = _learner(stores)
    provisioner = FakeProvisioner()
    _deletion(stores, {"default": provisioner}).delete("u1", "admin")
    provisioning_hook({"default": provisioner}, stores.schemas, lambda: NOW, None,
                      lambda uid: stores.users.get(uid) is not None)(user)
    _join_provisioning_threads()
    assert provisioner.calls == [] and stores.schemas.for_user("u1") == []


def test_deletion_ends_sessions_before_dropping_schemas():
    stores = memory_stores()
    _learner(stores)
    sessions = SessionManager(stores.sessions, lambda: NOW)
    token, _ = sessions.start("u1", "ip", "ua")
    seen = []
    AccountDeletion(stores, sessions, AuditLog(stores.audit, lambda: NOW),
                    lambda uid: seen.append(sessions.resolve(token))).delete("u1", "admin")
    assert seen == [None]


def test_failed_drop_of_the_old_schema_is_audited():
    stores = memory_stores()
    stores.schemas.put(PracticeSchema("u1", "default", "OLL_UABCDEFGHIJ", "failed", NOW, "ORA-1"))
    provisioner = FakeProvisioner()
    provisioner.drop = lambda name: (_ for _ in ()).throw(OraError("ORA-03113: end-of-file"))
    practice(stores, {"default": provisioner}).provision("default")
    (event,) = stores.audit.recent(event="schema_drop_failed")
    assert event.detail["schema_name"] == "OLL_UABCDEFGHIJ" and event.outcome == "fail"


def test_failed_drop_on_deletion_keeps_that_record():
    stores = memory_stores()
    stores.schemas.put(PracticeSchema("u1", "default", "OLL_UAAAAAAAAAA", "ready", NOW))
    stores.schemas.put(PracticeSchema("u1", "23ai", "OLL_UBBBBBBBBBB", "ready", NOW))
    broken = FakeProvisioner()
    broken.drop = lambda name: (_ for _ in ()).throw(OraError("ORA-03113"))
    with pytest.raises(OraError):
        drop_user_schemas("u1", stores.schemas, {"default": FakeProvisioner(), "23ai": broken})
    assert [r.database_key for r in stores.schemas.for_user("u1")] == ["23ai"]


def test_request_provisioning_is_capped_app_wide():
    from oracle_lab.provisioning import practice as module

    stores = memory_stores()
    held = [module._request_slots.acquire(blocking=False) for _ in range(2)]
    try:
        assert held == [True, True]
        provisioner = FakeProvisioner()
        with pytest.raises(PracticeUnavailable, match="being prepared"):
            practice(stores, {"default": provisioner, "23ai": provisioner}).for_exam(EXAM_23AI)
        assert provisioner.calls == []
    finally:
        for _ in held:
            module._request_slots.release()
    assert practice(stores, {"default": FakeProvisioner(), "23ai": FakeProvisioner()}).for_exam(EXAM_23AI)


def test_each_hook_runs_even_when_one_fails(caplog):
    from oracle_lab.bootstrap import each_hook

    ran = []

    def broken(user):
        raise RuntimeError("legacy store down")

    each_hook(broken, ran.append)(User("u1", "a@x.org", "A", "learner", "active", NOW, None, None))
    assert [u.id for u in ran] == ["u1"] and "legacy store down" in caplog.text
