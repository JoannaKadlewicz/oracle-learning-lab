"""Account plans: what guest, user, pro and admin may do, their limits, per-account overrides, and the migration
from per-workspace free/subscribed access."""

from __future__ import annotations

import pytest

from oracle_lab import exams
from oracle_lab.access import limits, plans
from oracle_lab.access.migration import migrate_plans
from oracle_lab.access.models import WorkspaceAccess
from oracle_lab.access.plans import Limits, PlanDefaults
from oracle_lab.accounts.memory import memory_stores
from oracle_lab.auth.audit import AuditLog
from oracle_lab.auth.models import Identity, User
from oracle_lab.study import engine

NOW = 1_800_000_000.0


def test_plan_defaults_and_override_win():
    settings = memory_stores().settings
    assert plans.limits_for("guest", "g1", settings) == Limits(questions=20, cards=20, exercises=0, topics=2)
    assert plans.limits_for("user", "u1", settings) == Limits(questions=None, cards=None, exercises=10, topics=None)
    assert plans.limits_for("pro", "p1", settings) == Limits(None, None, None, None)
    plans.set_override(settings, "g1", {"questions": 5})
    plans.set_override(settings, "u1", {"exercises": 50, "questions": 3})
    assert plans.limits_for("guest", "g1", settings).questions == 5
    assert plans.limits_for("user", "u1", settings) == Limits(questions=3, cards=None, exercises=50, topics=None)
    plans.set_override(settings, "u1", None)
    assert plans.limits_for("user", "u1", settings).exercises == 10 and plans.override(settings, "u1") == {}


def test_plan_defaults_round_trip_and_validation():
    settings = memory_stores().settings
    PlanDefaults(guest_questions=7, guest_cards=8, guest_topics=3, user_exercises=4).save(settings)
    assert PlanDefaults.load(settings) == PlanDefaults(7, 8, 3, 4)
    with pytest.raises(ValueError):
        PlanDefaults.parse({"guest_topics": 16})
    with pytest.raises(ValueError):
        plans.set_override(settings, "u1", {"questions": -1})


def test_can_by_plan():
    assert plans.can("user", "exercises") and plans.can("user", "mock") and not plans.can("user", "sql_lab")
    assert not plans.can("guest", "exercises") and not plans.can("guest", "mock") and not plans.can("guest", "sql_lab")
    assert all(plans.can("pro", f) and plans.can("admin", f) for f in plans.FEATURES)
    assert not plans.can("user", "many_workspaces") and plans.can("pro", "many_workspaces")


def _add(stores, uid, role, rows=()):
    user = User(uid, f"{uid}@x.org", uid, role, "active", 1.0, None, None)
    stores.users.add(user, Identity("password", user.email, uid, "h"))
    for code, level in rows:
        stores.access.put(WorkspaceAccess(uid, code, level, "a", 1.0))


def _run(stores):
    return migrate_plans(stores, lambda: NOW, AuditLog(stores.audit, lambda: NOW))


def test_subscribed_user_becomes_pro_and_keeps_memberships():
    stores = memory_stores()
    _add(stores, "u1", "user", [("1Z0-071", "free"), ("1Z0-171", "subscribed")])
    assert _run(stores) == 1
    assert stores.users.get("u1").role == "pro"
    assert {(r.workspace, r.level) for r in stores.access.for_user("u1")} == {("1Z0-071", "member"), ("1Z0-171", "member")}


def test_free_user_stays_user_and_second_run_changes_nothing():
    stores = memory_stores()
    _add(stores, "u1", "user", [("1Z0-071", "free")])
    _add(stores, "a1", "admin")
    assert _run(stores) == 1
    assert stores.users.get("u1").role == "user" and [r.level for r in stores.access.for_user("u1")] == ["member"]
    assert _run(stores) == 0 and stores.users.get("a1").role == "admin"


def test_used_today_counts_exercises_from_the_usage_counter():
    state = {}
    for _ in range(3):
        limits.count_use(state, "exercises", NOW)
    assert limits.used_today(state, NOW)["exercises"] == 3
    assert limits.used_today(state, NOW + 2 * engine.DAY)["exercises"] == 0


def test_a_solved_exercise_counts_once_a_day():
    state = {}
    assert limits.count_solved(state, "lab-a", NOW) and limits.count_solved(state, "lab-b", NOW)
    assert not limits.count_solved(state, "lab-a", NOW)  # solving it again the same day is free
    assert limits.used_today(state, NOW)["exercises"] == 2
    assert limits.count_solved(state, "lab-a", NOW + engine.DAY)  # a new day counts it again
    assert limits.used_today(state, NOW + engine.DAY)["exercises"] == 1


def test_membership_policy():
    from oracle_lab.access import policy

    rows = [WorkspaceAccess("u1", "1Z0-071", "member", "u1", 1.0)]
    assert policy.level_in("user", rows, "1Z0-071") == "member" and policy.level_in("user", rows, "1Z0-171") == "none"
    assert policy.usable("admin", []) == list(exams.EXAMS)
