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
    STUDY_AUTH_PASSWORD[_FILE]       the old basic-auth password: no longer used, only warned about
    STUDY_PUBLIC_URL                 address users reach the app at (default http://HOST:PORT); https turns on
                                     secure cookies
    STUDY_TRUST_PROXY                1, true or yes: believe X-Forwarded-For from a reverse proxy
    STUDY_GOOGLE_CLIENT_ID           enables "Sign in with Google" ...
    STUDY_GOOGLE_CLIENT_SECRET[_FILE] ... together with this secret
    STUDY_ADMIN_EMAIL                account that is made administrator
    STUDY_ADMIN_PASSWORD[_FILE]      its initial password
    STUDY_REGISTRATION               open (default) or closed: may new users sign up
    STUDY_MAX_USERS                  cap on accounts (default 25)
    STUDY_PROVISIONER_USER           Oracle user that creates and drops practice schemas; with
    STUDY_PROVISIONER_PASSWORD[_FILE]  its password, and
    STUDY_GATEWAY_USER               the proxy user that connects as a learner's schema, with
    STUDY_GATEWAY_PASSWORD[_FILE]    its password; both on STUDY_DSN enable private practice schemas
    STUDY_PRACTICE_TABLESPACE        default tablespace of a practice schema (default USERS)
    STUDY_PRACTICE_QUOTA_MB          its quota in MB (default 50)
    (the five practice variables above also exist with the suffix _23AI, on STUDY_DSN_23AI)
    STUDY_INIT_TIMEOUT               seconds `init-db` waits for the database (default 600)
    STUDY_CALL_TIMEOUT_MS            limit for one database round trip (default 15000)
    STUDY_LOG_LEVEL                  DEBUG, INFO (default), WARNING, ...
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from oracle_lab.credentials import Secret, resolve_secret

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
class GoogleConfig:
    client_id: str
    client_secret: Secret


@dataclass(frozen=True)
class PracticeTarget:
    """Where learners get private schemas: who creates them and who connects on their behalf."""

    provisioner: DatabaseTarget
    gateway: DatabaseTarget
    tablespace: str
    quota_mb: int


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    data_dir: Path
    state_file: Path
    database: DatabaseTarget
    database_23ai: DatabaseTarget | None
    state_database: DatabaseTarget | None
    legacy_basic_auth: bool
    public_url: str
    trust_proxy: bool
    google: GoogleConfig | None
    admin_email: str | None
    admin_password: Secret | None
    registration_open: bool
    max_users: int
    practice: dict[str, PracticeTarget]
    init_timeout: float
    call_timeout_ms: int
    log_level: str

    @property
    def personal_notes_dir(self) -> Path:
        return self.data_dir / "notes"

    @property
    def secure_cookies(self) -> bool:
        return self.public_url.startswith("https://")

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> Settings:
        data_dir = Path(env.get("STUDY_DATA_DIR") or _default_data_dir(env)).expanduser()
        user = env.get("STUDY_USER", "orastudy")
        password = (resolve_secret("STUDY_PASSWORD", env, fallback_file=Path.home() / ".orastudy_pwd")
                    or Secret.missing("STUDY_PASSWORD"))
        dsn_23ai = env.get("STUDY_DSN_23AI")
        database = DatabaseTarget(user, env.get("STUDY_DSN", "localhost:1521/ORAPDB1"), password)
        host = env.get("STUDY_HOST", "127.0.0.1")
        port = _integer(env, "STUDY_PORT", 8071, minimum=1, maximum=65535)
        practice = _practice_targets(env, database.dsn, dsn_23ai)
        return cls(
            host=host,
            port=port,
            data_dir=data_dir,
            state_file=Path(env.get("STUDY_STATE_FILE") or data_dir / "progress.json").expanduser(),
            database=database,
            database_23ai=DatabaseTarget(
                env.get("STUDY_USER_23AI", user), dsn_23ai,
                resolve_secret("STUDY_PASSWORD_23AI", env) or password,
            ) if dsn_23ai else None,
            state_database=_state_database(env, database, shared_schema=not practice),
            legacy_basic_auth=bool(env.get("STUDY_AUTH_PASSWORD") or env.get("STUDY_AUTH_PASSWORD_FILE")),
            public_url=_public_url(env, f"http://{host}:{port}"),
            trust_proxy=env.get("STUDY_TRUST_PROXY", "").lower() in ("1", "true", "yes"),
            google=_google(env),
            admin_email=(env.get("STUDY_ADMIN_EMAIL") or "").strip().lower() or None,
            admin_password=resolve_secret("STUDY_ADMIN_PASSWORD", env),
            registration_open=_registration_open(env),
            max_users=_integer(env, "STUDY_MAX_USERS", 25, minimum=1),
            practice=practice,
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


def _state_database(env: Mapping[str, str], study: DatabaseTarget, shared_schema: bool) -> DatabaseTarget | None:
    user = env.get("STUDY_STATE_USER")
    if not user:
        return None
    dsn = env.get("STUDY_STATE_DSN") or study.dsn
    if shared_schema and user.upper() == study.user.upper() and dsn == study.dsn:
        raise ConfigurationError("STUDY_STATE_USER must not be the learning user: SQL run in the lab could drop "
                                 "the progress tables")
    return DatabaseTarget(user, dsn, resolve_secret("STUDY_STATE_PASSWORD", env) or Secret.missing("STUDY_STATE_PASSWORD"))


def _public_url(env: Mapping[str, str], default: str) -> str:
    url = (env.get("STUDY_PUBLIC_URL") or default).rstrip("/")
    if not url.startswith(("http://", "https://")):
        raise ConfigurationError(f"STUDY_PUBLIC_URL must start with http:// or https://, got {url!r}")
    return url


def _google(env: Mapping[str, str]) -> GoogleConfig | None:
    client_id = env.get("STUDY_GOOGLE_CLIENT_ID")
    if not client_id:
        return None
    secret = resolve_secret("STUDY_GOOGLE_CLIENT_SECRET", env)
    if secret is None:
        raise ConfigurationError("STUDY_GOOGLE_CLIENT_SECRET (or _FILE) is required when STUDY_GOOGLE_CLIENT_ID is set")
    return GoogleConfig(client_id, secret)


def _registration_open(env: Mapping[str, str]) -> bool:
    mode = env.get("STUDY_REGISTRATION", "open").lower()
    if mode not in ("open", "closed"):
        raise ConfigurationError(f"STUDY_REGISTRATION must be open or closed, got {mode!r}")
    return mode == "open"


def _practice_targets(env: Mapping[str, str], dsn: str, dsn_23ai: str | None) -> dict[str, PracticeTarget]:
    targets = {"default": _practice(env, "", dsn), "23ai": _practice(env, "_23AI", dsn_23ai)}
    return {key: target for key, target in targets.items() if target}


def _practice(env: Mapping[str, str], suffix: str, dsn: str | None) -> PracticeTarget | None:
    """Practice schemas on one database; absent unless both the provisioner and the gateway user are set."""
    provisioner, gateway = env.get(f"STUDY_PROVISIONER_USER{suffix}"), env.get(f"STUDY_GATEWAY_USER{suffix}")
    if not (provisioner and gateway and dsn):
        return None
    return PracticeTarget(
        provisioner=_practice_user(env, provisioner, f"STUDY_PROVISIONER_PASSWORD{suffix}", dsn),
        gateway=_practice_user(env, gateway, f"STUDY_GATEWAY_PASSWORD{suffix}", dsn),
        tablespace=env.get(f"STUDY_PRACTICE_TABLESPACE{suffix}") or "USERS",
        quota_mb=_integer(env, f"STUDY_PRACTICE_QUOTA_MB{suffix}", 50, minimum=1),
    )


def _practice_user(env: Mapping[str, str], user: str, password_name: str, dsn: str) -> DatabaseTarget:
    return DatabaseTarget(user, dsn, resolve_secret(password_name, env) or Secret.missing(password_name))
