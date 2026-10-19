"""The JSON state store: atomic saves, no save on failure, safe under concurrent writers."""

import json
import threading

import pytest

from oracle_lab.study.state import JsonStateStore, new_state


def test_missing_file_is_an_empty_state(tmp_path):
    assert JsonStateStore(tmp_path / "progress.json").load() == new_state()


def test_changes_are_saved_and_no_temp_files_are_left(tmp_path):
    store = JsonStateStore(tmp_path / "sub" / "progress.json")
    with store.transaction() as state:
        state["settings"]["exam"] = "1Z0-171"
    assert json.loads((tmp_path / "sub" / "progress.json").read_text())["settings"] == {"exam": "1Z0-171"}
    assert [p.name for p in (tmp_path / "sub").iterdir()] == ["progress.json"]


def test_a_failed_change_is_not_saved(tmp_path):
    store = JsonStateStore(tmp_path / "progress.json")
    with pytest.raises(ValueError), store.transaction() as state:
        state["settings"]["exam"] = "half-done"
        raise ValueError("invalid input")
    assert store.load() == new_state()


def test_concurrent_transactions_do_not_lose_updates(tmp_path):
    store = JsonStateStore(tmp_path / "progress.json")

    def add(n):
        with store.transaction() as state:
            state["attempts"][f"q{n}"] = []

    threads = [threading.Thread(target=add, args=(n,)) for n in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(store.load()["attempts"]) == 20
