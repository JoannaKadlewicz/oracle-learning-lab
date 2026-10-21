"""Localized content: overlays, notes siblings, error explanations, server-built feedback, translation checks."""

import copy
import json

import pytest

from oracle_lab import bootstrap, content
from oracle_lab.analysis import error_hints, visualizer
from oracle_lab.content import i18n as overlays
from oracle_lab.database.executor import Transaction, client_command_result
from oracle_lab.grading import labs
from oracle_lab.grading.comparison import compare_results
from oracle_lab.sqltext.statements import split_statements
from oracle_lab.study.notes import NotesLibrary
from oracle_lab.tools import validate_content as v

ALIAS_WHERE = next(q for q in content.QUESTIONS if q["id"] == "q01-alias-where")
QUOTES = next(q for q in content.QUESTIONS if q["id"] == "q01-quotes")


@pytest.fixture
def overlay_dir(tmp_path, monkeypatch):
    """write(lang, name, data) puts an overlay file in a temporary overlay directory the loader reads."""
    root = tmp_path / "overlays"
    monkeypatch.setattr(overlays, "OVERLAY_DIR", root)
    overlays.load.cache_clear()

    def write(lang, name, data):
        (root / lang).mkdir(parents=True, exist_ok=True)
        (root / lang / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False), "utf-8")
        overlays.load.cache_clear()

    yield write
    overlays.load.cache_clear()


def _by_id(items, item_id):
    return next(i for i in items if i["id"] == item_id)


# --------------------------------------------------------------------------- overlays


def test_translated_question_shows_up_without_changing_the_source(overlay_dir):
    before = copy.deepcopy(content.QUESTIONS)
    overlay_dir("pl", "t01", {"questions": {"q01-alias-where": {
        "prompt": "Które stwierdzenie o tym zapytaniu jest prawdziwe?",
        "code": "-- alias w WHERE\n" + ALIAS_WHERE["code"],
    }}})
    q = _by_id(content.for_exam("1Z0-071", "pl").QUESTIONS, "q01-alias-where")
    assert q["prompt"] == "Które stwierdzenie o tym zapytaniu jest prawdziwe?"
    assert q["code"].startswith("-- alias w WHERE")
    assert q["explanation"] == ALIAS_WHERE["explanation"]  # a missing field keeps the source text
    assert q["options"] == ALIAS_WHERE["options"] and q["answer"] == ALIAS_WHERE["answer"]
    assert before == content.QUESTIONS
    assert _by_id(content.for_exam("1Z0-071").QUESTIONS, "q01-alias-where") == ALIAS_WHERE


def test_flashcards_in_english_read_the_english_overlay(overlay_dir):
    card = _by_id(content.FLASHCARDS, "c000")
    overlay_dir("en", "t01", {"flashcards": {"c000": {"front": "How do you put an apostrophe (') in a SQL string?"}}})
    english = _by_id(content.for_exam("1Z0-071", "en").FLASHCARDS, "c000")
    assert english["front"] == "How do you put an apostrophe (') in a SQL string?"
    assert english["back"] == card["back"]  # not translated yet: the source text
    assert _by_id(content.for_exam("1Z0-071", "pl").FLASHCARDS, "c000") == card  # Polish is the source
    assert content.PACKS["oracle-sql"].source_languages == {"questions": "en", "labs": "en", "flashcards": "pl",
                                                            "meta": "en"}


def test_pack_names_and_labs_come_from_the_overlay(overlay_dir):
    overlay_dir("pl", "_pack", {"topics": {"t01": "Podstawy SELECT"}, "sections": {"2": "Pobieranie danych"},
                                "objectives": {"2.1": "Polecenie SELECT"}})
    overlay_dir("pl", "t01", {"labs": {"lab-all-departments": {"title": "Wszystkie kolumny departments"}}})
    view = content.for_exam("1Z0-071", "pl")
    assert view.TOPICS["t01"] == "Podstawy SELECT" and view.TOPICS["t02"] == content.TOPICS["t02"]
    assert view.SECTIONS["2"] == "Pobieranie danych" and view.OBJECTIVES["2.1"] == "Polecenie SELECT"
    assert _by_id(view.LABS, "lab-all-departments")["title"] == "Wszystkie kolumny departments"
    assert content.for_exam("1Z0-071", "en").TOPICS["t01"] == content.TOPICS["t01"]


def test_needs_label_and_home_notes_fall_back_to_english(overlay_dir):
    view = content.for_exam("1Z0-171", "pl")
    t15 = next(q for q in view.QUESTIONS if q["topic"] == "t15")
    assert t15["needs"]["major"] == 23 and t15["needs"]["label"]
    assert [n["path"] for n in view.HOME_NOTES] == [n["path"] for n in content.PACKS["oracle-sql"].home_notes]
    assert view.EXAM["code"] == "1Z0-171" and view.EXAM["about"]


# --------------------------------------------------------------------------- the validator


def test_validator_accepts_a_good_translation(overlay_dir):
    overlay_dir("pl", "t01", {"questions": {
        "q01-alias-where": {"prompt": "Które stwierdzenie jest prawdziwe?",
                            "code": "/* alias w WHERE */\n" + ALIAS_WHERE["code"].replace("\n", "  -- wiersz\n", 1),
                            "options": ["Działa.", "Błąd: alias w WHERE.", "Błąd: alias w ORDER BY.", "Błąd: AS."]},
        "q01-quotes": {"options": QUOTES["options"]},
    }})
    assert v.translation_problems("pl", "t01") == []


def test_validator_rejects_broken_translations(overlay_dir):
    overlay_dir("pl", "t01", {
        "questions": {
            "q01-quotes": {"options": ["SELECT 'To''s done' FROM dual;"] + QUOTES["options"][1:]},
            "q01-alias-where": {"code": ALIAS_WHERE["code"].replace("100000", "1000"), "options": ["Tak", "Nie"],
                                "prompt": "Które {count} stwierdzenie?", "answer": [0]},
            "q01-nonexistent": {"prompt": "Nic"},
        },
        "labs": {"lab-all-departments": {"hint": ""}},
    })
    problems = "\n".join(v.translation_problems("pl", "t01"))
    assert "question q01-quotes: option 1 is SQL and must stay identical" in problems
    assert "question q01-alias-where: code differs from the source outside comments" in problems
    assert "question q01-alias-where: options has 2 entries, the source has 4" in problems
    assert "question q01-alias-where: prompt placeholders differ" in problems
    assert "question q01-alias-where: unknown field answer" in problems
    assert "question q01-nonexistent: unknown id" in problems
    assert "lab lab-all-departments: hint is empty" in problems


def test_validator_checks_backtick_spans_and_topic_files(overlay_dir):
    lab = next(lab for lab in content.LABS if lab["topic"] == "t01")
    overlay_dir("pl", "t02", {"labs": {lab["id"]: {"task": "Zwróć `department_id`."}}})
    problems = "\n".join(v.translation_problems("pl", "t02"))
    assert f"lab {lab['id']}: belongs to t01" in problems
    assert f"lab {lab['id']}: task code spans differ" in problems


def test_complete_lists_missing_items_and_fields(overlay_dir):
    overlay_dir("pl", "t01", {"questions": {"q01-alias-where": {"prompt": "Które stwierdzenie jest prawdziwe?"}}})
    assert v.translation_problems("pl", "t01") == []
    problems = v.translation_problems("pl", "t01", complete=True)
    assert "pl/t01.json: question q01-quotes: missing" in problems
    assert "pl/t01.json: question q01-alias-where: missing explanation" in problems
    assert not any("flashcard" in p for p in problems)  # Polish is the flashcards' source
    assert "pl/_pack.json: topic t01: missing" in v.translation_problems("pl", "_pack", complete=True)
    assert any("flashcard c000: missing" in p for p in v.translation_problems("en", "t01", complete=True))


def test_sql_comparison_ignores_only_comments():
    assert v.sql_without_comments("SELECT 1 -- one\nFROM dual /* x */;") == v.sql_without_comments(
        "-- jeden\nSELECT 1\n  FROM dual;")
    assert v.sql_without_comments("SELECT '--x' FROM dual") != v.sql_without_comments("SELECT '' FROM dual")
    assert v.sql_without_comments("SELECT q'[It's -- here]' FROM dual") != v.sql_without_comments(
        "SELECT q'[It's ]' FROM dual")


# --------------------------------------------------------------------------- notes


@pytest.fixture
def notes_dir(tmp_path):
    root = tmp_path / "notes"
    (root / "docs").mkdir(parents=True)
    (root / "topics" / "01-basic-select").mkdir(parents=True)
    (root / "docs" / "cheat-sheet.md").write_text("# Cheat sheet\n\n```sql\n-- one\nSELECT 1 FROM dual;\n```\n", "utf-8")
    (root / "docs" / "cheat-sheet.pl.md").write_text("# Ściąga\n\n```sql\n-- jeden\nSELECT 1 FROM dual;\n```\n", "utf-8")
    (root / "docs" / "progress.md").write_text("# Progress\n", "utf-8")
    topic = root / "topics" / "01-basic-select"
    (topic / "notes.md").write_text("# Notes\n\n```sql\nSELECT 2 FROM dual;\n```\n", "utf-8")
    (topic / "examples.sql").write_text("-- example\nSELECT 3 FROM dual;\n", "utf-8")
    (topic / "examples.pl.sql").write_text("-- przykład\nSELECT 3 FROM dual;\n", "utf-8")
    return root


class _NoPersonal:
    def entries(self):
        return []

    def read(self, name):
        return None


def test_notes_serve_the_sibling_and_list_no_siblings(notes_dir):
    notes = NotesLibrary(notes_dir, _NoPersonal())
    listed = notes.list()
    assert [n["path"] for n in listed] == ["docs/cheat-sheet.md", "docs/progress.md", "topics/01-basic-select/notes.md",
                                           "topics/01-basic-select/examples.sql"]
    assert listed[0]["title"] == "Cheat sheet"
    assert notes.read("docs/cheat-sheet.md", lang="pl").startswith("# Ściąga")
    assert notes.read("docs/cheat-sheet.md").startswith("# Cheat sheet")
    assert notes.read("docs/progress.md", lang="pl") == "# Progress\n"  # no sibling: English
    assert notes.read("topics/01-basic-select/examples.sql", lang="pl").startswith("-- przykład")
    assert notes.read("docs/cheat-sheet.pl.md", lang="pl") is None


def test_validator_checks_note_siblings(notes_dir, monkeypatch, overlay_dir):
    monkeypatch.setattr(v, "NOTES_DIR", notes_dir)
    assert v.translation_problems("pl") == []
    (notes_dir / "docs" / "cheat-sheet.pl.md").write_text("# Ściąga\n\n```sql\nSELECT 9 FROM dual;\n```\n", "utf-8")
    (notes_dir / "topics" / "01-basic-select" / "notes.pl.md").write_text("# Notatki\n", "utf-8")
    (notes_dir / "docs" / "orphan.pl.md").write_text("# Sierota\n", "utf-8")
    problems = v.translation_problems("pl")
    assert "notes/docs/cheat-sheet.pl.md: code block 1 differs from the English one outside comments" in problems
    assert "notes/topics/01-basic-select/notes.pl.md: 0 code blocks, the English note has 1" in problems
    assert "notes/docs/orphan.pl.md: no English note docs/orphan.md" in problems
    assert v.translation_problems("pl", "t02") == []  # other topics' notes are not checked
    assert "notes/docs/progress.md: missing" in v.translation_problems("pl", "docs", complete=True)
    (notes_dir / "topics" / "01-basic-select" / "examples.pl.sql").write_text("SELECT 4 FROM dual;\n", "utf-8")
    assert ("notes/topics/01-basic-select/examples.pl.sql: differs from the English file outside comments"
            in v.translation_problems("pl", "t01"))


def test_validate_cli_runs_the_translation_checks(overlay_dir, capsys, monkeypatch, tmp_path):
    from oracle_lab import cli

    monkeypatch.setenv("STUDY_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("STUDY_PASSWORD", "unused")
    overlay_dir("pl", "t01", {"questions": {"q01-nonexistent": {"prompt": "Nic"}}})
    assert cli.main(["validate", "--static", "--lang", "pl", "--topic", "t01"]) == 1
    out = capsys.readouterr().out
    assert "Translations (pl): 1 problem(s)." in out and "q01-nonexistent: unknown id" in out


# --------------------------------------------------------------------------- server-built feedback


class FakeSchema:
    def columns(self):
        return {"EMPLOYEES": ["EMPLOYEE_ID", "LAST_NAME", "SALARY", "DEPARTMENT_ID"]}

    def constraint(self, name):
        return None


def test_error_explanations_follow_the_language(monkeypatch):
    monkeypatch.setitem(error_hints.overlay("pl"), "ORA-00904",
                        {"title": "Nieprawidłowy identyfikator", "explanation": "Oracle nie znajduje kolumny."})
    error = 'ORA-00904: "E"."SALRY": invalid identifier'
    pl = error_hints.explain(error, "SELECT e.salry FROM employees e", FakeSchema(), lang="pl")
    assert pl["title"] == "Nieprawidłowy identyfikator" and pl["text"] == "Oracle nie znajduje kolumny."
    assert pl["hint"] == "Nie ma kolumny SALRY. Czy chodziło ci o SALARY (EMPLOYEES)?"
    en = error_hints.explain(error, "SELECT e.salry FROM employees e", FakeSchema())
    assert en["title"] == "Invalid identifier" and en["hint"] == "No column is called SALRY. Did you mean SALARY (EMPLOYEES)?"
    other = error_hints.explain("ORA-00942: table or view does not exist", "SELECT 1 FROM nope", FakeSchema(), lang="pl")
    assert other["title"] == "Table or view does not exist"  # no Polish entry yet: English


def test_grading_feedback_in_polish_and_unchanged_english():
    lab = {"columns": "id, name", "ordered": True}
    rows = [["1", "a"], ["2", "b"]]
    assert compare_results(lab, ["ID", "NAME"], rows[:1], ["ID", "NAME"], rows)["feedback"] == ["Expected 2 rows, got 1."]
    pl = compare_results(lab, ["ID", "NAME"], rows[:1], ["ID", "NAME"], rows, lang="pl")["feedback"]
    assert pl == ["Liczba wierszy: 1, oczekiwana: 2."]
    pl = compare_results(lab, ["ID", "NAME"], rows[::-1], ["ID", "NAME"], rows, lang="pl")["feedback"]
    assert pl == ["Właściwe wiersze, ale w złej kolejności. Sprawdź ORDER BY i kolumny rozstrzygające przy równych wartościach."]
    alias = compare_results(lab, ["X", "Y"], rows, ["ID", "NAME"], rows, lang="pl")["feedback"][0]
    assert "id, name" in alias and alias != compare_results(lab, ["X", "Y"], rows, ["ID", "NAME"], rows)["feedback"][0]


class _Conn:
    def rollback(self):
        pass

    def close(self):
        pass


class _Database:
    def connect(self):
        return _Conn()


def test_exercise_errors_follow_the_language():
    lab = {"id": "x", "kind": "dml", "check": "SELECT 1 FROM dual", "solution": "DELETE FROM t"}
    assert labs.grade(_Database(), lab, "")["error"] == "Write at least one statement."
    assert labs.grade(_Database(), lab, "", lang="pl")["error"] == "Napisz co najmniej jedno polecenie SQL."


def test_visualizer_and_lab_messages_follow_the_language():
    assert visualizer.visualize(None, "SELECT 1 FROM dual; SELECT 2 FROM dual", None)["error"] == \
        "Visualize one statement at a time."
    assert visualizer.visualize(None, "SELECT 1 FROM dual; SELECT 2 FROM dual", None, lang="pl")["error"] == \
        "Wizualizuj jedno polecenie SQL naraz."
    assert visualizer.visualize(None, "SELECT 1 FROM dual", None, lang="pl")["error"] != visualizer.UNSUPPORTED
    tx = Transaction("pl")
    tx.after("INSERT INTO t VALUES (1)", 3)
    assert tx.after("CREATE TABLE lab_x (a NUMBER)", 0)["note"] == \
        "To polecenie DDL najpierw zatwierdziło 3 oczekujące zmiany wierszy."
    tx = Transaction()
    tx.after("INSERT INTO t VALUES (1)", 1)
    assert tx.after("CREATE TABLE lab_x (a NUMBER)", 0)["note"] == "This DDL statement committed 1 pending row change first."
    [stmt] = split_statements("SET SERVEROUTPUT ON")
    assert client_command_result(stmt)["message"] == "SQL*Plus command ignored by the lab."
    assert client_command_result(stmt, "pl")["message"] == "Polecenie SQL*Plus pominięte w laboratorium SQL."


# --------------------------------------------------------------------------- delivery


def test_content_and_notes_follow_the_request_language(serve, overlay_dir, notes_dir, monkeypatch):
    monkeypatch.setattr(bootstrap, "NOTES_DIR", notes_dir)
    overlay_dir("pl", "t01", {"questions": {"q01-alias-where": {"prompt": "Które stwierdzenie jest prawdziwe?"}}})
    http = serve().sign_in()
    pl = json.loads(http("/api/content", headers={"X-Language": "pl"})[2])
    assert _by_id(pl["questions"], "q01-alias-where")["prompt"] == "Które stwierdzenie jest prawdziwe?"
    en = json.loads(http("/api/content", headers={"X-Language": "en"})[2])
    assert _by_id(en["questions"], "q01-alias-where")["prompt"] == ALIAS_WHERE["prompt"]
    assert en["exam"]["about"] == content.EXAMS["1Z0-071"]["about"]
    note = json.loads(http("/api/note?path=docs/cheat-sheet.md", headers={"X-Language": "pl"})[2])
    assert note["text"].startswith("# Ściąga")
    listed = json.loads(http("/api/notes", headers={"X-Language": "pl"})[2])
    assert not any(".pl." in n["path"] for n in listed)


# --------------------------------------------------------------------------- review round 1


def test_sql_options_are_code_and_sentences_about_sql_are_prose():
    options = {o for q in content.QUESTIONS for o in q["options"]}
    for prose in ("MERGE must include both WHEN MATCHED and WHEN NOT MATCHED clauses.",
                  "MERGE is DDL and commits implicitly.",
                  "MERGE can insert the unmatched rows into a table other than the INTO target.",
                  "SELECT is revoked and INSERT is silently ignored.",
                  "SELECT is revoked and a warning is returned for INSERT.",
                  "ALTER TABLE t MODIFY (name VARCHAR2(40)) succeeds.",
                  "REVOKE SELECT ON lab_t FROM PUBLIC, then GRANT SELECT ON lab_t TO PUBLIC"):
        assert prose in options and not v.is_sql_option(prose), prose
    for sql in ("SELECT q'[It's done]' FROM dual;", "MERGE", "col LIKE '%_%'",
                "employees e LEFT OUTER JOIN departments d ON ...", "GRANT SELECT ON employees TO lead WITH GRANT OPTION;",
                "SELECT e.salary AS select FROM employees e", "INSERT INTO departments VALUES (60, 'Legal');"):
        assert sql in options and v.is_sql_option(sql), sql


def test_complete_skips_sql_fields_without_comments_and_all_sql_options(overlay_dir):
    quotes = v.translation_problems("pl", "t01", complete=True)
    assert "pl/t01.json: question q01-quotes: missing" in quotes
    overlay_dir("pl", "t01", {"questions": {
        "q01-quotes": {"prompt": "Które dwa zapytania zwracają tekst It's done?", "explanation": "Apostrof podwajasz."},
        "q01-alias-where": {"prompt": "Które stwierdzenie jest prawdziwe?", "explanation": "WHERE jest przed SELECT.",
                            "options": ["Działa.", "Błąd: alias w WHERE.", "Błąd: alias w ORDER BY.", "Błąd: AS."]},
    }})
    problems = [p for p in v.translation_problems("pl", "t01", complete=True)
                if "q01-quotes" in p or "q01-alias-where" in p]
    assert problems == []  # all-SQL options and comment-free code/try_sql need no entry
    card = _by_id(content.FLASHCARDS, "c000")  # its try_sql has a comment
    overlay_dir("en", "t01", {"flashcards": {"c000": {"front": "Apostrophe?", "back": "Double it."}}})
    assert "en/t01.json: flashcard c000: missing try_sql" in v.translation_problems("en", "t01", complete=True)
    assert v.has_comments(card["try_sql"]) and not v.has_comments(QUOTES["try_sql"])


def test_indented_code_blocks_are_checked(notes_dir, monkeypatch, overlay_dir):
    monkeypatch.setattr(v, "NOTES_DIR", notes_dir)
    topic = notes_dir / "topics" / "01-basic-select"
    (topic / "notes.md").write_text("# Notes\n\n- Step:\n\n  ```sql\n  GRANT SELECT ON t TO u;\n  ```\n", "utf-8")
    (topic / "notes.pl.md").write_text("# Notatki\n\n- Krok:\n\n  ```sql\n  -- nadaj\n  GRANT SELECT ON t TO u;\n  ```\n",
                                       "utf-8")
    assert v.translation_problems("pl", "t01") == []
    (topic / "notes.pl.md").write_text("# Notatki\n\n- Krok:\n\n  ```sql\n  DROP USER x CASCADE;\n  ```\n", "utf-8")
    assert ("notes/topics/01-basic-select/notes.pl.md: code block 1 differs from the English one outside comments"
            in v.translation_problems("pl", "t01"))


def test_prompt_lines_are_code_not_comments():
    assert v.sql_without_comments("PROMPT --- Fixed: one\nSELECT 1 FROM dual;") != v.sql_without_comments(
        "PROMPT --- Poprawione: jeden\nSELECT 1 FROM dual;")
    assert not v.has_comments("prompt -- shown as it is\nSELECT 1 FROM dual;")


def test_a_broken_overlay_file_is_left_out_and_reported(overlay_dir, caplog):
    overlay_dir("pl", "t02", {"questions": {}})
    overlay_dir("pl", "t01", {"questions": {"q01-alias-where": {"prompt": "Które stwierdzenie jest prawdziwe?"}}})
    (overlays.OVERLAY_DIR / "pl" / "t01.json").write_text('{"questions": {', "utf-8")
    overlays.load.cache_clear()
    with caplog.at_level("ERROR"):
        q = _by_id(content.for_exam("1Z0-071", "pl").QUESTIONS, "q01-alias-where")
    assert q["prompt"] == ALIAS_WHERE["prompt"] and "t01.json" in caplog.text
    assert any(p.startswith("pl/t01.json: not valid JSON") for p in v.translation_problems("pl", "t01"))
