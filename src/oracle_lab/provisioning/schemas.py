"""Create and drop the learners' private practice schemas (OLL_U + 10 base32 characters).

Identifiers cannot be bound in DDL, so every one that goes into a statement passes a strict
pattern first. A learner's password is random, used once in CREATE USER and never kept or logged:
learners only ever connect through the gateway (see proxy.py).
"""

from __future__ import annotations

import base64
import logging
import re
import secrets
import string
from collections.abc import Callable
from typing import Any

import oracledb

from oracle_lab.database.connection import Database, session

log = logging.getLogger(__name__)

SCHEMA_NAME = re.compile(r"^OLL_U[A-Z2-7]{10}$")
IDENTIFIER = re.compile(r"^[A-Z][A-Z0-9_$#]{0,127}$")

LEARNER_GRANTS = {
    19: ("CREATE SESSION", "CREATE TABLE", "CREATE VIEW", "CREATE SEQUENCE", "CREATE SYNONYM"),
}
LEARNER_GRANTS[23] = LEARNER_GRANTS[19] + ("CREATE DOMAIN", "CREATE PROCEDURE")

PROFILE = "OLL_LEARNER"
PROFILE_DDL = (f"CREATE PROFILE {PROFILE} LIMIT SESSIONS_PER_USER 3 CPU_PER_CALL 3000 "
               "LOGICAL_READS_PER_CALL 2000000 IDLE_TIME 15 CONNECT_TIME 120")

PROFILE_EXISTS = 2379
PROFILE_UNAVAILABLE = {1031, 2376, 2377}  # insufficient privileges; invalid or unsupported resource limit
NO_SUCH_USER = 1918
NO_DBA_VIEW = {942, 1031}

_ALPHANUMERIC = string.ascii_letters + string.digits


def schema_name() -> str:
    """A fresh, opaque practice schema name."""
    return "OLL_U" + base64.b32encode(secrets.token_bytes(10)).decode()[:10]


def checked(name: str) -> str:
    """`name` if it is a practice schema name; ValueError otherwise."""
    if not isinstance(name, str) or not SCHEMA_NAME.match(name):
        raise ValueError(f"not a practice schema name: {name!r}")
    return name


def identifier(name: str) -> str:
    """An unquoted Oracle identifier (upper-cased); ValueError for anything else, quoted names included."""
    upper = name.upper() if isinstance(name, str) else ""
    if not IDENTIFIER.match(upper):
        raise ValueError(f"not a plain Oracle identifier: {name!r}")
    return upper


def grants_for(version: str) -> tuple[str, ...]:
    """The learner's system privileges for a database version such as "19.3.0.0.0"."""
    return LEARNER_GRANTS[23 if int(version.split(".")[0]) >= 23 else 19]


def _password() -> str:
    return secrets.choice(string.ascii_letters) + "".join(secrets.choice(_ALPHANUMERIC) for _ in range(29))


def _ora_code(exc: oracledb.DatabaseError) -> int | None:
    return getattr(exc.args[0], "code", None) if exc.args else None


class SchemaProvisioner:
    """Creates and drops practice schemas as the provisioner account (`admin`)."""

    def __init__(self, admin: Database, gateway_user: str, tablespace: str, quota_mb: int,
                 sample_loader: Callable[[Database], dict[str, Any]],
                 proxy_factory: Callable[[str], Database]):
        self.admin = admin
        self.gateway_user = gateway_user
        self.tablespace = tablespace
        self.quota_mb = int(quota_mb)
        self.sample_loader = sample_loader
        self.proxy_factory = proxy_factory
        self.profile_available: bool | None = None  # None: not tried yet

    def ensure_profile(self) -> None:
        """Create the OLL_LEARNER profile unless it exists; without it, schemas are created without one."""
        try:
            with session(self.admin) as conn, conn.cursor() as cur:
                cur.execute(PROFILE_DDL)
        except oracledb.DatabaseError as exc:
            code = _ora_code(exc)
            if code == PROFILE_EXISTS:
                self.profile_available = True
            elif code in PROFILE_UNAVAILABLE:
                log.warning("profile %s is unavailable on %s, practice schemas get no resource limits: %s",
                            PROFILE, self.admin.target, exc)
                self.profile_available = False
            else:
                raise
        else:
            log.info("created profile %s on %s", PROFILE, self.admin.target)
            self.profile_available = True

    def create(self, name: str) -> None:
        """Create the user, grant it the learner privileges and the gateway, then load the sample tables.

        When a step after CREATE USER fails, the user is dropped again (best effort) and the error raised.
        """
        name = checked(name)
        tablespace, gateway = identifier(self.tablespace), identifier(self.gateway_user)
        if self.profile_available is None:
            self.ensure_profile()
        profile = f" PROFILE {PROFILE}" if self.profile_available else ""
        with session(self.admin) as conn, conn.cursor() as cur:
            cur.execute(f'CREATE USER {name} IDENTIFIED BY "{_password()}" DEFAULT TABLESPACE {tablespace} '
                        f"QUOTA {self.quota_mb}M ON {tablespace}{profile}")
            try:
                cur.execute(f"GRANT {', '.join(grants_for(conn.version))} TO {name}")
                cur.execute(f"ALTER USER {name} GRANT CONNECT THROUGH {gateway}")
                result = self.sample_loader(self.proxy_factory(name))
                if isinstance(result, dict) and result.get("ok") is False:
                    raise RuntimeError(f"loading the sample tables into {name} failed: {result.get('error')}")
            except BaseException:
                try:
                    cur.execute(f"DROP USER {name} CASCADE")
                except Exception as exc:  # noqa: BLE001 - the first error is the one to report
                    log.warning("could not drop the half-created schema %s: %s", name, exc)
                raise
        log.info("created practice schema %s on %s", name, self.admin.target)

    def drop(self, name: str) -> None:
        """Drop the schema and everything in it; a schema that is not there counts as dropped."""
        name = checked(name)
        try:
            with session(self.admin) as conn, conn.cursor() as cur:
                cur.execute(f"DROP USER {name} CASCADE")
        except oracledb.DatabaseError as exc:
            if _ora_code(exc) != NO_SUCH_USER:
                raise
            return
        log.info("dropped practice schema %s on %s", name, self.admin.target)

    def size_mb(self, name: str) -> float | None:
        """Megabytes the schema's segments take, or None when the provisioner cannot read DBA_SEGMENTS."""
        try:
            with session(self.admin) as conn, conn.cursor() as cur:
                cur.execute("SELECT SUM(bytes)/1048576 FROM dba_segments WHERE owner = :o", o=checked(name))
                value = cur.fetchone()[0]
        except oracledb.DatabaseError as exc:
            if _ora_code(exc) in NO_DBA_VIEW:
                return None
            raise
        return float(value or 0)
