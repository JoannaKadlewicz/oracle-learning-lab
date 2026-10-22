"""Study content for the 1Z0-071 learning app.

All questions are original practice material written for this repository.
They are not real exam questions. Answers marked "executed" in comments were
checked against the ORASTUDY seed data on Oracle Database 19.3.

Content lives in one module per topic (t01_basic_select.py, ...), each defining
QUESTIONS, FLASHCARDS and LABS. Questions drafted by the AI tutor, checked against the database
and accepted by you in the review queue, are stored in generated.json and added here.
Check changes with: oracle-lab validate

Question fields:
    id, topic, objective, prompt, code (optional), options, answer (list of option indexes),
    explanation, try_sql (optional: SQL that can be run in the lab to see the behavior),
    try_error (optional: the ORA- code try_sql is expected to raise, e.g. "ORA-00904")
Flashcard fields:
    id, topic, objective, front, back
Lab fields:
    id, topic, objective, title, task, columns, ordered, solution, hint (optional)
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

from oracle_lab import exams
from oracle_lab.i18n import translate

from . import i18n as overlays
from . import (
    t01_basic_select,
    t02_restricting_sorting,
    t03_single_row_functions,
    t04_conversion_conditional,
    t05_aggregation,
    t06_joins,
    t07_subqueries,
    t08_set_operators,
    t09_dml_transactions,
    t10_tables_constraints,
    t11_views_sequences_indexes,
    t12_data_dictionary,
    t13_user_access,
    t14_time_zones_intervals,
    t15_oracle_23ai,
)
from .objectives import OBJECTIVES, SECTION_EXAMS, SECTIONS  # noqa: F401

# The exam facts live in the registry; content keeps the public dicts under the old names, a snapshot
# taken at import (code that must see exams registered later reads exams.EXAMS).
EXAMS = {code: exam.public() for code, exam in exams.EXAMS.items()}
DEFAULT_EXAM = exams.DEFAULT_EXAM
EXAM = EXAMS[DEFAULT_EXAM]


_MODULES = [
    t01_basic_select,
    t02_restricting_sorting,
    t03_single_row_functions,
    t04_conversion_conditional,
    t05_aggregation,
    t06_joins,
    t07_subqueries,
    t08_set_operators,
    t09_dml_transactions,
    t10_tables_constraints,
    t11_views_sequences_indexes,
    t12_data_dictionary,
    t13_user_access,
    t14_time_zones_intervals,
    t15_oracle_23ai,
]

GENERATED_FILE = Path(__file__).with_name("generated.json")
GENERATED = json.loads(GENERATED_FILE.read_text()) if GENERATED_FILE.exists() else []

QUESTIONS = [q for m in _MODULES for q in m.QUESTIONS] + GENERATED
FLASHCARDS = [c for m in _MODULES for c in m.FLASHCARDS]
LABS = [lab for m in _MODULES for lab in m.LABS]


@dataclass(frozen=True)
class Pack:
    """The content of one subject area: exams whose "pack" is its id share it."""

    id: str
    topics: dict[str, str]
    sections: dict[str, str]
    objectives: dict[str, str]
    topic_exams: dict[str, list[str]]  # topics only on some of the pack's exams
    section_exams: dict[str, list[str]]
    topic_needs: dict[str, dict]  # topic -> {"major": int, "label": str}: the database version its items need
    notes: tuple[str, ...]  # built-in note globs, relative to the notes directory
    home_notes: tuple[dict, ...]  # the notes the home page links to: {"path", "title", "blurb"}
    questions: list[dict]
    flashcards: list[dict]
    labs: list[dict]
    # The language each kind of item is written in ("meta": topic, section and objective names); the
    # other languages read translation overlays (content/i18n).
    source_languages: dict[str, str] = field(default_factory=lambda: dict.fromkeys(SOURCE_KINDS, "en"))


SOURCE_KINDS = ("questions", "labs", "flashcards", "meta")

TOPICS = {
    "t01": "Basic SELECT",
    "t02": "Restricting and sorting",
    "t03": "Single-row functions",
    "t04": "Conversion and conditional",
    "t05": "Aggregation",
    "t06": "Joins",
    "t07": "Subqueries",
    "t08": "Set operators",
    "t09": "DML and transactions",
    "t10": "Tables and constraints",
    "t11": "Views, sequences, indexes",
    "t12": "Data dictionary",
    "t13": "User access control",
    "t14": "Time zones and intervals",
    "t15": "Oracle 23ai SQL features",
}

PACKS = {
    "oracle-sql": Pack(
        id="oracle-sql",
        topics=TOPICS,
        sections=SECTIONS,
        objectives=OBJECTIVES,
        # Topics and sections only on one exam; every other one belongs to both.
        topic_exams={"t15": ["1Z0-171"]},
        section_exams=SECTION_EXAMS,
        topic_needs={"t15": {"major": 23, "label": "Oracle 23ai"}},
        notes=("docs/*.md", "topics/*/*.md", "topics/*/*.sql"),
        home_notes=(
            {"path": "docs/exam-guide-2026.md", "title": "Exam guide 2026",
             "blurb": "1Z0-071 and 1Z0-171 compared, with every 19c and 23ai difference."},
            {"path": "docs/cheat-sheet.md", "title": "Cheat sheet",
             "blurb": "The rules and traps of every topic on one page."},
        ),
        questions=QUESTIONS,
        flashcards=FLASHCARDS,
        labs=LABS,
        source_languages={"questions": "en", "labs": "en", "flashcards": "pl", "meta": "en"},
    ),
}

# The union over packs; with one pack these are that pack's own lists.
TOPICS = {t: n for pack in PACKS.values() for t, n in pack.topics.items()}
SECTIONS = {s: n for pack in PACKS.values() for s, n in pack.sections.items()}
OBJECTIVES = {o: n for pack in PACKS.values() for o, n in pack.objectives.items()}
TOPIC_EXAMS = {t: e for pack in PACKS.values() for t, e in pack.topic_exams.items()}
QUESTIONS = [q for pack in PACKS.values() for q in pack.questions]
FLASHCARDS = [c for pack in PACKS.values() for c in pack.flashcards]
LABS = [lab for pack in PACKS.values() for lab in pack.labs]


def pack_of(code: str | None) -> Pack:
    """The pack of an exam (the default exam's for an unknown code)."""
    return PACKS[exams.get(code).pack]


def pack_holding(item: dict) -> Pack:
    return next((p for p in PACKS.values() if item.get("topic") in p.topics), next(iter(PACKS.values())))


def pack_exams(pack: Pack) -> list[str]:
    """The codes of the exams that use a pack."""
    return [code for code, exam in exams.EXAMS.items() if exam.pack == pack.id]


def item_exams(item: dict, pack: Pack | None = None) -> list[str]:
    """The exams an item belongs to: its own "exams" list, else its topic's, else every exam of its pack."""
    pack = pack or pack_holding(item)
    return item.get("exams") or pack.topic_exams.get(item.get("topic")) or pack_exams(pack)


def _with_needs(items: list[dict], pack: Pack, lang: str = "en") -> list[dict]:
    """The items, those of a topic that needs a database version as copies carrying "needs"."""
    needs = {t: {**n, "label": translate(lang, n["label"])} for t, n in pack.topic_needs.items()}
    return [{**i, "needs": needs[i["topic"]]} if i.get("topic") in needs else i for i in items]


def _localized(kind: str, items: list[dict], pack: Pack, lang: str) -> list[dict]:
    """The items in `lang`: as they are in their source language, else copies with the overlay applied."""
    if pack.source_languages.get(kind, "en") == lang:
        return items
    overlay = overlays.load(lang)
    return [overlays.localize(kind, item, overlay) for item in items]


def _names(kind: str, names: dict[str, str], pack: Pack, lang: str) -> dict[str, str]:
    if pack.source_languages.get("meta", "en") == lang:
        return names
    overlay = overlays.load(lang)
    return {key: overlay.name(kind, key, name) for key, name in names.items()}


def public_exam(exam: exams.Exam, lang: str = "en") -> dict:
    """The exam facts for the front end, the about text in `lang`."""
    facts = exam.public()
    return {**facts, "about": translate(lang, facts["about"]), "tile": translate(lang, facts["tile"])}


def home_notes(pack: Pack, lang: str = "en") -> list[dict]:
    return [{**n, "title": translate(lang, n["title"]), "blurb": translate(lang, n["blurb"])} for n in pack.home_notes]


def for_exam(code, lang: str = "en"):
    """The content of one exam track in `lang`, with the same attributes as this module (used by the engine).
    Items not written in `lang` are localized copies; the module's own lists are never changed."""
    exam = exams.get(code)
    pack = PACKS[exam.pack]
    code = exam.code
    sections = {s: t for s, t in pack.sections.items() if code in pack.section_exams.get(s, pack_exams(pack))}

    def items(kind, source):
        mine = [i for i in source if code in item_exams(i, pack)]
        return _with_needs(_localized(kind, mine, pack, lang), pack, lang)

    return SimpleNamespace(
        CODE=code,
        EXAM=public_exam(exam, lang),
        PACK=pack,
        HOME_NOTES=home_notes(pack, lang),
        TOPICS=_names("topics", {t: n for t, n in pack.topics.items()
                                 if code in pack.topic_exams.get(t, pack_exams(pack))}, pack, lang),
        SECTIONS=_names("sections", sections, pack, lang),
        OBJECTIVES=_names("objectives", {o: t for o, t in pack.objectives.items() if o.split(".")[0] in sections},
                          pack, lang),
        QUESTIONS=items("questions", pack.questions),
        FLASHCARDS=items("flashcards", pack.flashcards),
        LABS=items("labs", pack.labs),
    )
