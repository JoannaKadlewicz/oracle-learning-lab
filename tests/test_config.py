"""Settings and credentials: defaults, secret files, and that passwords never show up in logs."""

import pytest

from oracle_lab.config import ConfigurationError, Settings
from oracle_lab.credentials import Secret, SecretNotFoundError, resolve_secret


def test_a_secret_file_takes_precedence_over_the_environment(tmp_path):
    file = tmp_path / "pw"
    file.write_text("from-file\n")
    secret = resolve_secret("STUDY_PASSWORD", {"STUDY_PASSWORD_FILE": str(file), "STUDY_PASSWORD": "from-env"})
    assert secret.reveal() == "from-file"


def test_secret_files_are_read_when_needed_so_rotation_needs_no_restart(tmp_path):
    file = tmp_path / "pw"
    file.write_text("first")
    secret = resolve_secret("X", {"X_FILE": str(file)})
    file.write_text("second")
    assert secret.reveal() == "second"


def test_fallback_file_and_missing_secret(tmp_path):
    fallback = tmp_path / ".orastudy_pwd"
    assert resolve_secret("X", {}, fallback_file=fallback) is None
    fallback.write_text("legacy")
    assert resolve_secret("X", {}, fallback_file=fallback).reveal() == "legacy"
    with pytest.raises(SecretNotFoundError, match="X_FILE"):
        Secret.missing("X").reveal()
    with pytest.raises(SecretNotFoundError, match="cannot read"):
        resolve_secret("X", {"X_FILE": str(tmp_path / "nope")}).reveal()


def test_secrets_never_show_their_value():
    secret = Secret.from_value("hunter2", "environment variable X")
    settings = Settings.from_env({"STUDY_PASSWORD": "hunter2", "STUDY_DATA_DIR": "/data"})
    assert "hunter2" not in repr(secret) + str(secret) + repr(settings) + str(settings.database)


def test_defaults_and_derived_paths(tmp_path):
    settings = Settings.from_env({"STUDY_DATA_DIR": str(tmp_path), "STUDY_PASSWORD": "x"})
    assert (settings.host, settings.port) == ("127.0.0.1", 8071)
    assert str(settings.database) == "orastudy@localhost:1521/ORAPDB1"
    assert settings.state_file == tmp_path / "progress.json"
    assert settings.personal_notes_dir == tmp_path / "notes"
    assert settings.database_23ai is None and settings.state_database is None


def test_the_23ai_database_reuses_the_main_password_unless_it_has_its_own():
    shared = Settings.from_env({"STUDY_PASSWORD": "main", "STUDY_DSN_23AI": "db23:1521/FREEPDB1"})
    assert shared.database_23ai.password.reveal() == "main"
    own = Settings.from_env({"STUDY_PASSWORD": "main", "STUDY_DSN_23AI": "db23", "STUDY_PASSWORD_23AI": "other"})
    assert own.database_23ai.password.reveal() == "other"


def test_the_state_user_shares_the_study_database_unless_it_has_its_own():
    shared = Settings.from_env({"STUDY_DSN": "adb_low", "STUDY_STATE_USER": "oralab_app", "STUDY_STATE_PASSWORD": "s"})
    assert str(shared.state_database) == "oralab_app@adb_low" and shared.state_database.password.reveal() == "s"
    own = Settings.from_env({"STUDY_STATE_USER": "orastudy", "STUDY_STATE_DSN": "elsewhere"})
    assert str(own.state_database) == "orastudy@elsewhere"
    with pytest.raises(SecretNotFoundError, match="STUDY_STATE_PASSWORD"):
        own.state_database.password.reveal()


def test_progress_cannot_live_in_the_learning_schema():
    with pytest.raises(ConfigurationError, match="STUDY_STATE_USER"):
        Settings.from_env({"STUDY_USER": "orastudy", "STUDY_STATE_USER": "ORASTUDY"})
    # allowed once learners have their own schemas
    Settings.from_env({"STUDY_USER": "orastudy", "STUDY_STATE_USER": "ORASTUDY", "STUDY_PROVISIONER_USER": "a",
                       "STUDY_PROVISIONER_PASSWORD": "p", "STUDY_GATEWAY_USER": "g", "STUDY_GATEWAY_PASSWORD": "g"})


def test_public_url_defaults_to_host_and_port_and_decides_cookie_security():
    s = Settings.from_env({"STUDY_PORT": "9000"})
    assert s.public_url == "http://127.0.0.1:9000" and not s.secure_cookies
    secure = Settings.from_env({"STUDY_PUBLIC_URL": "https://lab.example.org/"})
    assert secure.public_url == "https://lab.example.org" and secure.secure_cookies
    with pytest.raises(ConfigurationError, match="STUDY_PUBLIC_URL"):
        Settings.from_env({"STUDY_PUBLIC_URL": "lab.example.org"})


def test_trust_proxy_is_opt_in():
    assert Settings.from_env({}).trust_proxy is False
    assert Settings.from_env({"STUDY_TRUST_PROXY": "yes", "STUDY_PUBLIC_URL": "https://lab.example.org"}).trust_proxy


def test_google_needs_both_id_and_secret():
    assert Settings.from_env({}).google is None
    with pytest.raises(ConfigurationError, match="STUDY_GOOGLE_CLIENT_SECRET"):
        Settings.from_env({"STUDY_GOOGLE_CLIENT_ID": "abc"})
    g = Settings.from_env({"STUDY_GOOGLE_CLIENT_ID": "abc", "STUDY_GOOGLE_CLIENT_SECRET": "s"}).google
    assert g.client_id == "abc" and g.client_secret.reveal() == "s"


def test_admin_account_is_normalised_and_optional():
    assert Settings.from_env({}).admin_email is None and Settings.from_env({}).admin_password is None
    s = Settings.from_env({"STUDY_ADMIN_EMAIL": " Boss@Example.ORG ", "STUDY_ADMIN_PASSWORD": "pw"})
    assert s.admin_email == "boss@example.org" and s.admin_password.reveal() == "pw"


def test_practice_targets_need_provisioner_and_gateway():
    env = {"STUDY_PROVISIONER_USER": "admin", "STUDY_PROVISIONER_PASSWORD": "p", "STUDY_GATEWAY_USER": "oll_gateway",
           "STUDY_GATEWAY_PASSWORD": "g", "STUDY_DSN": "db1"}
    s = Settings.from_env(env)
    default = s.practice["default"]
    assert set(s.practice) == {"default"} and default.quota_mb == 50 and default.tablespace == "USERS"
    assert str(default.provisioner) == "admin@db1" and str(default.gateway) == "oll_gateway@db1"
    assert Settings.from_env({"STUDY_PROVISIONER_USER": "admin"}).practice == {}
    both = Settings.from_env({**env, "STUDY_DSN_23AI": "db2", "STUDY_PROVISIONER_USER_23AI": "a2",
                              "STUDY_GATEWAY_USER_23AI": "g2", "STUDY_PRACTICE_QUOTA_MB_23AI": "10",
                              "STUDY_PRACTICE_TABLESPACE_23AI": "DATA"})
    assert set(both.practice) == {"default", "23ai"}
    assert str(both.practice["23ai"].gateway) == "g2@db2" and both.practice["23ai"].quota_mb == 10
    assert both.practice["23ai"].tablespace == "DATA"


def test_registration_and_cap():
    assert Settings.from_env({}).registration_open is True
    assert Settings.from_env({"STUDY_REGISTRATION": "closed"}).registration_open is False
    with pytest.raises(ConfigurationError, match="STUDY_REGISTRATION"):
        Settings.from_env({"STUDY_REGISTRATION": "maybe"})
    assert Settings.from_env({}).max_users == 25
    with pytest.raises(ConfigurationError):
        Settings.from_env({"STUDY_MAX_USERS": "0"})


def test_legacy_basic_auth_is_flagged_while_it_is_configured(tmp_path):
    assert Settings.from_env({}).legacy_basic_auth is False
    assert Settings.from_env({"STUDY_AUTH_PASSWORD": "pw"}).legacy_basic_auth is True
    pw = tmp_path / "pw"
    pw.write_text("pw\n")
    assert Settings.from_env({"STUDY_AUTH_PASSWORD_FILE": str(pw)}).legacy_basic_auth is True


@pytest.mark.parametrize("port", ["eighty", "0", "70000"])
def test_bad_numbers_are_configuration_errors(port):
    with pytest.raises(ConfigurationError, match="STUDY_PORT"):
        Settings.from_env({"STUDY_PORT": port})


def test_unknown_log_level_is_a_configuration_error():
    with pytest.raises(ConfigurationError, match="STUDY_LOG_LEVEL"):
        Settings.from_env({"STUDY_LOG_LEVEL": "loud"})
    assert Settings.from_env({"STUDY_LOG_LEVEL": "debug"}).log_level == "DEBUG"


def test_google_with_an_empty_secret_file_is_refused(tmp_path):
    empty = tmp_path / "google"
    empty.write_text("")
    assert Settings.from_env({"STUDY_GOOGLE_CLIENT_SECRET_FILE": str(empty)}).google is None
    with pytest.raises(ConfigurationError, match="empty"):
        Settings.from_env({"STUDY_GOOGLE_CLIENT_ID": "abc", "STUDY_GOOGLE_CLIENT_SECRET_FILE": str(empty)})


def test_admin_email_needs_a_password_or_google():
    with pytest.raises(ConfigurationError, match="STUDY_ADMIN_PASSWORD.*STUDY_GOOGLE_CLIENT_ID"):
        Settings.from_env({"STUDY_ADMIN_EMAIL": "boss@example.org"})
    assert Settings.from_env({"STUDY_ADMIN_EMAIL": "boss@example.org", "STUDY_ADMIN_PASSWORD": "pw"}).admin_email
    google = {"STUDY_GOOGLE_CLIENT_ID": "abc", "STUDY_GOOGLE_CLIENT_SECRET": "s"}
    assert Settings.from_env({"STUDY_ADMIN_EMAIL": "boss@example.org", **google}).admin_email == "boss@example.org"


def test_trusting_a_proxy_needs_an_https_public_url():
    with pytest.raises(ConfigurationError, match="set STUDY_PUBLIC_URL to your https address"):
        Settings.from_env({"STUDY_TRUST_PROXY": "1"})
    with pytest.raises(ConfigurationError, match="STUDY_PUBLIC_URL"):
        Settings.from_env({"STUDY_TRUST_PROXY": "yes", "STUDY_PUBLIC_URL": "http://lab.example.org"})
    assert Settings.from_env({"STUDY_TRUST_PROXY": "1", "STUDY_PUBLIC_URL": "https://lab.example.org"}).trust_proxy


@pytest.mark.parametrize("url", ["http://", "https://", "https:///", "https://:8071", "http:// /x"])
def test_public_url_needs_a_host(url):
    with pytest.raises(ConfigurationError, match="STUDY_PUBLIC_URL"):
        Settings.from_env({"STUDY_PUBLIC_URL": url})


def test_an_empty_admin_password_file_counts_as_unset(tmp_path):
    empty = tmp_path / "admin_password"
    empty.write_text("")
    assert Settings.from_env({"STUDY_ADMIN_PASSWORD_FILE": str(empty)}).admin_password is None
    with pytest.raises(ConfigurationError, match="STUDY_ADMIN_PASSWORD"):
        Settings.from_env({"STUDY_ADMIN_EMAIL": "boss@example.org", "STUDY_ADMIN_PASSWORD_FILE": str(empty)})
    empty.write_text("a fine long passphrase\n")
    s = Settings.from_env({"STUDY_ADMIN_EMAIL": "boss@example.org", "STUDY_ADMIN_PASSWORD_FILE": str(empty)})
    assert s.admin_password.reveal() == "a fine long passphrase"
