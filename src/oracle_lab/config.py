"""Settings of the app, read once from the environment (12-factor style).

Non-secret settings are plain environment variables; passwords go through `credentials`, so
they can live in secret files. Every variable is optional and has a development default.

    STUDY_HOST, STUDY_PORT           address of the web server (default 127.0.0.1:8071)
    STUDY_DATA_DIR                   progress.json and personal notes
                                     (default $XDG_DATA_HOME/oracle-learning-lab)
    STUDY_STATE_FILE                 progress file, overriding STUDY_DATA_DIR/progress.json
    STUDY_DSN, STUDY_USER            learning schema (default localhost:1521/ORAPDB1, orastudy)
    STUDY_PASSWORD[_FILE]            its password (fallback: ~/.orastudy_pwd)
    STUDY_DSN_23AI, STUDY_USER_23AI  optional Oracle 23ai database for the 1Z0-171 track
    STUDY_PASSWORD_23AI[_FILE]       its password (default: the STUDY_PASSWORD one)
    STUDY_STATE_USER                 keep progress and personal notes in this Oracle user's tables instead
                                     of files, for hosts without a persistent disk (must not be STUDY_USER)
    STUDY_STATE_DSN                  its database (default: the STUDY_DSN one)
    STUDY_STATE_PASSWORD[_FILE]      its password
    STUDY_AUTH_USER                  login of the web app (default "study")
    STUDY_AUTH_PASSWORD[_FILE]       enables HTTP basic auth when set and not empty
    STUDY_INIT_TIMEOUT               seconds `init-db` waits for the database (default 600)
    STUDY_CALL_TIMEOUT_MS            limit for one database round trip (default 15000)
    STUDY_LOG_LEVEL                  DEBUG, INFO (default), WARNING, ...
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from oracle_lab.credentials import Secret, SecretNotFoundError, resolve_secret

EXAM_23AI = "1Z0-171"
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


class ConfigurationError(ValueError):
    """An environment variable has a value the app cannot use."""


@dataclass(frozen=True)
class DatabaseTarget:
    """Where to connect, as which user."""

    user: str
    dsn: str
    password: Secret

    def __str__(self) -> str:
        return f"{self.user}@{self.dsn}"


@dataclass(frozen=True)
class BasicAuthConfig:
    user: str
    password: str = field(repr=False)


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    data_dir: Path
    state_file: Path
    database: DatabaseTarget
    database_23ai: DatabaseTarget | None
    state_database: DatabaseTarget | None
    auth: BasicAuthConfig | None
    init_timeout: float
    call_timeout_ms: int
    log_level: str

    @property
    def personal_notes_dir(self) -> Path:
        return self.data_dir / "notes"

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> Settings:
        data_dir = Path(env.get("STUDY_DATA_DIR") or _default_data_dir(env)).expanduser()
        user = env.get("STUDY_USER", "orastudy")
        password = (resolve_secret("STUDY_PASSWORD", env, fallback_file=Path.home() / ".orastudy_pwd")
                    or Secret.missing("STUDY_PASSWORD"))
        dsn_23ai = env.get("STUDY_DSN_23AI")
        database = DatabaseTarget(user, env.get("STUDY_DSN", "localhost:1521/ORAPDB1"), password)
        return cls(
            host=env.get("STUDY_HOST", "127.0.0.1"),
            port=_integer(env, "STUDY_PORT", 8071, minimum=1, maximum=65535),
            data_dir=data_dir,
            state_file=Path(env.get("STUDY_STATE_FILE") or data_dir / "progress.json").expanduser(),
            database=database,
            database_23ai=DatabaseTarget(
                env.get("STUDY_USER_23AI", user), dsn_23ai,
                resolve_secret("STUDY_PASSWORD_23AI", env) or password,
            ) if dsn_23ai else None,
            state_database=_state_database(env, database),
            auth=_basic_auth(env),
            init_timeout=_integer(env, "STUDY_INIT_TIMEOUT", 600, minimum=0),
            call_timeout_ms=_integer(env, "STUDY_CALL_TIMEOUT_MS", 15000, minimum=1),
            log_level=_log_level(env),
        )


def _default_data_dir(env: Mapping[str, str]) -> Path:
    base = Path(env.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "oracle-learning-lab"


def _integer(env: Mapping[str, str], name: str, default: int, minimum: int | None = None,
             maximum: int | None = None) -> int:
    raw = env.get(name)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ConfigurationError(f"{name} must be a whole number, got {raw!r}") from None
    if (minimum is not None and value < minimum) or (maximum is not None and value > maximum):
        raise ConfigurationError(f"{name} is out of range: {value}")
    return value


def _log_level(env: Mapping[str, str]) -> str:
    level = env.get("STUDY_LOG_LEVEL", "INFO").upper()
    if level not in LOG_LEVELS:
        raise ConfigurationError(f"STUDY_LOG_LEVEL must be one of {', '.join(LOG_LEVELS)}, got {level!r}")
    return level


def _state_database(env: Mapping[str, str], study: DatabaseTarget) -> DatabaseTarget | None:
    user = env.get("STUDY_STATE_USER")
    if not user:
        return None
    dsn = env.get("STUDY_STATE_DSN") or study.dsn
    return DatabaseTarget(user, dsn, resolve_secret("STUDY_STATE_PASSWORD", env) or Secret.missing("STUDY_STATE_PASSWORD"))


def _basic_auth(env: Mapping[str, str]) -> BasicAuthConfig | None:
    """Basic auth is on when a non-empty password is configured. Read once: it guards every request."""
    secret = resolve_secret("STUDY_AUTH_PASSWORD", env)
    if secret is None:
        return None
    try:
        password = secret.reveal()
    except SecretNotFoundError as exc:
        raise ConfigurationError(str(exc)) from exc
    return BasicAuthConfig(env.get("STUDY_AUTH_USER", "study"), password) if password else None
