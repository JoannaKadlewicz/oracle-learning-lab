"""The HTTP layer end to end over a real socket: health check, routing, errors (no database needed).
Every test signs in first (conftest.Client.sign_in); the login itself is covered by test_auth_web.py."""

import json

from conftest import settings_for
from oracle_lab import content
from oracle_lab.study.state import MemoryStateStore


def test_health_check_needs_no_login(serve):
    status, _, body = serve()("/healthz")
    assert (status, json.loads(body)) == (200, {"ok": True})


def test_api_calls_need_a_login(serve):
    http = serve()
    assert http("/api/state")[0] == 401
    assert http.sign_in()("/api/state")[0] == 200


def test_personal_notes_are_kept_in_the_data_dir(serve, tmp_path):
    http = serve(settings_for(tmp_path)).sign_in()
    status, _, body = http("/api/notes/save", data={"title": "Joins", "sql": "SELECT 1 FROM dual;"})
    path = json.loads(body)["path"]
    assert status == 200 and path.startswith("personal/")
    assert (tmp_path / "notes" / path.removeprefix("personal/")).is_file()
    assert path in {n["path"] for n in json.loads(http("/api/notes")[2])}
    assert "SELECT 1 FROM dual;" in json.loads(http(f"/api/note?path={path}")[2])["text"]
    assert http("/api/note?path=../../etc/passwd")[0] == 404


def test_answers_are_saved_and_progress_is_returned(serve, tmp_path):
    store = MemoryStateStore()
    http = serve(settings_for(tmp_path), store).sign_in()
    question = content.QUESTIONS[0]
    status, _, body = http("/api/attempt", data={"id": question["id"], "chosen": question["answer"]})
    assert status == 200 and json.loads(body)["progress"]["exam"] == content.DEFAULT_EXAM
    assert store.state["attempts"][question["id"]][0]["correct"] is True


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
