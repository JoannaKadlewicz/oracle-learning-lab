"""Every translation is complete: Polish questions, exercises, names, notes and error explanations,
English flashcards, and both catalogs. A gap anywhere fails here, before a learner sees English text
in the Polish app or Polish text in the English one."""

from __future__ import annotations

from oracle_lab import i18n
from oracle_lab.analysis import error_hints
from oracle_lab.study.notes import guide_title, source_files, translated
from oracle_lab.tools import validate_content


def test_polish_content_is_complete():
    assert validate_content.translation_problems("pl", complete=True) == []


def test_english_flashcards_are_complete():
    assert validate_content.translation_problems("en", complete=True) == []


def test_every_built_in_note_has_a_polish_sibling():
    root = validate_content.NOTES_DIR
    notes = source_files(root / "docs", "*.md") + source_files(root / "topics", "*/*.md") \
        + source_files(root / "topics", "*/*.sql")
    assert len(notes) >= 20
    assert [n.relative_to(root).as_posix() for n in notes if not translated(n, "pl").is_file()] == []


def test_every_error_explanation_has_a_polish_entry():
    polish = error_hints.overlay("pl")
    missing = [code for code in error_hints.ERRORS if not (polish.get(code) or {}).get("title")
               or not polish[code].get("explanation")]
    assert missing == []


def test_guide_titles_and_exam_texts_have_polish_entries():
    from oracle_lab import content, exams

    catalog = i18n.catalog("pl")
    titles = [guide_title(f) for f in source_files(validate_content.NOTES_DIR / "docs", "*.md")]
    about = [exam.public()["about"] for exam in exams.EXAMS.values()]
    home = [text for note in content.for_exam(content.DEFAULT_EXAM).HOME_NOTES for text in (note["title"], note["blurb"])]
    assert [text for text in titles + about + home if text not in catalog] == []
