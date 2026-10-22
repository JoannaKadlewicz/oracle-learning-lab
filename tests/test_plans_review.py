"""Fixes from the plans review: each test reproduces one finding."""

from __future__ import annotations

import json

import pytest

from conftest import NOW, PASSWORD, Client, settings_for
from oracle_lab import content
from oracle_lab.access.migration import migrate_plans
from oracle_lab.access.models import WorkspaceAccess
from oracle_lab.accounts.memory import memory_stores
from oracle_lab.auth.audit import AuditLog
from oracle_lab.auth.guest import adopt_guest
from oracle_lab.auth.models import Identity, User
from test_guest import start_guest


def _user(stores, uid, role):
    user = User(uid, f"{uid}@x.org", uid, role, "active", 1.0, None, None)
    stores.users.add(user, Identity("password", user.email, uid, "h"))


def test_a_failed_pro_promotion_is_retried(monkeypatch):
    stores = memory_stores()
    _user(stores, "u1", "user")
    stores.access.put(WorkspaceAccess("u1", "1Z0-171", "subscribed", "a", 1.0))
    real = stores.users.set_role
    monkeypatch.setattr(stores.users, "set_role", lambda *a: (_ for _ in ()).throw(RuntimeError("db down")))
    audit = AuditLog(stores.audit, lambda: NOW)
    migrate_plans(stores, lambda: NOW, audit)
    monkeypatch.setattr(stores.users, "set_role", real)
    migrate_plans(stores, lambda: NOW, audit)
    assert stores.users.get("u1").role == "pro"


@pytest.fixture
def lab(serve):
    stores = memory_stores()
    server = serve(stores=stores)
    admin = server.sign_in("admin@x.org")
    user = Client(server.port).sign_in("user@x.org")
    uid = stores.users.by_email("user@x.org").id
    stores.access.put(WorkspaceAccess(uid, "1Z0-071", "member", "a", 1.0))
    return stores, admin, user, uid, server


def test_an_exercise_that_did_not_run_is_not_counted(lab):
    stores, _, user, uid, _ = lab
    assert user("/api/grade", {"id": content.LABS[0]["id"], "sql": "SELECT 1 FROM dual"})[0] == 503  # no practice db
    assert stores.states.for_user(uid).load().get("usage", {}).get("exercises", 0) == 0


def test_graded_runs_are_counted_and_limited(lab, monkeypatch):
    from oracle_lab.web.controllers import sql_lab

    stores, _, user, uid, _ = lab
    monkeypatch.setattr(sql_lab.ExerciseService, "grade", lambda self, *a: {"passed": False, "feedback": []})
    lab_id = content.LABS[0]["id"]
    for _ in range(10):
        assert user("/api/grade", {"id": lab_id, "sql": "SELECT 1 FROM dual"})[0] == 200
    status, _, raw = user("/api/grade", {"id": lab_id, "sql": "SELECT 1 FROM dual"})
    assert status == 403 and json.loads(raw)["limit"] == "exercises"
    monkeypatch.setattr(sql_lab.ExerciseService, "grade", lambda self, *a: {"passed": False, "error": "ORA-00942"})
    stores.settings.set(f"limits:{uid}", json.dumps({"exercises": 20}))
    user("/api/grade", {"id": lab_id, "sql": "SELECT nope"})
    assert stores.states.for_user(uid).load()["usage"]["exercises"] == 10  # SQL that did not run is free


def test_an_odd_exercise_id_is_a_client_error(lab):
    _, _, user, _, _ = lab
    assert user("/api/grade", {"id": [1], "sql": "SELECT 1"})[0] in (400, 404)


def test_a_guest_cannot_change_credentials_or_link_google(serve):
    server = serve(stores=memory_stores())
    server.sign_in("admin@x.org")
    guest = start_guest(Client(server.port))
    assert guest("/api/account/set-password", {"password": PASSWORD})[0] == 403
    assert guest("/api/account/delete", {})[0] == 403
    assert guest("/auth/google/start?intent=link")[0] in (403, 404)


def test_downgrading_pro_keeps_one_workspace(lab):
    stores, admin, user, uid, _ = lab
    admin("/api/admin/role", {"user_id": uid, "role": "pro"})
    stores.access.put(WorkspaceAccess(uid, "1Z0-171", "member", "a", 1.0))
    assert user("/api/settings", {"exam": "1Z0-171"})[0] == 200
    assert admin("/api/admin/role", {"user_id": uid, "role": "user"})[0] == 200
    assert [r.workspace for r in stores.access.for_user(uid)] == ["1Z0-171"]  # the one in use stays


def test_adopting_a_guest_never_overwrites_existing_progress():
    stores = memory_stores()
    _user(stores, "g1", "guest")
    _user(stores, "u1", "user")
    with stores.states.for_user("g1").transaction() as s:
        s["attempts"]["q-guest"] = [{"t": 1.0}]
    with stores.states.for_user("u1").transaction() as s:
        s["attempts"]["q-imported"] = [{"t": 1.0}]
    adopt_guest(stores, "g1", "u1")
    assert "q-imported" in stores.states.for_user("u1").load()["attempts"]


def test_no_guests_while_registration_is_closed(serve, tmp_path):
    server = serve(settings_for(tmp_path, STUDY_REGISTRATION="closed"), stores=memory_stores())
    assert server("/api/auth/guest", {}, headers={"Origin": server.origin})[0] == 403
    assert json.loads(server("/api/auth/config")[2])["guests"] is False
