import logging
from urllib.parse import parse_qs, urlparse

import pytest

from conftest import PASSWORD, settings_for
from oracle_lab.accounts.first_admin import ensure_first_admin, import_legacy, legacy_hook, retry_legacy_import
from oracle_lab.accounts.memory import memory_stores
from oracle_lab.auth.audit import AuditLog
from oracle_lab.auth.google import GoogleSignIn
from oracle_lab.auth.models import Identity, User
from oracle_lab.auth.passwords import PasswordPolicy, verify_password
from oracle_lab.auth.registration import Registration, RegistrationPolicy
from oracle_lab.auth.sessions import SessionManager
from oracle_lab.auth.throttle import Throttle
from oracle_lab.bootstrap import build_app
from oracle_lab.config import ConfigurationError, GoogleConfig
from oracle_lab.credentials import Secret
from oracle_lab.study.notes import FileNotes
from oracle_lab.study.state import JsonStateStore, new_state
from test_google import CID, FakeEndpoint

CLOCK = lambda: 1000.0  # noqa: E731


def test_admin_created_from_settings_with_password(tmp_path, caplog):
    stores = memory_stores()
    audit = AuditLog(stores.audit, CLOCK)
    settings = settings_for(tmp_path, STUDY_ADMIN_EMAIL="Boss@Example.org", STUDY_ADMIN_PASSWORD=PASSWORD)
    seen = []
    with caplog.at_level(logging.DEBUG):
        ensure_first_admin(stores, settings, CLOCK, audit, seen.append)
        ensure_first_admin(stores, settings, CLOCK, audit, seen.append)  # a second start does nothing
    user = stores.users.by_email("boss@example.org")
    assert user.role == "admin" and stores.users.count() == 1 and seen == [user]
    (identity,) = stores.users.identities(user.id)
    assert verify_password(PASSWORD, identity.password_hash)
    assert [e.event for e in stores.audit.recent()] == ["admin_bootstrapped"]
    assert PASSWORD not in caplog.text and PASSWORD not in repr(stores.audit.recent())


def test_existing_users_stop_the_bootstrap(tmp_path):
    stores = memory_stores()
    app_settings = settings_for(tmp_path)
    build_app(app_settings, stores=stores)  # no admin email: nothing happens
    assert stores.users.count() == 0 and not stores.settings.get("admin_email_claim")


def test_admin_email_without_password_is_claimed_by_google(tmp_path):
    stores = memory_stores()
    settings = settings_for(tmp_path, STUDY_ADMIN_EMAIL="ann@example.org")
    audit = AuditLog(stores.audit, CLOCK)
    ensure_first_admin(stores, settings, CLOCK, audit)
    assert stores.users.count() == 0
    assert stores.settings.get("admin_email_claim") == "ann@example.org"

    state = JsonStateStore(tmp_path / "legacy.json")
    with state.transaction() as s:
        s["settings"]["marker"] = 1
    hook = legacy_hook(stores, lambda: (state, None), audit)
    sessions, throttle = SessionManager(stores.sessions, CLOCK), Throttle(stores.throttle, CLOCK)
    reg = Registration(stores, PasswordPolicy(frozenset()), RegistrationPolicy(stores.settings, stores.users, True, 9),
                       sessions, throttle, audit, CLOCK, hook, first_user_is_admin=False)
    endpoint = FakeEndpoint()
    google = GoogleSignIn(GoogleConfig(CID, Secret.from_value("s", "test")), "https://lab.example", endpoint,
                          stores, sessions, throttle, audit, CLOCK, reg)
    url, flow_id = google.start("login", "/", None, "1.1.1.1")
    flow = next(iter(stores.flows._flows.values()))  # noqa: SLF001
    endpoint.claims = {"iss": "https://accounts.google.com", "aud": CID, "exp": 2000, "nonce": flow.nonce,
                       "sub": "s1", "email": "ann@example.org", "email_verified": True, "name": "Ann"}
    google.finish(flow_id, parse_qs(urlparse(url).query)["state"][0], "c", "ip", "ua", None)
    ann = stores.users.by_email("ann@example.org")
    assert ann.role == "admin"
    assert stores.states.for_user(ann.id).load()["settings"] == {"marker": 1}
    assert stores.settings.get("legacy_imported") == "1"


def test_first_registered_user_is_admin_without_admin_email(tmp_path, serve):
    stores = memory_stores()
    state = JsonStateStore(tmp_path / "progress.json")
    with state.transaction() as s:
        s["settings"]["marker"] = 1
    http = serve(settings_for(tmp_path), stores=stores)
    http.sign_in("first@example.org")
    first = stores.users.by_email("first@example.org")
    assert first.role == "admin"
    assert stores.states.for_user(first.id).load()["settings"] == {"marker": 1}
    http2 = serve(settings_for(tmp_path), stores=stores).sign_in("second@example.org")
    second = stores.users.by_email("second@example.org")
    assert second.role == "learner" and stores.states.for_user(second.id).load() == new_state()
    assert http2


def test_warning_when_the_first_user_becomes_admin(tmp_path, caplog):
    with caplog.at_level(logging.WARNING):
        build_app(settings_for(tmp_path), stores=memory_stores())
    assert "STUDY_ADMIN_EMAIL is not set: the first account to register becomes the admin." in caplog.text
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        build_app(settings_for(tmp_path, STUDY_ADMIN_EMAIL="a@example.org"), stores=memory_stores())
    assert "STUDY_ADMIN_EMAIL" not in caplog.text


def test_legacy_progress_and_notes_move_once(tmp_path):
    stores = memory_stores()
    state = JsonStateStore(tmp_path / "progress.json")
    with state.transaction() as s:
        s["settings"]["exam"] = "1z0-082"
        s["mocks"].append({"id": "m1"})
    notes = FileNotes(tmp_path / "notes")
    notes.add("2026-01-01-joins", "Joins", "# Joins\n\nbody")
    notes.add("2026-01-02-sets", "Sets", "# Sets\n")

    assert import_legacy(stores, "u1", state, notes) is True
    assert import_legacy(stores, "u1", state, notes) is False
    assert stores.states.for_user("u1").load()["mocks"] == [{"id": "m1"}]
    assert stores.states.for_user("u1").load()["settings"] == {"exam": "1z0-082"}
    assert stores.notes.for_user("u1").entries() == [("2026-01-02-sets.md", "Sets"), ("2026-01-01-joins.md", "Joins")]
    assert stores.notes.for_user("u1").read("2026-01-01-joins.md") == "# Joins\n\nbody"
    assert len(notes.entries()) == 2 and state.load()["mocks"]  # sources are kept


def test_empty_legacy_still_marks_imported_and_missing_oracle_tables_count_as_empty(tmp_path):
    stores = memory_stores()

    class NoTables:
        def load(self):
            raise RuntimeError("ORA-00942: table or view does not exist")

        def entries(self):
            raise RuntimeError("ORA-00942: table or view does not exist")

    assert import_legacy(stores, "u1", NoTables(), NoTables()) is True
    assert stores.settings.get("legacy_imported") == "1"
    assert import_legacy(stores, "u2", JsonStateStore(tmp_path / "none.json"), None) is False


def test_admin_email_with_existing_users_does_nothing(tmp_path):
    stores = memory_stores()
    stores.users.add(User("u", "x@example.org", "X", "learner", "active", 1.0, None, None),
                     Identity("password", "u", "u", "h"))
    ensure_first_admin(stores, settings_for(tmp_path, STUDY_ADMIN_EMAIL="a@example.org",
                                            STUDY_ADMIN_PASSWORD=PASSWORD), CLOCK, AuditLog(stores.audit, CLOCK))
    assert stores.users.count() == 1 and not stores.settings.get("admin_email_claim")


def test_weak_admin_password_is_a_configuration_error(tmp_path):
    with pytest.raises(ConfigurationError, match="STUDY_ADMIN_PASSWORD"):
        build_app(settings_for(tmp_path, STUDY_ADMIN_EMAIL="a@example.org", STUDY_ADMIN_PASSWORD="short"),
                  stores=memory_stores())


class Broken:
    def load(self):
        raise OSError("disk gone")

    def entries(self):
        return []


def test_failing_legacy_source_does_not_break_sign_up_and_is_retried(tmp_path, serve, monkeypatch):
    stores = memory_stores()
    settings = settings_for(tmp_path)
    good = JsonStateStore(tmp_path / "progress.json")
    with good.transaction() as s:
        s["settings"]["marker"] = 1
    monkeypatch.setattr("oracle_lab.bootstrap.JsonStateStore", lambda path: Broken())
    http = serve(settings, stores=stores)
    http.sign_in("first@example.org")  # asserts 200 and a session cookie
    first = stores.users.by_email("first@example.org")
    (event,) = stores.audit.recent(event="legacy_import")
    assert event.outcome == "fail" and event.detail == {"reason": "OSError"}
    assert stores.settings.get("legacy_imported") is None

    monkeypatch.undo()
    build_app(settings, stores=stores)  # next start: the source works now
    assert stores.states.for_user(first.id).load()["settings"] == {"marker": 1}
    assert stores.settings.get("legacy_imported") == "1"


def test_retry_never_overwrites_existing_progress(tmp_path, caplog):
    stores = memory_stores()
    audit = AuditLog(stores.audit, CLOCK)
    stores.users.add(User("a", "a@example.org", "A", "admin", "active", 1.0, None, None),
                     Identity("password", "a", "a", "h"))
    with stores.states.for_user("a").transaction() as s:
        s["settings"]["mine"] = 1
    legacy = JsonStateStore(tmp_path / "progress.json")
    with legacy.transaction() as s:
        s["settings"]["old"] = 1
    with caplog.at_level(logging.WARNING):
        retry_legacy_import(stores, lambda: (legacy, None), audit)
    assert stores.states.for_user("a").load()["settings"] == {"mine": 1}
    assert stores.settings.get("legacy_imported") == "1" and "already has progress" in caplog.text


def test_partial_import_is_undone(tmp_path):
    stores = memory_stores()
    state = JsonStateStore(tmp_path / "progress.json")
    with state.transaction() as s:
        s["settings"]["x"] = 1

    class BadNotes:
        def entries(self):
            return [("n.md", "N")]

        def read(self, name):
            raise OSError("boom")

    with pytest.raises(OSError):
        import_legacy(stores, "u1", state, BadNotes())
    assert stores.states.for_user("u1").load() == new_state() and not stores.settings.get("legacy_imported")
