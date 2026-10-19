"""Shared fixtures. Tests that need Oracle take the `database` fixture and are skipped without one.

The database comes from the same STUDY_* settings as the app (see oracle_lab.config). The tests of
the Oracle state store take `state_database`, a user of its own that they empty: STUDY_TEST_STATE_USER
and STUDY_TEST_STATE_PASSWORD[_FILE], on STUDY_TEST_STATE_DSN (default: STUDY_DSN). Never point it at
the user that keeps your progress.
"""

import os

import pytest

from oracle_lab.config import DatabaseTarget, Settings
from oracle_lab.credentials import resolve_secret
from oracle_lab.database.connection import OracleDatabase


@pytest.fixture(scope="session")
def database():
    db = OracleDatabase(Settings.from_env().database)
    try:
        db.connect().close()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"database not reachable: {exc}")
    return db


@pytest.fixture(scope="session")
def state_database():
    user, password = os.environ.get("STUDY_TEST_STATE_USER"), resolve_secret("STUDY_TEST_STATE_PASSWORD")
    if not user or password is None:
        pytest.skip("STUDY_TEST_STATE_USER / STUDY_TEST_STATE_PASSWORD not set")
    dsn = os.environ.get("STUDY_TEST_STATE_DSN") or Settings.from_env().database.dsn
    db = OracleDatabase(DatabaseTarget(user, dsn, password))
    try:
        db.connect().close()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"state database not reachable: {exc}")
    return db
