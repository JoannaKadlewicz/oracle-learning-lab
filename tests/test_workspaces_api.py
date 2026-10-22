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
    assert all(w["level"] == "none" and w["title"] and w["tile"] for w in first["workspaces"])
    stores.access.put(WorkspaceAccess(uid, "1Z0-171", "free", uid, 1.0))
    after = body(user("/api/workspaces"))
    assert after["current"] == "1Z0-171"
    assert {w["code"]: w["level"] for w in after["workspaces"]} == {"1Z0-071": "none", "1Z0-171": "free"}
    assert body(admin("/api/workspaces"))["current"] == exams.DEFAULT_EXAM


def test_choose_once_grants_free_and_sets_default(lab):
    stores, _, user, uid = lab
    assert user("/api/workspaces/choose", {"workspace": "nope"})[0] == 400
    assert user("/api/workspaces/choose", {"workspace": "1Z0-171"})[0] == 200
    assert levels(stores, uid) == {"1Z0-171": "free"}
    assert stores.states.for_user(uid).load()["settings"]["exam"] == "1Z0-171"
    assert body(user("/api/progress"))["access"]["workspace"] == "1Z0-171"
    assert user("/api/workspaces/choose", {"workspace": "1Z0-071"})[0] == 403
    assert levels(stores, uid) == {"1Z0-171": "free"}


def test_admin_moves_free_access_keeps_one_free_row(lab):
    stores, admin, user, uid = lab
    user("/api/workspaces/choose", {"workspace": "1Z0-071"})
    assert admin("/api/admin/workspace-access", {"user_id": uid, "workspace": "1Z0-171", "level": "free"})[0] == 200
    assert levels(stores, uid) == {"1Z0-171": "free"}


def test_admin_subscribes_and_revokes(lab):
    stores, admin, user, uid = lab
    user("/api/workspaces/choose", {"workspace": "1Z0-071"})
    assert admin("/api/admin/workspace-access", {"user_id": uid, "workspace": "1Z0-171", "level": "subscribed"})[0] == 200
    assert levels(stores, uid) == {"1Z0-071": "free", "1Z0-171": "subscribed"}
    row = next(u for u in body(admin("/api/admin/users"))["users"] if u["id"] == uid)
    assert row["workspaces"] == [{"code": "1Z0-071", "level": "free"}, {"code": "1Z0-171", "level": "subscribed"}]
    for code in exams.EXAMS:
        admin("/api/admin/workspace-access", {"user_id": uid, "workspace": code, "level": "none"})
    assert levels(stores, uid) == {} and body(user("/api/workspaces"))["current"] is None


def test_admin_access_requests_are_validated(lab):
    stores, admin, user, uid = lab
    admin_id = stores.users.by_email("admin@x.org").id
    assert admin("/api/admin/workspace-access", {"user_id": uid, "workspace": "nope", "level": "free"})[0] == 400
    assert admin("/api/admin/workspace-access", {"user_id": uid, "workspace": "1Z0-071", "level": "gold"})[0] == 400
    assert admin("/api/admin/workspace-access", {"user_id": admin_id, "workspace": "1Z0-071", "level": "free"})[0] == 400
    assert admin("/api/admin/workspace-access", {"user_id": "nobody", "workspace": "1Z0-071", "level": "free"})[0] == 404
    assert user("/api/admin/workspace-access", {"user_id": uid, "workspace": "1Z0-071", "level": "subscribed"})[0] == 404


def test_admin_settings_round_trip_free_limits(lab):
    _, admin, _, _ = lab
    assert body(admin("/api/admin/settings"))["free_limits"] == {"questions": 20, "cards": 20, "topics": 2}
    changed = body(admin("/api/admin/settings", {"free_limits": {"questions": 10, "cards": 5, "topics": 3}}))
    assert changed["free_limits"] == {"questions": 10, "cards": 5, "topics": 3}
    assert admin("/api/admin/settings", {"free_limits": {"questions": -1, "cards": 5, "topics": 3}})[0] == 400


def test_access_changes_are_audited(lab):
    stores, admin, user, uid = lab
    user("/api/workspaces/choose", {"workspace": "1Z0-071"})
    admin("/api/admin/workspace-access", {"user_id": uid, "workspace": "1Z0-171", "level": "subscribed"})
    events = {e.event: e for e in stores.audit.recent(50)}
    assert events["workspace_chosen"].detail["workspace"] == "1Z0-071"
    changed = events["workspace_access_changed"].detail
    assert (changed["target"], changed["workspace"], changed["level"]) == (uid, "1Z0-171", "subscribed")
