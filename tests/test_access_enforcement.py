"""The server enforces workspaces: no study without one, the free plan's daily limits, and subscription-only
features (SQL, mock exams, later lessons)."""

from __future__ import annotations

import json

import pytest

from conftest import NOW, Client
from oracle_lab import content
from oracle_lab.access import limits
from oracle_lab.access.models import WorkspaceAccess
from oracle_lab.accounts.memory import memory_stores


@pytest.fixture
def lab(serve):
    """(stores, admin client, user client, user id): the first account is the admin."""
    stores = memory_stores()
    server = serve(stores=stores)
    admin = server.sign_in("admin@x.org")
    user = Client(server.port).sign_in("user@x.org")
    return stores, admin, user, stores.users.by_email("user@x.org").id


def grant(stores, uid, workspace, level):
    stores.access.put(WorkspaceAccess(uid, workspace, level, "admin", 1.0))


def body(response):
    return json.loads(response[2])


def test_user_without_access_gets_409_on_study_routes(lab):
    _, _, user, _ = lab
    for path in ("/api/progress", "/api/content"):
        status, _, raw = user(path)
        assert (status, json.loads(raw)) == (409, {"error": "Choose a workspace first.", "workspace": "required"})


def test_admin_without_rows_gets_no_409(lab):
    _, admin, _, _ = lab
    assert admin("/api/progress")[0] == 200 and admin("/api/content")[0] == 200


def test_free_user_21st_answer_is_refused(lab):
    stores, _, user, uid = lab
    grant(stores, uid, "1Z0-071", "free")
    question = content.QUESTIONS[0]
    for _ in range(20):
        assert user("/api/attempt", {"id": question["id"], "chosen": question["answer"]})[0] == 200
    status, _, raw = user("/api/attempt", {"id": question["id"], "chosen": question["answer"]})
    assert status == 403 and json.loads(raw)["limit"] == "questions"
    card = content.FLASHCARDS[0]["id"]
    for _ in range(20):
        assert user("/api/card", {"id": card, "rating": "good"})[0] == 200
    status, _, raw = user("/api/card", {"id": card, "rating": "good"})
    assert status == 403 and json.loads(raw)["limit"] == "cards"
    assert body(user("/api/progress"))["access"]["used"] == {"questions": 20, "cards": 20}


@pytest.mark.parametrize("method,path", [("POST", "/api/run"), ("POST", "/api/visualize"), ("GET", "/api/schema"),
                                         ("POST", "/api/reset-data"), ("POST", "/api/grade"), ("POST", "/api/mock/start")])
def test_free_user_cannot_run_sql_or_start_a_mock(lab, method, path):
    stores, _, user, uid = lab
    grant(stores, uid, "1Z0-071", "free")
    status, _, raw = user(path, {"sql": "select 1 from dual", "id": "x", "count": 10} if method == "POST" else None)
    assert status == 403 and json.loads(raw)["error"] == "This needs a subscription to the workspace."


def test_free_user_reads_only_the_first_lessons(lab):
    stores, _, user, uid = lab
    grant(stores, uid, "1Z0-071", "free")
    notes = {n["path"]: n.get("locked", False) for n in body(user("/api/notes"))}
    assert notes["topics/01-basic-select/notes.md"] is False and notes["topics/03-single-row-functions/notes.md"] is True
    assert user("/api/note?path=topics/01-basic-select/notes.md")[0] == 200
    assert user("/api/note?path=topics/03-single-row-functions/notes.md")[0] == 403


def test_switching_to_an_unusable_workspace_is_403(lab):
    stores, _, user, uid = lab
    grant(stores, uid, "1Z0-071", "free")
    assert user("/api/settings", {"exam": "1Z0-171"})[0] == 403
    grant(stores, uid, "1Z0-171", "subscribed")
    assert user("/api/settings", {"exam": "1Z0-171"})[0] == 200


def test_saved_exam_without_access_falls_back(lab):
    stores, _, user, uid = lab
    with stores.states.for_user(uid).transaction() as state:
        state["settings"]["exam"] = "1Z0-171"
    grant(stores, uid, "1Z0-071", "free")
    access = body(user("/api/progress"))["access"]
    assert access["workspace"] == "1Z0-071" and access["level"] == "free"
    assert access["limits"] == {"questions": 20, "cards": 20, "topics": 2}


def test_subscribed_user_has_no_limits(lab):
    stores, _, user, uid = lab
    grant(stores, uid, "1Z0-071", "subscribed")
    question = content.QUESTIONS[0]
    for _ in range(25):
        assert user("/api/attempt", {"id": question["id"], "chosen": question["answer"]})[0] == 200
    access = body(user("/api/progress"))["access"]
    assert access["level"] == "subscribed" and access["limits"] is None


def test_free_plan_session_fits_the_daily_allowance(lab):
    stores, _, user, uid = lab
    grant(stores, uid, "1Z0-071", "free")
    stores.settings.set("free_questions_per_day", "7")
    stores.settings.set("free_cards_per_day", "2")
    with stores.states.for_user(uid).transaction() as state:
        state["settings"]["daily_minutes"] = 120
    plan = body(user("/api/progress"))["progress"]["plan"]
    assert len(plan["questions"]) <= 7 and len(plan["cards"]) <= 2


def test_used_today_matches_the_limits_module(lab):
    stores, _, user, uid = lab
    grant(stores, uid, "1Z0-071", "free")
    question = content.QUESTIONS[0]
    user("/api/attempt", {"id": question["id"], "chosen": question["answer"]})
    assert limits.used_today(stores.states.for_user(uid).load(), NOW)["questions"] == 1
