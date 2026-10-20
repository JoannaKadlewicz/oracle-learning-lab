"""The legacy single-user tables, and the schema bootstrap. Skipped without a test state user (see conftest)."""

import pytest

from oracle_lab.database.app_store import LegacyOracleNotes, LegacyOracleState, ensure_app_schema
from oracle_lab.database.connection import session
from oracle_lab.study.state import new_state

LEGACY_TABLES = {
    "LAB_STATE": "CREATE TABLE lab_state (id NUMBER(1) PRIMARY KEY, doc CLOB NOT NULL CHECK (doc IS JSON))",
    "LAB_NOTES": "CREATE TABLE lab_notes (name VARCHAR2(100) PRIMARY KEY, title VARCHAR2(200) NOT NULL, body CLOB NOT NULL)",
}


@pytest.fixture
def legacy_tables(state_database):
    with session(state_database) as conn, conn.cursor() as cur:
        cur.execute("SELECT table_name FROM user_tables")
        for (name,) in list(cur):
            if name in LEGACY_TABLES:
                cur.execute(f"DROP TABLE {name} PURGE")
        for ddl in LEGACY_TABLES.values():
            cur.execute(ddl)
    return state_database


def test_ensure_app_schema_migrates_and_leaves_legacy_tables_alone(legacy_tables):
    with session(legacy_tables) as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO lab_notes (name, title, body) VALUES ('a.md', 'A', 'body')")
        conn.commit()
    assert ensure_app_schema(legacy_tables, timeout=0)
    assert ensure_app_schema(legacy_tables, timeout=0)
    with session(legacy_tables) as conn, conn.cursor() as cur:
        cur.execute("SELECT table_name FROM user_tables WHERE table_name IN ('APP_USERS', 'APP_SCHEMA_VERSION')")
        assert {name for (name,) in cur} == {"APP_USERS", "APP_SCHEMA_VERSION"}
        cur.execute("SELECT COUNT(*) FROM lab_notes")
        assert cur.fetchone()[0] == 1


def test_legacy_state_is_read_and_defaults_to_a_new_state(legacy_tables):
    reader = LegacyOracleState(legacy_tables)
    assert reader.load() == new_state()
    with session(legacy_tables) as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO lab_state (id, doc) VALUES (1, :doc)", doc='{"settings": {"exam": "1Z0-171"}}')
        conn.commit()
    assert reader.load()["settings"] == {"exam": "1Z0-171"}


def test_legacy_notes_are_listed_newest_name_first_and_read(legacy_tables):
    with session(legacy_tables) as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO lab_notes (name, title, body) VALUES ('2026-01-01-a.md', 'A', 'first')")
        cur.execute("INSERT INTO lab_notes (name, title, body) VALUES ('2026-02-01-b.md', 'B', 'second')")
        conn.commit()
    notes = LegacyOracleNotes(legacy_tables)
    assert notes.entries() == [("2026-02-01-b.md", "B"), ("2026-01-01-a.md", "A")]
    assert notes.read("2026-01-01-a.md") == "first"
    assert notes.read("missing.md") is None
