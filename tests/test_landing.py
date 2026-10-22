"""The landing page: logged out, "/" is the sign-in page with the workspaces to try; a workspace tile starts a
guest right inside it; signed in, "/" is the app in the default workspace."""

from __future__ import annotations

import json

from conftest import Client, session_cookie
from oracle_lab import exams
from oracle_lab.accounts.memory import memory_stores


def test_logged_out_root_is_the_landing_page(serve):
    status, headers, body = serve()("/")
    assert status == 200 and b'id="login-form"' in body and b'id="landing-workspaces"' in body


def test_signed_in_root_is_the_app(serve):
    http = serve().sign_in()
    status, _, body = http("/")
    assert status == 200 and b'id="main"' in body


def test_config_lists_the_workspaces_to_try(serve):
    config = json.loads(serve()("/api/auth/config")[2])
    workspaces = config["workspaces"]
    assert [w["code"] for w in workspaces] == list(exams.EXAMS)
    first = workspaces[0]
    assert first["logo"] == "oracle" and first["title"] and first["tile"] and first["minutes"] == 120
    assert first["counts"]["questions"] > 50 and first["counts"]["flashcards"] > 0 and first["counts"]["exercises"] > 0


def test_a_tile_starts_a_guest_inside_its_workspace(serve):
    stores = memory_stores()
    server = serve(stores=stores)
    status, headers, _ = server("/api/auth/guest", {"workspace": "1Z0-171"}, headers={"Origin": server.origin})
    assert status == 200
    cookie = session_cookie(headers)
    guest = next(u for u in stores.users.all() if u.role == "guest")
    assert [r.workspace for r in stores.access.for_user(guest.id)] == ["1Z0-171"]
    overview = json.loads(server("/api/workspaces", headers={"Cookie": cookie})[2])
    assert overview["current"] == "1Z0-171"


def test_an_unknown_workspace_still_starts_a_guest_who_picks(serve):
    stores = memory_stores()
    server = serve(stores=stores)
    assert server("/api/auth/guest", {"workspace": "nope"}, headers={"Origin": server.origin})[0] == 200
    guest = next(u for u in stores.users.all() if u.role == "guest")
    assert stores.access.for_user(guest.id) == []


def test_the_landing_scripts_are_public(serve):
    http = serve()
    for path in ("/js/ui/tech-logos.js", "/js/ui/workspace-tiles.js"):
        assert http(path)[0] == 200, path
    assert Client(http.port)("/js/main.js")[0] == 401
