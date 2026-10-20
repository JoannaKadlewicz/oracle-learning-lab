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
