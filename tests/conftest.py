"""Shared fixtures. Tests that need Oracle take the `database` fixture and are skipped without one.

The database comes from the same STUDY_* settings as the app (see oracle_lab.config).
"""

import pytest

from oracle_lab.config import Settings
from oracle_lab.database.connection import OracleDatabase


@pytest.fixture(scope="session")
def database():
    db = OracleDatabase(Settings.from_env().database)
    try:
        db.connect().close()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"database not reachable: {exc}")
    return db
