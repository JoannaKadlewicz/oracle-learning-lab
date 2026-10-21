"""The database-engine boundary: the engine registry and routing exams to databases by key."""

from conftest import FakeEngine
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
    monkeypatch.setitem(engines.ENGINES, "fake", FakeEngine())
    assert DatabaseCatalog({"default": object()}).for_exam("PG-1") is None


def test_a_fake_engine_and_exam_added_through_the_registry_alone(monkeypatch, serve):
    """The spec's check: a new engine and exam, registered and nothing else, reach the exam list,
    the routing and the validator."""
    import json

    from oracle_lab import content
    from oracle_lab.provisioning.practice import NOT_SET_UP
    from oracle_lab.tools.validate_content import exams_to_check

    fake = exams.Exam(code="PG-1", name="PostgreSQL SQL", product="PostgreSQL", engine="fake", database="pg16",
                      database_label="PostgreSQL 16", fallback=None, versions=(16, None), pack="fake-sql",
                      questions=1, minutes=1, passing_pct=1, about="")
    pack = content.Pack(id="fake-sql", topics={}, sections={}, objectives={}, topic_exams={}, section_exams={},
                        topic_needs={}, notes=(), home_notes=(), questions=[], flashcards=[], labs=[])
    monkeypatch.setitem(engines.ENGINES, "fake", FakeEngine())
    monkeypatch.setitem(exams.EXAMS, "PG-1", fake)
    monkeypatch.setitem(content.PACKS, "fake-sql", pack)

    http = serve().sign_in()  # the first account is the admin, who falls back to the shared database
    assert "PG-1" in json.loads(http("/api/content")[2])["exams"]
    assert http("/api/settings", {"exam": "PG-1"})[0] == 200
    body = json.loads(http("/api/content")[2])
    assert body["exam"]["product"] == "PostgreSQL"
    assert body["engine"] == {"name": "fake", "label": "Fake SQL", "editor_mode": "text/x-sql"}

    assert DatabaseCatalog({"default": object()}).for_exam("PG-1") is None
    status, _, raw = http("/api/schema")
    assert status == 503 and json.loads(raw)["error"] == NOT_SET_UP

    assert exams_to_check("16.4", engine="fake") == ["PG-1"]
    assert exams_to_check("16.4", engine="oracle") == []
