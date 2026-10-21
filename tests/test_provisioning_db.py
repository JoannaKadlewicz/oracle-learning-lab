"""Private learner schemas on a real database (skipped without `provisioner_database`)."""

import oracledb
import pytest

from oracle_lab.database.connection import OracleDatabase, session
from oracle_lab.database.sample_schema import SampleSchema
from oracle_lab.provisioning.proxy import ProxyDatabase
from oracle_lab.provisioning.schemas import SchemaProvisioner, schema_name


def load_sample(db):
    result = SampleSchema(db).reset()
    if not result["ok"]:
        raise RuntimeError(result["error"])
    return result


@pytest.fixture
def practice(provisioner_database):
    """(provisioner factory, new_name()); every schema named here is dropped afterwards, even on failure."""
    target = provisioner_database
    names = []

    def make(sample_loader=load_sample):
        return SchemaProvisioner(OracleDatabase(target.provisioner), target.gateway.user, target.tablespace,
                                 target.quota_mb, sample_loader=sample_loader,
                                 proxy_factory=lambda name: ProxyDatabase(target.gateway, name))

    def new_name():
        names.append(schema_name())
        return names[-1]

    yield make, new_name
    cleaner = make()
    for name in names:
        cleaner.drop(name)


def scalar(db, sql):
    with session(db) as conn, conn.cursor() as cur:
        cur.execute(sql)
        return cur.fetchone()[0]


def test_create_connect_through_gateway_and_drop(practice, provisioner_database):
    make, new_name = practice
    provisioner, name = make(), new_name()
    provisioner.create(name)
    learner = ProxyDatabase(provisioner_database.gateway, name)
    assert scalar(learner, "SELECT USER FROM dual") == name
    assert scalar(learner, "SELECT COUNT(*) FROM employees") > 0
    size = provisioner.size_mb(name)  # None when the provisioner cannot read DBA_SEGMENTS
    assert size is None or size > 0

    provisioner.drop(name)
    with pytest.raises(oracledb.DatabaseError):
        learner.connect().close()
    provisioner.drop(name)  # dropping again is fine


def test_learner_schema_has_no_direct_login(practice, provisioner_database):
    make, new_name = practice
    name = new_name()
    make().create(name)
    for password in ("x", name, "Abcdefghij1234567890Abcdefghij"):
        with pytest.raises(oracledb.DatabaseError):
            oracledb.connect(user=name, password=password, dsn=provisioner_database.provisioner.dsn).close()
    # the failed attempts lock nothing: the gateway still gets in
    assert scalar(ProxyDatabase(provisioner_database.gateway, name), "SELECT USER FROM dual") == name


def test_learner_cannot_see_other_learners_tables(practice, provisioner_database):
    make, new_name = practice
    provisioner, a, b = make(), new_name(), new_name()
    provisioner.create(a)
    provisioner.create(b)
    with pytest.raises(oracledb.DatabaseError, match="ORA-00942"):
        scalar(ProxyDatabase(provisioner_database.gateway, a), f"SELECT * FROM {b}.employees")


def test_retry_after_failure_recreates(practice, provisioner_database):
    make, new_name = practice
    name, calls = new_name(), []

    def flaky(db):
        calls.append(db)
        if len(calls) == 1:
            raise RuntimeError("simulated failure while loading the sample")
        return load_sample(db)

    provisioner = make(sample_loader=flaky)
    with pytest.raises(RuntimeError):
        provisioner.create(name)
    provisioner.drop(name)
    provisioner.create(name)
    assert scalar(ProxyDatabase(provisioner_database.gateway, name), "SELECT COUNT(*) FROM employees") > 0


def test_sql_lab_runs_in_the_users_own_schema(provisioner_database, serve, tmp_path):
    """End to end: sign-up provisions the default schema in the background; /api/run then runs in it."""
    import dataclasses
    import json
    import threading
    import time

    from conftest import settings_for

    from oracle_lab.accounts.memory import memory_stores
    from oracle_lab.bootstrap import build_provisioner

    stores = memory_stores()
    settings = dataclasses.replace(settings_for(tmp_path), practice={"default": provisioner_database})
    try:
        server = serve(settings, stores=stores)
        server.sign_in("admin@x.org")
        learner = type(server)(server.port).sign_in("learner@x.org")
        deadline = time.time() + 180
        while True:
            status, _, body = learner("/api/run", {"sql": "SELECT COUNT(*) FROM employees;\nSELECT USER FROM dual;"})
            if status != 503 or time.time() > deadline:
                break
            assert json.loads(body)["practice"] == "unavailable"
            time.sleep(1)
        assert status == 200, body
        count, user = json.loads(body)["results"]
        assert int(count["rows"][0][0]) > 0
        learner_id = stores.users.by_email("learner@x.org").id
        assert user["rows"][0][0] == stores.schemas.get(learner_id, "default").schema_name
    finally:
        for thread in threading.enumerate():
            if thread.name.startswith("provision-"):
                thread.join(300)
        cleaner = build_provisioner(provisioner_database)
        for rec in stores.schemas.all():
            cleaner.drop(rec.schema_name)
