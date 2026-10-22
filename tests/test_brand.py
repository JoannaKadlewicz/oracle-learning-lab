"""The product name comes from STUDY_APP_NAME (default "Stepwise"): every page a user sees shows it."""

from __future__ import annotations

import pathlib

from conftest import settings_for
from oracle_lab.config import Settings

STATIC = pathlib.Path(__file__).parent.parent / "src" / "oracle_lab" / "resources" / "static"
SERVER_CATALOG = pathlib.Path(__file__).parent.parent / "src" / "oracle_lab" / "i18n" / "pl.json"


def test_default_name_is_stepwise(tmp_path):
    assert settings_for(tmp_path).app_name == "Stepwise"


def test_pages_show_the_configured_name(serve, tmp_path):
    http = serve(settings_for(tmp_path, STUDY_APP_NAME="Acme & Co"))
    for path in ("/login", "/register", "/reset"):
        page = http(path)[2].decode()
        assert "Acme &amp; Co" in page and "{{APP_NAME}}" not in page, path
    assert "Sign in · Acme &amp; Co</title>" in http("/login")[2].decode()
    app = http.sign_in("a@x.org")("/")[2].decode()  # the app itself, signed in
    assert "<title>Acme &amp; Co</title>" in app and 'data-app-name="Acme &amp; Co"' in app


def test_no_oracle_learning_lab_left():
    files = [*STATIC.rglob("*.html"), *STATIC.rglob("*.js"), STATIC / "i18n" / "pl.json", SERVER_CATALOG]
    assert [str(f) for f in files if "Oracle Learning Lab" in f.read_text(encoding="utf-8")] == []


def test_settings_type_carries_the_name():
    assert "app_name" in Settings.__dataclass_fields__
