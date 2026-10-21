"""The HTTP layer end to end over a real socket: health check, routing, errors (no database needed).
Every test signs in first (conftest.Client.sign_in); the login itself is covered by test_auth_web.py."""

import json

from conftest import Client, settings_for
from oracle_lab import content
from oracle_lab.accounts.memory import memory_stores


def test_health_check_needs_no_login(serve):
    status, _, body = serve()("/healthz")
    assert (status, json.loads(body)) == (200, {"ok": True})


def test_api_calls_need_a_login(serve):
    http = serve()
    assert http("/api/state")[0] == 401
    assert http.sign_in()("/api/state")[0] == 200


def test_personal_notes_are_kept_in_the_users_store(serve):
    stores = memory_stores()
    http = serve(stores=stores).sign_in()
    status, _, body = http("/api/notes/save", data={"title": "Joins", "sql": "SELECT 1 FROM dual;"})
    path = json.loads(body)["path"]
    assert status == 200 and path.startswith("personal/")
    user = stores.users.by_email("learner@example.org")
    assert "SELECT 1 FROM dual;" in stores.notes.for_user(user.id).read(path.removeprefix("personal/"))
    assert path in {n["path"] for n in json.loads(http("/api/notes")[2])}
    assert "SELECT 1 FROM dual;" in json.loads(http(f"/api/note?path={path}")[2])["text"]
    assert http("/api/note?path=../../etc/passwd")[0] == 404


def test_answers_are_saved_and_progress_is_returned(serve):
    stores = memory_stores()
    http = serve(stores=stores).sign_in()
    question = content.QUESTIONS[0]
    status, _, body = http("/api/attempt", data={"id": question["id"], "chosen": question["answer"]})
    assert status == 200 and json.loads(body)["progress"]["exam"] == content.DEFAULT_EXAM
    store = stores.states.for_user(stores.users.by_email("learner@example.org").id)
    assert store.load()["attempts"][question["id"]][0]["correct"] is True


def test_invalid_input_is_a_client_error(serve, tmp_path):
    http = serve(settings_for(tmp_path)).sign_in()
    assert http("/api/attempt", data={"id": "no-such-question"})[0] == 404
    assert http("/api/settings", data={"daily_minutes": 0})[0] == 400
    assert http("/api/settings", data=b"{not json")[0] == 400
    assert http("/api/mock?id=missing")[0] == 404
    assert http("/api/mock/teleport", data={})[0] == 404
    assert http("/api/no-such-endpoint", data={})[0] == 404


def test_cross_origin_posts_are_refused(serve, tmp_path):
    http = serve(settings_for(tmp_path)).sign_in()
    assert http("/api/reset-progress", data={}, headers={"Origin": "https://evil.example"})[0] == 403


def test_front_end_routes_get_the_app_shell_and_missing_assets_a_404(serve, tmp_path):
    http = serve(settings_for(tmp_path)).sign_in()
    status, headers, body = http("/quiz")
    assert status == 200 and headers["Content-Type"].startswith("text/html") and b"<html" in body.lower()
    assert http("/js/no-such-file.js")[0] == 404
    assert http("/../../pyproject.toml")[0] in (200, 404)  # never outside the static dir
    assert b"[project]" not in http("/../../pyproject.toml")[2]


def test_mock_exam_round_trip(serve, tmp_path):
    http = serve(settings_for(tmp_path)).sign_in()
    status, _, body = http("/api/mock/start", data={"count": 2, "minutes": 5})
    mock = json.loads(body)["mock"]
    assert status == 200 and len(mock["items"]) == 2
    answer = {"mock_id": mock["id"], "id": mock["items"][0], "chosen": [0]}
    assert json.loads(http("/api/mock/answer", data=answer)[2]) == {"ok": True}
    report = json.loads(http("/api/mock/submit", data={"mock_id": mock["id"]})[2])["report"]
    assert report["score"][1] == 2


def test_cross_site_fetches_are_refused(serve):
    http = serve().sign_in()
    assert http("/api/reset-progress", data={}, headers={"Sec-Fetch-Site": "cross-site"})[0] == 403
    assert http("/api/reset-progress", data={}, headers={"Sec-Fetch-Site": "same-origin"})[0] == 200


def test_progress_reports_sql_available_for_learners_and_admins(serve):
    http = serve()
    admin = http.sign_in("admin@example.org")  # the first account is the admin
    learner = Client(http.port).sign_in("learner@example.org")
    assert json.loads(admin("/api/progress")[2])["sql_available"] is True
    assert json.loads(learner("/api/progress")[2])["sql_available"] is False


def test_content_payload_has_engine_and_exam_facts(serve):
    http = serve().sign_in()
    body = json.loads(http("/api/content")[2])
    assert body["engine"] == {"name": "oracle", "label": "Oracle", "editor_mode": "text/x-plsql"}
    assert list(body["exams"]) == ["1Z0-071", "1Z0-171"]
    assert body["exam"]["code"] == "1Z0-071" and body["exam"]["product"] == "Oracle"
    assert [n["path"] for n in body["home_notes"]] == ["docs/exam-guide-2026.md", "docs/cheat-sheet.md"]


def test_progress_comes_in_the_language_of_the_request(serve):
    http = serve().sign_in()
    english = json.loads(http("/api/progress")[2])["progress"]
    polish = json.loads(http("/api/progress", headers={"X-Language": "pl"})[2])["progress"]
    assert english["badges"][0]["title"] == "Clean run" and polish["badges"][0]["title"] != "Clean run"
    changed = json.loads(http("/api/settings", data={"daily_minutes": 45}, headers={"X-Language": "pl"})[2])
    assert changed["progress"]["ready"]["items"][0]["label"] == polish["ready"]["items"][0]["label"]
