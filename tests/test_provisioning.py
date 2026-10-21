"""Private learner schemas, without a database: names, identifier checks, grants and the DDL sent."""

import logging

import oracledb
import pytest

from oracle_lab.config import DatabaseTarget
from oracle_lab.credentials import Secret
from oracle_lab.provisioning.proxy import ProxyDatabase
from oracle_lab.provisioning.schemas import (
    LEARNER_GRANTS,
    PROFILE_DDL,
    PROFILE_UPDATE_DDL,
    SCHEMA_NAME,
    SchemaProvisioner,
    checked,
    grants_for,
    schema_name,
)

TARGET = DatabaseTarget("prov", "db:1521/x", Secret.from_value("pw", "test"))


def test_schema_names_are_opaque_and_valid():
    names = [schema_name() for _ in range(1000)]
    assert all(SCHEMA_NAME.match(name) for name in names)
    assert len(set(names)) == 1000


def test_checked_rejects_injection():
    with pytest.raises(ValueError):
        checked("OLL_U1; DROP USER x")
    with pytest.raises(ValueError):
        checked("oll_uabcdefghij")
    with pytest.raises(ValueError):
        checked("OLL_UABCDEFGHIJ\n")
    assert checked("OLL_UABCDEFGH23") == "OLL_UABCDEFGH23"


def test_grants_by_version():
    assert LEARNER_GRANTS[19] == ("CREATE SESSION", "CREATE TABLE", "CREATE VIEW", "CREATE SEQUENCE", "CREATE SYNONYM")
    assert LEARNER_GRANTS[23] == LEARNER_GRANTS[19] + ("CREATE DOMAIN", "CREATE PROCEDURE")
    assert grants_for("19.3.0.0.0") == LEARNER_GRANTS[19]
    assert grants_for("23.5.0.24.7") == LEARNER_GRANTS[23]
    assert grants_for("26.1.0.0.0") == LEARNER_GRANTS[23]


# --- the DDL, against a recording fake ---

class FakeAdmin:
    """Records the statements run on it; `fail` maps a statement prefix to the ORA code it raises."""

    def __init__(self, version="19.3.0.0.0", fail=None):
        self.target = TARGET
        self.version = version
        self.fail = dict(fail or {})
        self.statements: list[str] = []

    def connect(self):
        return FakeConnection(self)


class FakeConnection:
    def __init__(self, admin):
        self.admin = admin
        self.version = admin.version

    def cursor(self):
        return FakeCursor(self.admin)

    def rollback(self):
        pass

    def close(self):
        pass


class FakeCursor:
    def __init__(self, admin):
        self.admin = admin

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, *args, **kwargs):
        self.admin.statements.append(sql)
        for prefix, code in self.admin.fail.items():
            if sql.startswith(prefix):
                raise _ora(code)

    def fetchone(self):
        return (None,)


class _Error:
    """Stands in for python-oracledb's error object, the first argument of a DatabaseError."""

    def __init__(self, code):
        self.code, self.full_code, self.message = code, f"ORA-{code:05d}", f"ORA-{code:05d}: simulated"

    def __str__(self):
        return self.message


def _ora(code):
    return oracledb.DatabaseError(_Error(code))


def provisioner(admin, loaded=None, **kwargs):
    loaded = [] if loaded is None else loaded
    return SchemaProvisioner(admin, kwargs.pop("gateway", "oll_gateway"), kwargs.pop("tablespace", "users"),
                             kwargs.pop("quota_mb", 50),
                             sample_loader=kwargs.pop("sample_loader", lambda db: loaded.append(db) or {"ok": True}),
                             proxy_factory=lambda name: f"proxy:{name}")


def test_create_runs_the_steps_in_order():
    admin, loaded = FakeAdmin(), []
    provisioner(admin, loaded).create("OLL_UABCDEFGHIJ")
    create_user, *rest = admin.statements[1:]
    assert admin.statements[0] == PROFILE_DDL
    assert create_user == ("CREATE USER OLL_UABCDEFGHIJ NO AUTHENTICATION DEFAULT TABLESPACE USERS "
                           "QUOTA 50M ON USERS PROFILE OLL_LEARNER")
    assert rest == [f"GRANT {', '.join(LEARNER_GRANTS[19])} TO OLL_UABCDEFGHIJ",
                    "ALTER USER OLL_UABCDEFGHIJ GRANT CONNECT THROUGH OLL_GATEWAY"]
    assert loaded == ["proxy:OLL_UABCDEFGHIJ"]


def test_create_grants_the_23ai_privileges_on_23ai():
    admin = FakeAdmin(version="23.5.0.24.7")
    provisioner(admin).create("OLL_UABCDEFGHIJ")
    assert f"GRANT {', '.join(LEARNER_GRANTS[23])} TO OLL_UABCDEFGHIJ" in admin.statements


@pytest.mark.parametrize("code", [1031, 2376, 2377])
def test_unavailable_profile_is_left_out(code, caplog):
    admin = FakeAdmin(fail={"CREATE PROFILE": code})
    prov = provisioner(admin)
    with caplog.at_level(logging.WARNING):
        prov.ensure_profile()
    assert "OLL_LEARNER" in caplog.text
    prov.create("OLL_UABCDEFGHIJ")
    create_user = next(s for s in admin.statements if s.startswith("CREATE USER"))
    assert "PROFILE" not in create_user


def test_profile_never_locks_or_expires_accounts():
    assert "FAILED_LOGIN_ATTEMPTS UNLIMITED" in PROFILE_DDL
    assert "PASSWORD_LIFE_TIME UNLIMITED" in PROFILE_DDL


def test_existing_profile_is_used_and_brought_up_to_date():
    admin = FakeAdmin(fail={"CREATE PROFILE": 2379})
    prov = provisioner(admin)
    prov.ensure_profile()
    assert admin.statements[-1] == PROFILE_UPDATE_DDL
    prov.create("OLL_UABCDEFGHIJ")
    assert next(s for s in admin.statements if s.startswith("CREATE USER")).endswith("PROFILE OLL_LEARNER")


@pytest.mark.parametrize("code", [1031, 2376, 2377])
def test_existing_profile_that_cannot_be_altered_is_still_used(code, caplog):
    admin = FakeAdmin(fail={"CREATE PROFILE": 2379, "ALTER PROFILE": code})
    prov = provisioner(admin)
    with caplog.at_level(logging.WARNING):
        prov.ensure_profile()
    assert f"ORA-{code:05d}" in caplog.text
    prov.create("OLL_UABCDEFGHIJ")
    assert next(s for s in admin.statements if s.startswith("CREATE USER")).endswith("PROFILE OLL_LEARNER")


def test_other_profile_errors_are_raised():
    with pytest.raises(oracledb.DatabaseError):
        provisioner(FakeAdmin(fail={"CREATE PROFILE": 1017})).ensure_profile()


def test_failed_step_drops_the_half_made_user():
    def broken(db):
        return {"ok": False, "error": "seed: ORA-01536"}

    admin = FakeAdmin()
    with pytest.raises(RuntimeError, match="ORA-01536"):
        provisioner(admin, sample_loader=broken).create("OLL_UABCDEFGHIJ")
    assert admin.statements[-1] == "DROP USER OLL_UABCDEFGHIJ CASCADE"


def test_failed_create_user_drops_nothing():
    admin = FakeAdmin(fail={"CREATE USER": 1920})
    with pytest.raises(oracledb.DatabaseError):
        provisioner(admin).create("OLL_UABCDEFGHIJ")
    assert not any(s.startswith("DROP USER") for s in admin.statements)


@pytest.mark.parametrize("kwargs", [{"tablespace": "USERS\n"}, {"gateway": "GW\n"},
                                    {"tablespace": 'USERS" x'}, {"tablespace": "USERS QUOTA UNLIMITED"},
                                    {"gateway": "GW; DROP USER SYS"}, {"tablespace": '"users"'}])
def test_bad_identifiers_are_refused_before_any_sql(kwargs):
    admin = FakeAdmin()
    with pytest.raises(ValueError):
        provisioner(admin, **kwargs).create("OLL_UABCDEFGHIJ")
    assert not any(s.startswith("CREATE USER") for s in admin.statements)


def test_create_and_drop_refuse_bad_schema_names():
    admin = FakeAdmin()
    with pytest.raises(ValueError):
        provisioner(admin).create("SYSTEM")
    with pytest.raises(ValueError):
        provisioner(admin).drop("SYSTEM")
    assert admin.statements == []


def test_drop_ignores_a_missing_user():
    admin = FakeAdmin(fail={"DROP USER": 1918})
    provisioner(admin).drop("OLL_UABCDEFGHIJ")
    assert admin.statements == ["DROP USER OLL_UABCDEFGHIJ CASCADE"]


@pytest.mark.parametrize("code", [942, 1031])
def test_size_is_unknown_without_dba_segments(code):
    assert provisioner(FakeAdmin(fail={"SELECT": code})).size_mb("OLL_UABCDEFGHIJ") is None


def test_size_of_an_empty_schema_is_zero():
    assert provisioner(FakeAdmin()).size_mb("OLL_UABCDEFGHIJ") == 0.0


def test_proxy_database_targets_the_schema_and_checks_it():
    gateway = DatabaseTarget("oll_gateway", "db:1521/x", Secret.from_value("pw", "test"))
    db = ProxyDatabase(gateway, "OLL_UABCDEFGHIJ")
    assert str(db.target) == "OLL_UABCDEFGHIJ@db:1521/x"
    with pytest.raises(ValueError):
        ProxyDatabase(gateway, "SYSTEM")


def test_proxy_database_connects_as_the_gateway_on_behalf_of_the_schema(monkeypatch):
    calls = []

    class Conn:
        call_timeout = None

        def cursor(self):
            return FakeCursor(FakeAdmin())

    def connect(**kwargs):
        calls.append(kwargs)
        return Conn()

    monkeypatch.setattr(oracledb, "connect", connect)
    gateway = DatabaseTarget("oll_gateway", "db:1521/x", Secret.from_value("gw-secret", "test"))
    conn = ProxyDatabase(gateway, "OLL_UABCDEFGHIJ", call_timeout_ms=1234).connect()
    assert calls == [{"user": "oll_gateway[OLL_UABCDEFGHIJ]", "password": "gw-secret", "dsn": "db:1521/x"}]
    assert conn.call_timeout == 1234


def test_init_db_ensures_the_profile_on_each_practice_target_and_survives_failures(monkeypatch, caplog, tmp_path):
    from oracle_lab import cli
    from oracle_lab.config import Settings

    settings = Settings.from_env({
        "STUDY_DATA_DIR": str(tmp_path), "STUDY_PASSWORD": "unused", "STUDY_DSN": "db:1521/a",
        "STUDY_DSN_23AI": "db:1522/b", "STUDY_PASSWORD_23AI": "unused",
        "STUDY_PROVISIONER_USER": "prov", "STUDY_PROVISIONER_PASSWORD": "p",
        "STUDY_GATEWAY_USER": "gw", "STUDY_GATEWAY_PASSWORD": "g",
        "STUDY_PROVISIONER_USER_23AI": "prov", "STUDY_PROVISIONER_PASSWORD_23AI": "p",
        "STUDY_GATEWAY_USER_23AI": "gw", "STUDY_GATEWAY_PASSWORD_23AI": "g",
    })
    assert set(settings.practice) == {"default", "23ai"}
    seen = []

    def ensure_profile(self):
        seen.append(self.admin.target.dsn)
        raise oracledb.DatabaseError("ORA-12541: no listener")

    monkeypatch.setattr(SchemaProvisioner, "ensure_profile", ensure_profile)
    with caplog.at_level(logging.WARNING):
        cli._ensure_profiles(settings)
    assert sorted(seen) == ["db:1521/a", "db:1522/b"]
    assert caplog.text.count("ORA-12541") == 2


def test_start_up_warns_when_practice_schemas_are_off(tmp_path, caplog):
    from conftest import settings_for
    from oracle_lab.accounts.memory import memory_stores
    from oracle_lab.bootstrap import build_app

    warning = ("Practice schemas are off (STUDY_PROVISIONER_* / STUDY_GATEWAY_* not set): learners can't run SQL; "
               "admins use the shared schema.")
    with caplog.at_level(logging.WARNING):
        build_app(settings_for(tmp_path), stores=memory_stores(), maintenance=False)
    assert warning in caplog.text
    caplog.clear()
    practice = {"STUDY_PROVISIONER_USER": "prov", "STUDY_PROVISIONER_PASSWORD": "p", "STUDY_GATEWAY_USER": "gw",
                "STUDY_GATEWAY_PASSWORD": "g"}
    with caplog.at_level(logging.WARNING):
        build_app(settings_for(tmp_path, **practice), stores=memory_stores(), maintenance=False)
    assert "Practice schemas are off" not in caplog.text


def test_build_app_without_maintenance_starts_no_thread(tmp_path):
    import threading

    from conftest import settings_for
    from oracle_lab.accounts.memory import memory_stores
    from oracle_lab.bootstrap import build_app

    before = {t.ident for t in threading.enumerate() if t.name == "maintenance"}
    build_app(settings_for(tmp_path), stores=memory_stores(), maintenance=False)
    assert {t.ident for t in threading.enumerate() if t.name == "maintenance"} == before
