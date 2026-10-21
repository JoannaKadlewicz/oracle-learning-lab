"""The Oracle stores satisfy the shared account-store contract. Skipped without a test state user."""

from __future__ import annotations

import threading

import pytest

from accounts_contract import CONTRACT, add_user
from oracle_lab.accounts.oracle_store import MIGRATIONS, migrate, oracle_stores
from oracle_lab.database.connection import session

APP_TABLES = [  # children first
    "app_audit", "app_throttle", "app_reset_tokens", "app_login_flows", "app_settings", "app_user_notes",
    "app_user_state", "app_practice_schemas", "app_sessions", "app_identities", "app_users",
]


def drop_app_tables(database):
    with session(database) as conn, conn.cursor() as cur:
        cur.execute("SELECT table_name FROM user_tables WHERE table_name LIKE 'APP\\_%' ESCAPE '\\'")
        for (name,) in list(cur):
            cur.execute(f"DROP TABLE {name} CASCADE CONSTRAINTS PURGE")


@pytest.fixture(scope="module")
def schema(state_database):
    drop_app_tables(state_database)  # a clean run, whatever an earlier version left
    migrate(state_database)
    return state_database


@pytest.fixture
def stores(schema, state_database):
    with session(state_database) as conn, conn.cursor() as cur:
        for table in APP_TABLES:
            cur.execute(f"DELETE FROM {table}")
        conn.commit()
    return oracle_stores(state_database)


@pytest.mark.parametrize("check", CONTRACT, ids=lambda f: f.__name__)
def test_contract(check, stores):
    check(stores)


def test_migrate_twice_is_a_no_op(schema, state_database):
    migrate(state_database)
    migrate(state_database)
    with session(state_database) as conn, conn.cursor() as cur:
        cur.execute("SELECT version FROM app_schema_version")
        assert cur.fetchall() == [(len(MIGRATIONS),)]


def test_user_state_rows_are_locked_per_user(stores):
    add_user(stores, "a")
    add_user(stores, "b")
    holding, release, entered = threading.Event(), threading.Event(), threading.Event()
    errors: list[BaseException] = []

    def hold():
        try:
            with stores.states.for_user("a").transaction() as state:
                state["settings"]["by"] = "holder"
                holding.set()
                release.wait(20)
        except BaseException as e:  # noqa: BLE001
            errors.append(e)

    def same_user():
        with stores.states.for_user("a").transaction() as state:
            entered.set()
            state["settings"]["second"] = True

    holder = threading.Thread(target=hold)
    holder.start()
    assert holding.wait(20)
    with stores.states.for_user("b").transaction() as state:  # another user never waits
        state["settings"]["x"] = 1
    waiter = threading.Thread(target=same_user)
    waiter.start()
    assert not entered.wait(1.0)  # the same user queues behind the open transaction
    release.set()
    holder.join(20)
    waiter.join(20)
    assert entered.is_set() and not errors
    assert stores.states.for_user("a").load()["settings"] == {"by": "holder", "second": True}
    assert stores.states.for_user("b").load()["settings"] == {"x": 1}


def test_failed_transaction_is_not_saved_and_large_states_fit(stores):
    add_user(stores, "u1")
    state_store = stores.states.for_user("u1")
    with state_store.transaction() as state:
        state["attempts"] = {f"q{n}": [{"ok": True, "answer": "x" * 50}] for n in range(2000)}
    with pytest.raises(RuntimeError), state_store.transaction() as state:
        state["attempts"] = {}
        raise RuntimeError
    assert len(state_store.load()["attempts"]) == 2000


def test_empty_strings_survive_although_oracle_stores_them_as_null(stores):
    from oracle_lab.auth.models import AuditEvent, SessionRecord

    add_user(stores, "u1")
    stores.sessions.add(SessionRecord("t", "u1", "csrf", 1.0, 1.0, 9.0, "", ""))
    stores.audit.add(AuditEvent(1.0, "login", "ok", None, "", "", {}))
    stores.settings.set("k", "")
    note = stores.notes.for_user("u1")
    name = note.add("n", "", "")
    rec = stores.sessions.get("t")
    assert rec is not None and (rec.ip, rec.user_agent) == ("", "")
    assert stores.audit.recent()[0].ip == ""
    assert stores.settings.get("k") == ""
    assert note.read(name) == "" and note.entries() == [(name, "")]


def test_first_state_transactions_of_a_new_user_do_not_race(stores):
    add_user(stores, "u1")
    barrier, errors = threading.Barrier(6), []

    def first():
        try:
            barrier.wait(20)
            with stores.states.for_user("u1").transaction() as state:
                state["n"] = state.get("n", 0) + 1
        except BaseException as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=first) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    assert not errors
    assert stores.states.for_user("u1").load()["n"] == 6


def test_migrate_resumes_after_a_partial_run(state_database):
    drop_app_tables(state_database)
    with session(state_database) as conn, conn.cursor() as cur:
        cur.execute("CREATE TABLE app_users (id VARCHAR2(64) PRIMARY KEY)")  # as left by a failed first run
    migrate(state_database)
    with session(state_database) as conn, conn.cursor() as cur:
        cur.execute("SELECT version FROM app_schema_version")
        assert cur.fetchall() == [(len(MIGRATIONS),)]
        cur.execute("SELECT COUNT(*) FROM user_tables WHERE table_name LIKE 'APP\\_%' ESCAPE '\\'")
        assert cur.fetchone()[0] == 12


def test_migrations_need_no_create_sequence():
    """Identity columns need CREATE SEQUENCE, which the state user does not have (CREATE SESSION, CREATE TABLE)."""
    from oracle_lab.accounts.oracle_store import next_seq

    assert not any("IDENTITY" in s.upper() or "SEQUENCE" in s.upper() for m in MIGRATIONS for s in m)
    values = [next_seq() for _ in range(1000)]
    assert values == sorted(set(values))
