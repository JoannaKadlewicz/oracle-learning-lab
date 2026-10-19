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
    assert settings.database_23ai is None and settings.auth is None


def test_the_23ai_database_reuses_the_main_password_unless_it_has_its_own():
    shared = Settings.from_env({"STUDY_PASSWORD": "main", "STUDY_DSN_23AI": "db23:1521/FREEPDB1"})
    assert shared.database_23ai.password.reveal() == "main"
    own = Settings.from_env({"STUDY_PASSWORD": "main", "STUDY_DSN_23AI": "db23", "STUDY_PASSWORD_23AI": "other"})
    assert own.database_23ai.password.reveal() == "other"


def test_an_empty_auth_password_turns_login_off(tmp_path):
    empty = tmp_path / "auth"
    empty.write_text("\n")
    assert Settings.from_env({"STUDY_AUTH_PASSWORD_FILE": str(empty)}).auth is None
    assert Settings.from_env({"STUDY_AUTH_PASSWORD": "pw", "STUDY_AUTH_USER": "me"}).auth.user == "me"
    with pytest.raises(ConfigurationError):
        Settings.from_env({"STUDY_AUTH_PASSWORD_FILE": str(tmp_path / "missing")})


@pytest.mark.parametrize("port", ["eighty", "0", "70000"])
def test_bad_numbers_are_configuration_errors(port):
    with pytest.raises(ConfigurationError, match="STUDY_PORT"):
        Settings.from_env({"STUDY_PORT": port})


def test_unknown_log_level_is_a_configuration_error():
    with pytest.raises(ConfigurationError, match="STUDY_LOG_LEVEL"):
        Settings.from_env({"STUDY_LOG_LEVEL": "loud"})
    assert Settings.from_env({"STUDY_LOG_LEVEL": "debug"}).log_level == "DEBUG"
