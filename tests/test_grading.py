from oracle_lab.grading.comparison import compare_results, diff_rows

LAB = {"columns": "id, name", "ordered": True}
UNORDERED = {"columns": "id, name", "ordered": False}
ROWS = [["1", "a"], ["2", "b"]]


def test_identical_result_passes():
    result = compare_results(LAB, ["ID", "NAME"], ROWS, ["ID", "NAME"], ROWS)
    assert result["passed"]
    assert result["feedback"] == []
    assert result["expected_rows"] is None


def test_wrong_column_count_fails():
    result = compare_results(LAB, ["ID"], [["1"], ["2"]], ["ID", "NAME"], ROWS)
    assert not result["passed"]
    assert "Expected 2 columns" in result["feedback"][0]
    assert result["expected_rows"] == ROWS


def test_wrong_row_count_fails():
    result = compare_results(LAB, ["ID", "NAME"], ROWS[:1], ["ID", "NAME"], ROWS)
    assert not result["passed"]
    assert result["feedback"] == ["Expected 2 rows, got 1."]


def test_wrong_values_fail_and_show_a_missing_row():
    got = [["1", "a"], ["2", "x"]]
    result = compare_results(LAB, ["ID", "NAME"], got, ["ID", "NAME"], ROWS)
    assert not result["passed"]
    assert result["feedback"][-1].endswith("2, b")


def test_duplicates_count():
    got = [["1", "a"], ["1", "a"]]
    assert not compare_results(UNORDERED, ["ID", "NAME"], got, ["ID", "NAME"], ROWS)["passed"]


def test_null_differs_from_the_string_null():
    got = [["1", "NULL"], ["2", "b"]]
    want = [["1", None], ["2", "b"]]
    result = compare_results(LAB, ["ID", "NAME"], got, ["ID", "NAME"], want)
    assert not result["passed"]
    assert result["feedback"][-1].endswith("1, NULL")


def test_wrong_order_fails_when_order_is_graded():
    result = compare_results(LAB, ["ID", "NAME"], ROWS[::-1], ["ID", "NAME"], ROWS)
    assert not result["passed"]
    assert "wrong order" in result["feedback"][0]


def test_any_order_passes_when_order_is_not_graded():
    assert compare_results(UNORDERED, ["ID", "NAME"], ROWS[::-1], ["ID", "NAME"], ROWS)["passed"]


def test_different_aliases_pass_with_a_note():
    result = compare_results(LAB, ["X", "Y"], ROWS, ["ID", "NAME"], ROWS)
    assert result["passed"]
    assert "aliases are not graded" in result["feedback"][0]


def statuses(diff):
    return [(d["status"], d["cells"]) for d in diff]


def test_diff_marks_extra_and_missing_rows():
    diff = diff_rows([["1", "a"], ["3", "c"]], [["1", "a"], ["2", "b"]], ordered=False)
    assert statuses(diff) == [("ok", ["1", "a"]), ("extra", ["3", "c"]), ("missing", ["2", "b"])]


def test_diff_pairs_a_row_with_one_wrong_cell():
    diff = diff_rows([["1", "a"], ["2", "x"]], ROWS, ordered=True)
    assert diff[1] == {"status": "changed", "cells": ["2", "x"], "expected": ["2", "b"], "diff": [1]}
    assert len(diff) == 2


def test_diff_shows_rows_in_the_wrong_position():
    diff = diff_rows(ROWS[::-1], ROWS, ordered=True)
    assert [d["status"] for d in diff] == ["moved", "moved"]


def test_diff_treats_null_and_the_string_null_as_different():
    diff = diff_rows([["1", "NULL"]], [["1", None]], ordered=False)
    assert diff[0]["status"] == "changed" and diff[0]["diff"] == [1]


def test_failed_result_includes_the_diff():
    result = compare_results(LAB, ["ID", "NAME"], [["1", "a"], ["2", "x"]], ["ID", "NAME"], ROWS)
    assert [d["status"] for d in result["diff"]] == ["ok", "changed"]
