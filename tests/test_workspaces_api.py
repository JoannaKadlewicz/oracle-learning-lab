"""The workspace overview, a user's first pick, and admins managing workspace access and free plan limits."""

from __future__ import annotations

import json

import pytest

from conftest import Client
from oracle_lab import exams
from oracle_lab.access.models import WorkspaceAccess
from oracle_lab.accounts.memory import memory_stores


@pytest.fixture
def lab(serve):
    stores = memory_stores()
    server = serve(stores=stores)
    admin = server.sign_in("admin@x.org")  # the first account is the admin
    user = Client(server.port).sign_in("user@x.org")
    return stores, admin, user, stores.users.by_email("user@x.org").id


def body(response):
    return json.loads(response[2])


def levels(stores, uid):
    return {r.workspace: r.level for r in stores.access.for_user(uid)}


def test_overview_marks_levels_and_current(lab):
    stores, admin, user, uid = lab
    first = body(user("/api/workspaces"))
    assert first["current"] is None
    assert [w["code"] for w in first["workspaces"]] == list(exams.EXAMS)
    assert all(w["level"] == "none" and w["title"] and w["tile"] and w["logo"] == "oracle" for w in first["workspaces"])
    stores.access.put(WorkspaceAccess(uid, "1Z0-171", "member", uid, 1.0))
    after = body(user("/api/workspaces"))
    assert after["current"] == "1Z0-171"
    assert {w["code"]: w["level"] for w in after["workspaces"]} == {"1Z0-071": "none", "1Z0-171": "member"}
    assert body(admin("/api/workspaces"))["current"] == exams.DEFAULT_EXAM


def test_overview_carries_the_account_language_for_the_picker(lab):
    stores, _, user, uid = lab
    assert body(user("/api/workspaces"))["language"] is None
    with stores.states.for_user(uid).transaction() as state:
        state["settings"]["language"] = "pl"
    assert body(user("/api/workspaces"))["language"] == "pl"


def test_choose_once_grants_free_and_sets_default(lab):
    stores, _, user, uid = lab
    assert user("/api/workspaces/choose", {"workspace": "nope"})[0] == 400
    assert user("/api/workspaces/choose", {"workspace": "1Z0-171"})[0] == 200
    assert levels(stores, uid) == {"1Z0-171": "member"}
    assert stores.states.for_user(uid).load()["settings"]["exam"] == "1Z0-171"
    assert body(user("/api/progress"))["access"]["workspace"] == "1Z0-171"
    assert user("/api/workspaces/choose", {"workspace": "1Z0-071"})[0] == 403
    assert levels(stores, uid) == {"1Z0-171": "member"}


def test_admin_moves_a_users_single_workspace(lab):
    stores, admin, user, uid = lab
    user("/api/workspaces/choose", {"workspace": "1Z0-071"})
    assert admin("/api/admin/membership", {"user_id": uid, "workspace": "1Z0-171", "member": True})[0] == 200
    assert levels(stores, uid) == {"1Z0-171": "member"}


def test_admin_adds_and_removes_pro_workspaces(lab):
    stores, admin, user, uid = lab
    user("/api/workspaces/choose", {"workspace": "1Z0-071"})
    assert admin("/api/admin/role", {"user_id": uid, "role": "pro"})[0] == 200
    assert admin("/api/admin/membership", {"user_id": uid, "workspace": "1Z0-171", "member": True})[0] == 200
    assert levels(stores, uid) == {"1Z0-071": "member", "1Z0-171": "member"}
    row = next(u for u in body(admin("/api/admin/users"))["users"] if u["id"] == uid)
    assert row["role"] == "pro" and row["workspaces"] == ["1Z0-071", "1Z0-171"]
    for code in exams.EXAMS:
        admin("/api/admin/membership", {"user_id": uid, "workspace": code, "member": False})
    assert levels(stores, uid) == {} and body(user("/api/workspaces"))["current"] is None


def test_admin_membership_requests_are_validated(lab):
    stores, admin, user, uid = lab
    admin_id = stores.users.by_email("admin@x.org").id
    assert admin("/api/admin/membership", {"user_id": uid, "workspace": "nope", "member": True})[0] == 400
    assert admin("/api/admin/membership", {"user_id": uid, "workspace": "1Z0-071", "member": "yes"})[0] == 400
    assert admin("/api/admin/membership", {"user_id": admin_id, "workspace": "1Z0-071", "member": True})[0] == 400
    assert admin("/api/admin/membership", {"user_id": "nobody", "workspace": "1Z0-071", "member": True})[0] == 404
    assert user("/api/admin/membership", {"user_id": uid, "workspace": "1Z0-071", "member": True})[0] == 404


def test_access_changes_are_audited(lab):
    stores, admin, user, uid = lab
    user("/api/workspaces/choose", {"workspace": "1Z0-071"})
    admin("/api/admin/membership", {"user_id": uid, "workspace": "1Z0-171", "member": True})
    events = {e.event: e for e in stores.audit.recent(50)}
    assert events["workspace_chosen"].detail["workspace"] == "1Z0-071"
    changed = events["workspace_access_changed"].detail
    assert (changed["target"], changed["workspace"], changed["member"]) == (uid, "1Z0-171", True)


