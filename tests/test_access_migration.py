"""The one-time move from account roles (free / learner) to workspace access."""

from __future__ import annotations

from oracle_lab import exams
from oracle_lab.access.migration import migrate_roles
from oracle_lab.accounts.memory import memory_stores
from oracle_lab.auth.audit import AuditLog
from oracle_lab.auth.models import Identity, User

NOW = 1_800_000_000.0


def add(stores, uid, role, exam=None):
    user = User(uid, f"{uid}@x.org", uid, role, "active", 1.0, None, None)
    stores.users.add(user, Identity("password", user.email, uid, "h"))
    if exam:
        with stores.states.for_user(uid).transaction() as state:
            state["settings"]["exam"] = exam
    return user


def run(stores):
    return migrate_roles(stores, lambda: NOW, AuditLog(stores.audit, lambda: NOW))


def levels(stores, uid):
    return {r.workspace: r.level for r in stores.access.for_user(uid)}


def test_learner_becomes_user_subscribed_everywhere():
    stores = memory_stores()
    add(stores, "l1", "learner")
    assert run(stores) == 1
    assert stores.users.get("l1").role == "user"
    assert levels(stores, "l1") == {code: "subscribed" for code in exams.EXAMS}
    assert all(r.granted_by == "migration" for r in stores.access.for_user("l1"))


def test_free_becomes_user_free_in_saved_exam():
    stores = memory_stores()
    add(stores, "f1", "free", exam="1Z0-171")
    add(stores, "f2", "free")
    run(stores)
    assert stores.users.get("f1").role == "user" and levels(stores, "f1") == {"1Z0-171": "free"}
    assert levels(stores, "f2") == {exams.DEFAULT_EXAM: "free"}


def test_admin_untouched_and_second_run_changes_nothing():
    stores = memory_stores()
    add(stores, "a1", "admin")
    add(stores, "l1", "learner")
    run(stores)
    assert stores.users.get("a1").role == "admin" and levels(stores, "a1") == {}
    assert run(stores) == 0
    assert levels(stores, "l1") == {code: "subscribed" for code in exams.EXAMS}


def test_one_broken_account_does_not_stop_the_others(monkeypatch):
    from oracle_lab.access import migration

    stores = memory_stores()
    add(stores, "f1", "free")
    add(stores, "l1", "learner")
    real = migration.exam_code
    monkeypatch.setattr(migration, "exam_code", lambda state: (_ for _ in ()).throw(ValueError("corrupt")))
    assert run(stores) == 1  # f1 failed, l1 moved
    assert stores.users.get("l1").role == "user" and stores.users.get("f1").role == "free"
    monkeypatch.setattr(migration, "exam_code", real)
    assert run(stores) == 1 and stores.users.get("f1").role == "user"


def test_a_learner_not_migrated_yet_keeps_everything():
    from oracle_lab.access import policy

    assert policy.usable("learner", []) == list(exams.EXAMS)
    assert all(policy.level_in("learner", [], code) == "member" for code in exams.EXAMS)
