"""The SQLite stores satisfy the shared account-store contract, and survive threads and restarts."""

from __future__ import annotations

import sqlite3
import threading
from contextlib import closing

import pytest

from accounts_contract import CONTRACT, add_user, make_user, password_identity
from oracle_lab.accounts.sqlite_store import MIGRATIONS, sqlite_stores


@pytest.mark.parametrize("check", CONTRACT, ids=lambda f: f.__name__)
def test_contract(check, tmp_path):
    check(sqlite_stores(tmp_path / "app.db"))


def test_concurrent_transactions_do_not_lose_updates(tmp_path):
    stores = sqlite_stores(tmp_path / "app.db")
    add_user(stores, "u1")

    def bump():
        for _ in range(50):
            with stores.states.for_user("u1").transaction() as s:
                s.setdefault("n", 0)
                s["n"] += 1

    threads = [threading.Thread(target=bump) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert stores.states.for_user("u1").load()["n"] == 200


def test_failed_transaction_is_not_saved(tmp_path):
    stores = sqlite_stores(tmp_path / "app.db")
    add_user(stores, "u1")
    with pytest.raises(RuntimeError), stores.states.for_user("u1").transaction() as s:
        s["settings"]["x"] = 1
        raise RuntimeError
    assert stores.states.for_user("u1").load()["settings"] == {}


def test_data_survives_reopening_and_migrations_are_idempotent(tmp_path):
    path = tmp_path / "app.db"
    first = sqlite_stores(path)
    user = make_user()
    first.users.add(user, password_identity(user))
    second = sqlite_stores(path)
    assert second.users.get(user.id) == user
    with closing(sqlite3.connect(path)) as conn:
        versions = conn.execute("SELECT version FROM app_schema_version ORDER BY version").fetchall()
        assert versions == [(n,) for n in range(1, len(MIGRATIONS) + 1)]  # each applied once


def test_audit_detail_round_trips_as_json(tmp_path):
    from oracle_lab.auth.models import AuditEvent

    stores = sqlite_stores(tmp_path / "app.db")
    event = AuditEvent(1.0, "login", "ok", None, "ip", "ua", {"a": [1, 2], "b": "x"})
    stores.audit.add(event)
    assert stores.audit.recent() == [event]
