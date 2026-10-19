"""The HTTP layer end to end over a real socket: auth, health check, routing, errors (no database needed)."""

import base64
import json
import threading
import urllib.error
import urllib.request

import pytest

from oracle_lab import content
from oracle_lab.bootstrap import build_app
from oracle_lab.config import Settings
from oracle_lab.study.state import MemoryStateStore
from oracle_lab.web.server import create_server

NOW = 1_800_000_000


def settings_for(tmp_path, **env):
    return Settings.from_env({"STUDY_DATA_DIR": str(tmp_path), "STUDY_PASSWORD": "unused", **env})


@pytest.fixture
def serve():
    """Start the app on a free port; returns request(path, ...) -> (status, headers, body)."""
    servers = []

    def start(settings, store=None):
        httpd = create_server(build_app(settings, store=store or MemoryStateStore(), clock=lambda: NOW), "127.0.0.1", 0)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        servers.append(httpd)

        def request(path, data=None, user=None, password=None, headers=None):
            body = json.dumps(data).encode() if isinstance(data, dict) else data
            req = urllib.request.Request(f"http://127.0.0.1:{httpd.server_port}{path}", data=body, headers=headers or {})
            if user is not None:
                req.add_header("Authorization", "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode())
            try:
                with urllib.request.urlopen(req) as resp:
                    return resp.status, resp.headers, resp.read()
            except urllib.error.HTTPError as exc:
                return exc.code, exc.headers, exc.read()

        return request

    yield start
    for httpd in servers:
        httpd.shutdown()
        httpd.server_close()


def test_without_a_password_no_login_is_needed(serve, tmp_path):
    http = serve(settings_for(tmp_path))
    assert http("/api/state")[0] == 200


def test_with_a_password_every_page_and_api_call_needs_the_login(serve, tmp_path):
    http = serve(settings_for(tmp_path, STUDY_AUTH_PASSWORD="s3cret"))
    status, headers, _ = http("/")
    assert status == 401 and headers["WWW-Authenticate"].startswith("Basic")
    assert http("/api/state")[0] == 401
    assert http("/api/reset-progress", data={})[0] == 401
    assert http("/api/state", user="study", password="wrong")[0] == 401
    assert http("/api/state", user="someone", password="s3cret")[0] == 401
    assert http("/api/state", headers={"Authorization": "Basic !!not-base64!!"})[0] == 401
    assert http("/api/state", user="study", password="s3cret")[0] == 200
    assert http("/api/reset-progress", data={}, user="study", password="s3cret")[0] == 200


def test_auth_password_can_come_from_a_secret_file(serve, tmp_path):
    secret = tmp_path / "auth"
    secret.write_text("from-file\n")
    http = serve(settings_for(tmp_path, STUDY_AUTH_PASSWORD_FILE=str(secret)))
    assert http("/api/state", user="study", password="from-file")[0] == 200


def test_health_check_needs_no_login(serve, tmp_path):
    http = serve(settings_for(tmp_path, STUDY_AUTH_PASSWORD="s3cret"))
    status, _, body = http("/healthz")
    assert (status, json.loads(body)) == (200, {"ok": True})


def test_personal_notes_are_kept_in_the_data_dir(serve, tmp_path):
    http = serve(settings_for(tmp_path))
    status, _, body = http("/api/notes/save", data={"title": "Joins", "sql": "SELECT 1 FROM dual;"})
    path = json.loads(body)["path"]
    assert status == 200 and path.startswith("personal/")
    assert (tmp_path / "notes" / path.removeprefix("personal/")).is_file()
    assert path in {n["path"] for n in json.loads(http("/api/notes")[2])}
    assert "SELECT 1 FROM dual;" in json.loads(http(f"/api/note?path={path}")[2])["text"]
    assert http("/api/note?path=../../etc/passwd")[0] == 404


def test_answers_are_saved_and_progress_is_returned(serve, tmp_path):
    store = MemoryStateStore()
    http = serve(settings_for(tmp_path), store)
    question = content.QUESTIONS[0]
    status, _, body = http("/api/attempt", data={"id": question["id"], "chosen": question["answer"]})
    assert status == 200 and json.loads(body)["progress"]["exam"] == content.DEFAULT_EXAM
    assert store.state["attempts"][question["id"]][0]["correct"] is True


def test_invalid_input_is_a_client_error(serve, tmp_path):
    http = serve(settings_for(tmp_path))
    assert http("/api/attempt", data={"id": "no-such-question"})[0] == 404
    assert http("/api/settings", data={"daily_minutes": 0})[0] == 400
    assert http("/api/settings", data=b"{not json")[0] == 400
    assert http("/api/mock?id=missing")[0] == 404
    assert http("/api/mock/teleport", data={})[0] == 404
    assert http("/api/no-such-endpoint", data={})[0] == 404


def test_cross_origin_posts_are_refused(serve, tmp_path):
    http = serve(settings_for(tmp_path))
    assert http("/api/reset-progress", data={}, headers={"Origin": "https://evil.example"})[0] == 403


def test_front_end_routes_get_the_app_shell_and_missing_assets_a_404(serve, tmp_path):
    http = serve(settings_for(tmp_path))
    status, headers, body = http("/quiz")
    assert status == 200 and headers["Content-Type"].startswith("text/html") and b"<html" in body.lower()
    assert http("/js/no-such-file.js")[0] == 404
    assert http("/../../pyproject.toml")[0] in (200, 404)  # never outside the static dir
    assert b"[project]" not in http("/../../pyproject.toml")[2]


def test_mock_exam_round_trip(serve, tmp_path):
    http = serve(settings_for(tmp_path))
    status, _, body = http("/api/mock/start", data={"count": 2, "minutes": 5})
    mock = json.loads(body)["mock"]
    assert status == 200 and len(mock["items"]) == 2
    answer = {"mock_id": mock["id"], "id": mock["items"][0], "chosen": [0]}
    assert json.loads(http("/api/mock/answer", data=answer)[2]) == {"ok": True}
    report = json.loads(http("/api/mock/submit", data={"mock_id": mock["id"]})[2])["report"]
    assert report["score"][1] == 2
