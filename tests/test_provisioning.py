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
    assert create_user.startswith('CREATE USER OLL_UABCDEFGHIJ IDENTIFIED BY "')
    assert create_user.endswith('" DEFAULT TABLESPACE USERS QUOTA 50M ON USERS PROFILE OLL_LEARNER')
    password = create_user.split('"')[1]
    assert len(password) == 30 and password.isalnum() and password[0].isalpha()
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


def test_existing_profile_is_used():
    admin = FakeAdmin(fail={"CREATE PROFILE": 2379})
    prov = provisioner(admin)
    prov.ensure_profile()
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


@pytest.mark.parametrize("kwargs", [{"tablespace": 'USERS" x'}, {"tablespace": "USERS QUOTA UNLIMITED"},
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
