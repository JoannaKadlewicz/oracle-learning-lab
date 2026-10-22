"""The server enforces plans: no study without a workspace, a guest's daily limits and no SQL at all, a user's
daily graded exercises and no SQL lab, pro for everything; per-account limits override the plan."""

from __future__ import annotations

import json

import pytest

from conftest import Client
from oracle_lab import content
from oracle_lab.access import plans
from oracle_lab.access.models import WorkspaceAccess
from oracle_lab.accounts.memory import memory_stores

SQL_LAB = [("POST", "/api/run"), ("POST", "/api/visualize"), ("GET", "/api/schema"), ("POST", "/api/reset-data")]


@pytest.fixture
def lab(serve):
    """(stores, admin client, user client, user id): the first account is the admin."""
    stores = memory_stores()
    server = serve(stores=stores)
    admin = server.sign_in("admin@x.org")
    user = Client(server.port).sign_in("user@x.org")
    return stores, admin, user, stores.users.by_email("user@x.org").id


def member(stores, uid, workspace="1Z0-071"):
    stores.access.put(WorkspaceAccess(uid, workspace, "member", "admin", 1.0))


def as_plan(stores, uid, role, workspace="1Z0-071"):
    stores.users.set_role(uid, role)
    member(stores, uid, workspace)


def body(response):
    return json.loads(response[2])


def answer(user):
    question = content.QUESTIONS[0]
    return user("/api/attempt", {"id": question["id"], "chosen": question["answer"]})


def grade(user):
    lab = content.LABS[0]
    return user("/api/grade", {"id": lab["id"], "sql": "SELECT 1 FROM dual"})


def test_user_without_access_gets_409_on_study_routes(lab):
    _, _, user, _ = lab
    for path in ("/api/progress", "/api/content"):
        status, _, raw = user(path)
        assert (status, json.loads(raw)) == (409, {"error": "Choose a workspace first.", "workspace": "required"})


def test_admin_without_rows_gets_no_409(lab):
    _, admin, _, _ = lab
    assert admin("/api/progress")[0] == 200 and admin("/api/content")[0] == 200


def test_guest_limits_and_user_unlimited_quizzes(lab):
    stores, _, user, uid = lab
    as_plan(stores, uid, "guest")
    for _ in range(20):
        assert answer(user)[0] == 200
    status, _, raw = answer(user)
    assert status == 403 and json.loads(raw)["limit"] == "questions"
    card = content.FLASHCARDS[0]["id"]
    for _ in range(20):
        assert user("/api/card", {"id": card, "rating": "good"})[0] == 200
    assert body(user("/api/card", {"id": card, "rating": "good"}))["limit"] == "cards"
    stores.users.set_role(uid, "user")
    assert answer(user)[0] == 200 and user("/api/card", {"id": card, "rating": "good"})[0] == 200


@pytest.mark.parametrize("method,path", [*SQL_LAB, ("POST", "/api/grade")])
def test_guest_cannot_reach_any_sql(lab, method, path):
    stores, _, user, uid = lab
    as_plan(stores, uid, "guest")
    status, _, raw = user(path, {"sql": "select 1 from dual", "id": content.LABS[0]["id"]} if method == "POST" else None)
    assert status == 403 and json.loads(raw)["error"] == "Create a free account to use this."
    assert stores.schemas.for_user(uid) == []


@pytest.mark.parametrize("method,path", SQL_LAB)
def test_user_cannot_use_the_sql_lab_but_pro_can(lab, method, path):
    stores, _, user, uid = lab
    as_plan(stores, uid, "user")
    data = {"sql": "select 1 from dual"} if method == "POST" else None
    status, _, raw = user(path, data)
    assert status == 403 and json.loads(raw)["error"] == "This needs the Pro plan."
    stores.users.set_role(uid, "pro")
    assert user(path, data)[0] != 403  # 503 here: this test server has no practice database


@pytest.fixture
def graded(monkeypatch):
    """Grading answers at once (this test server has no practice database); the count is what is tested."""
    from oracle_lab.web.controllers import sql_lab

    monkeypatch.setattr(sql_lab.ExerciseService, "grade", lambda self, *a: {"passed": False, "feedback": []})


def test_user_gets_ten_graded_exercises_a_day(lab, graded):
    stores, _, user, uid = lab
    as_plan(stores, uid, "user")
    for _ in range(10):
        assert grade(user)[0] == 200
    status, _, raw = grade(user)
    assert status == 403 and json.loads(raw)["limit"] == "exercises"
    assert user("/api/reset-progress", {})[0] == 200
    assert grade(user)[0] == 403
    assert body(user("/api/progress"))["access"]["used"]["exercises"] == 10


def test_override_unlocks_more_for_one_account(lab, graded):
    stores, _, user, uid = lab
    as_plan(stores, uid, "user")
    plans.set_override(stores.settings, uid, {"exercises": 1})
    assert grade(user)[0] != 403 and grade(user)[0] == 403
    plans.set_override(stores.settings, uid, {"exercises": 3})
    assert grade(user)[0] != 403


def test_user_can_start_a_mock_guest_cannot(lab):
    stores, _, user, uid = lab
    as_plan(stores, uid, "guest")
    assert user("/api/mock/start", {"count": 2, "minutes": 5})[0] == 403
    stores.users.set_role(uid, "user")
    assert user("/api/mock/start", {"count": 2, "minutes": 5})[0] == 200


def test_guest_reads_first_lessons_user_reads_all(lab):
    stores, _, user, uid = lab
    as_plan(stores, uid, "guest")
    notes = {n["path"]: n["locked"] for n in body(user("/api/notes"))}
    assert notes["topics/01-basic-select/notes.md"] is False and notes["topics/03-single-row-functions/notes.md"] is True
    assert user("/api/note?path=topics/03-single-row-functions/notes.md")[0] == 403
    stores.users.set_role(uid, "user")
    assert user("/api/note?path=topics/03-single-row-functions/notes.md")[0] == 200


def test_switching_to_a_workspace_without_membership_is_403(lab):
    stores, _, user, uid = lab
    as_plan(stores, uid, "user")
    assert user("/api/settings", {"exam": "1Z0-171"})[0] == 403
    member(stores, uid, "1Z0-171")
    assert user("/api/settings", {"exam": "1Z0-171"})[0] == 200


def test_saved_exam_without_access_falls_back(lab):
    stores, _, user, uid = lab
    with stores.states.for_user(uid).transaction() as state:
        state["settings"]["exam"] = "1Z0-171"
    as_plan(stores, uid, "guest")
    access = body(user("/api/progress"))["access"]
    assert access["workspace"] == "1Z0-071" and access["plan"] == "guest"
    assert access["limits"] == {"questions": 20, "cards": 20, "exercises": 0, "topics": 2}


def test_switching_returns_the_new_workspaces_access(lab):
    stores, _, user, uid = lab
    as_plan(stores, uid, "pro")
    member(stores, uid, "1Z0-171")
    switched = body(user("/api/settings", {"exam": "1Z0-171"}))
    assert switched["access"]["workspace"] == "1Z0-171" and switched["progress"]["exam"] == "1Z0-171"


def test_resetting_progress_keeps_todays_usage(lab):
    stores, _, user, uid = lab
    as_plan(stores, uid, "guest")
    plans.set_override(stores.settings, uid, {"questions": 2})
    for _ in range(2):
        assert answer(user)[0] == 200
    assert user("/api/reset-progress", {})[0] == 200
    status, _, raw = answer(user)
    assert status == 403 and json.loads(raw)["limit"] == "questions"


def test_guest_session_fits_the_daily_allowance(lab):
    stores, _, user, uid = lab
    as_plan(stores, uid, "guest")
    plans.set_override(stores.settings, uid, {"questions": 7, "cards": 2})
    with stores.states.for_user(uid).transaction() as state:
        state["settings"]["daily_minutes"] = 120
    plan = body(user("/api/progress"))["progress"]["plan"]
    assert len(plan["questions"]) <= 7 and len(plan["cards"]) <= 2
