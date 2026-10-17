"""Study content for the 1Z0-071 learning app.

All questions are original practice material written for this repository.
They are not real exam questions. Answers marked "executed" in comments were
checked against the ORASTUDY seed data on Oracle Database 19.3.

Content lives in one module per topic (t01_basic_select.py, ...), each defining
QUESTIONS, FLASHCARDS and LABS. Questions drafted by the AI tutor, checked against the database
and accepted by you in the review queue, are stored in generated.json and added here.
Check changes with: .venv/bin/python app/validate_content.py

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
from pathlib import Path

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
)
from .objectives import EXAM, OBJECTIVES, SECTIONS  # noqa: F401

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
}

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
]

GENERATED_FILE = Path(__file__).with_name("generated.json")
GENERATED = json.loads(GENERATED_FILE.read_text()) if GENERATED_FILE.exists() else []

QUESTIONS = [q for m in _MODULES for q in m.QUESTIONS] + GENERATED
FLASHCARDS = [c for m in _MODULES for c in m.FLASHCARDS]
LABS = [lab for m in _MODULES for lab in m.LABS]
