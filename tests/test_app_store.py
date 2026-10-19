"""Progress and personal notes in Oracle. Skipped without a test state user (see conftest)."""

import threading

import pytest

from oracle_lab.database.app_store import TABLES, OracleNotes, OracleStateStore, ensure_app_schema
from oracle_lab.database.connection import session
from oracle_lab.study.notes import NotesLibrary
from oracle_lab.study.state import new_state


@pytest.fixture
def app_schema(state_database):
    with session(state_database) as conn, conn.cursor() as cur:
        cur.execute("SELECT table_name FROM user_tables")
        for (name,) in list(cur):
            if name in TABLES:
                cur.execute(f"DROP TABLE {name} PURGE")
    assert ensure_app_schema(state_database, timeout=0)
    return state_database


def test_tables_are_created_once_and_start_with_an_empty_state(app_schema):
    store = OracleStateStore(app_schema)
    assert store.load() == new_state()
    with store.transaction() as state:
        state["settings"]["exam"] = "1Z0-171"
    assert ensure_app_schema(app_schema, timeout=0)
    assert store.load()["settings"] == {"exam": "1Z0-171"}


def test_a_failed_change_is_not_saved_and_large_states_fit(app_schema):
    store = OracleStateStore(app_schema)
    with store.transaction() as state:
        state["attempts"] = {f"q{n}": [{"ok": True, "at": 1_800_000_000, "answer": "x" * 50}] for n in range(2000)}
    with pytest.raises(ValueError), store.transaction() as state:
        state["attempts"] = {}
        raise ValueError("invalid input")
    assert len(store.load()["attempts"]) == 2000


def test_concurrent_transactions_do_not_lose_updates(app_schema):
    store = OracleStateStore(app_schema)

    def add(n):
        with store.transaction() as state:
            state["attempts"][f"q{n}"] = []

    threads = [threading.Thread(target=add, args=(n,)) for n in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(store.load()["attempts"]) == 10


def test_personal_notes_get_unique_names_and_only_saved_ones_can_be_read(app_schema, tmp_path):
    notes = NotesLibrary(tmp_path, OracleNotes(app_schema))
    first = notes.save("Outer joins", "SELECT 1 FROM dual;", 1_800_000_000)
    second = notes.save("Outer joins", "SELECT 2 FROM dual;", 1_800_000_000)
    assert first.endswith("-outer-joins.md") and second.endswith("-outer-joins-2.md")
    assert "```sql\nSELECT 2 FROM dual;\n```" in notes.read(second)
    assert [n["path"] for n in notes.list()] == [first, second]  # newest day first, like FileNotes
    assert {n["title"] for n in notes.list()} == {"My notes / Outer joins"}
    assert notes.read("personal/missing.md") is None
