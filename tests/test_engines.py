"""The database-engine boundary: the engine registry and routing exams to databases by key."""

from oracle_lab import engines, exams
from oracle_lab.database.connection import DatabaseCatalog


def test_oracle_engine_registered():
    e = engines.engine("oracle")
    assert (e.name, e.label, e.editor_mode) == ("oracle", "Oracle", "text/x-plsql")
    assert engines.engine_for_exam("1Z0-171") is e and engines.engine_for_key("23ai") is e


def test_catalog_routes_by_key_with_same_engine_fallback():
    a, b = object(), object()
    assert DatabaseCatalog({"default": a, "23ai": b}).for_exam("1Z0-171") is b
    assert DatabaseCatalog({"default": a}).for_exam("1Z0-171") is a        # registry fallback
    assert DatabaseCatalog({"default": a}).for_exam("1Z0-071") is a


def test_fake_engine_exam_without_database_is_not_set_up(monkeypatch):
    fake = exams.Exam(code="PG-1", name="PG", product="PostgreSQL", engine="fake", database="pg16",
                      database_label="PostgreSQL 16", fallback=None, versions=(16, None), pack="oracle-sql",
                      questions=1, minutes=1, passing_pct=1, about="")
    monkeypatch.setitem(exams.EXAMS, "PG-1", fake)
    monkeypatch.setitem(engines.ENGINES, "fake", engines.ENGINES["oracle"])
    assert DatabaseCatalog({"default": object()}).for_exam("PG-1") is None
