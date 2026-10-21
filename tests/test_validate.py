import dataclasses

import pytest

from oracle_lab import exams
from oracle_lab.database.connection import DatabaseCatalog
from oracle_lab.tools import validate_content as v


def test_exams_to_check_by_version():
    assert v.exams_to_check("19.3.0.0.0", engine="oracle") == ["1Z0-071"]
    assert v.exams_to_check("21.3.0.0.0", engine="oracle") == ["1Z0-071"]
    assert v.exams_to_check("23.5.0.24.7", engine="oracle") == ["1Z0-171"]
    assert v.exams_to_check("19.3.0.0.0", only="1Z0-171", engine="oracle") == ["1Z0-171"]


def test_exams_to_check_matches_the_engine_of_the_database():
    assert v.exams_to_check("19.3.0.0.0", engine="postgres") == []


def test_exams_to_check_unknown_exam():
    with pytest.raises(SystemExit, match="unknown exam: X"):
        v.exams_to_check("19.3.0.0.0", only="X", engine="oracle")


class FakeConnection:
    def __init__(self, version):
        self.version = version

    def rollback(self):
        pass

    def close(self):
        pass


class FakeDatabase:
    def __init__(self, version="19.3.0.0.0"):
        self.version = version

    def connect(self):
        return FakeConnection(self.version)


def test_no_matching_exam_is_a_problem(capsys):
    assert v.db_errors(FakeDatabase("18.3.0.0.0")) == ["no exam is checked on Oracle 18"]
    assert "checking the  items" not in capsys.readouterr().out


def test_banner_names_the_engine_of_the_database(capsys):
    assert v.db_errors(FakeDatabase("19.3.0.0.0"), topic="none") == []
    assert "Database: Oracle 19.3.0.0.0, checking the 1Z0-071 items of topic none." in capsys.readouterr().out


def test_an_exam_outside_the_connected_version_is_checked_with_a_warning(capsys):
    assert v.db_errors(FakeDatabase("19.3.0.0.0"), topic="none", only="1Z0-171") == []
    out = capsys.readouterr().out
    assert "Warning: 1Z0-171 is not matched to Oracle 19" in out
    assert "checking the 1Z0-171 items" in out
    v.db_errors(FakeDatabase("23.5.0.24.7"), topic="none", only="1Z0-171")
    assert "Warning" not in capsys.readouterr().out


def test_database_to_check_is_the_exams_own_database():
    default, ai = FakeDatabase("19.3.0.0.0"), FakeDatabase("23.5.0.24.7")
    both = DatabaseCatalog({"default": default, "23ai": ai})
    assert v.database_to_check(both, None) == (default, "oracle")
    assert v.database_to_check(both, "1Z0-071") == (default, "oracle")
    assert v.database_to_check(both, "1Z0-171") == (ai, "oracle")
    assert v.database_to_check(DatabaseCatalog({"default": default}), "1Z0-171") == (default, "oracle")  # its fallback


def test_database_to_check_unknown_or_unconfigured_exam(monkeypatch):
    catalog = DatabaseCatalog({"default": FakeDatabase()})
    with pytest.raises(SystemExit, match="unknown exam: X"):
        v.database_to_check(catalog, "X")
    lone = dataclasses.replace(exams.EXAMS["1Z0-171"], code="LONE-1", database="lone", fallback=None)
    monkeypatch.setitem(exams.EXAMS, "LONE-1", lone)
    with pytest.raises(SystemExit, match="LONE-1 has no database configured: set STUDY_DSN_LONE"):
        v.database_to_check(catalog, "LONE-1")


def test_ids_must_be_unique_across_packs(monkeypatch):
    from oracle_lab import content

    oracle = content.PACKS["oracle-sql"]
    question, card, lab = oracle.questions[0], oracle.flashcards[0], oracle.labs[0]
    other = dataclasses.replace(
        oracle, id="other-sql", topics={"t01": "Again", "p01": "New"}, sections={"1": "Again"},
        objectives={"1.1": "Again"}, questions=[question], flashcards=[card], labs=[lab])
    monkeypatch.setitem(content.PACKS, "other-sql", other)
    errors = v.static_errors()
    for kind, item_id in (("topic", "t01"), ("section", "1"), ("objective", "1.1"),
                          ("question", question["id"]), ("flashcard", card["id"]), ("lab", lab["id"])):
        assert f"{kind} {item_id} is in two packs: oracle-sql and other-sql" in errors
    assert not any("p01" in e for e in errors)
