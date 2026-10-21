"""Check the study content before using it.

    oracle-lab validate               # structure + database checks
    oracle-lab validate --static      # structure only, no database
    oracle-lab validate --reset       # reset the sample data first
    oracle-lab validate --topic t08   # database checks for one topic only

Structure checks: unique IDs (topic, section, objective and item IDs also across content packs),
valid topics and objectives, valid answer indexes, "Which two/three" prompts matching the number of
answers, known fields only, try_sql (questions and flashcards) without DDL or COMMIT, lab cleanup that
only drops LAB_ objects, flashcard samples whose DDL only touches the card's own LAB_C<id>_ objects,
dropped by its cleanup.
Database checks:
  - every try_sql of a question or flashcard runs, or raises exactly its try_error
  - a flashcard sample with DDL leaves the schema and the sample data as it found them
  - answer_sql returns exactly the text of the correct option
  - equivalent_sql: exactly the correct options return the same rows as this query
  - query labs: the solution runs, returns rows and the columns the task names
  - dml/ddl labs: the solution changes the check result, and gives the same result twice
  - labs with a starter (a "fix the bug" exercise): the starter does not already pass
Items are checked on the database of their exam track, chosen through the exam registry: Oracle 23ai or
later checks the 1Z0-171 items, older versions the 1Z0-071 items (an item's "exams" field, else its topic's,
else both). --exam CODE checks one exam's items only, on that exam's own database (else its fallback's),
with a warning when the database's version is outside the exam's.
Changes are rolled back. --reset drops and recreates the ORASTUDY sample tables.

    oracle-lab validate --static --lang pl              # + the Polish translations
    oracle-lab validate --static --lang pl --topic t06  # one topic's overlay file and notes only
    oracle-lab validate --static --lang pl --complete   # + every missing translation

Translation checks (translation_problems, see AUTHORING.md "Translations"): overlay files name only known
items and fields, keep the option count, keep SQL options identical, change SQL fields (code, try_sql,
starter, solution) only in their comments, keep {placeholders} and `code spans`, and have no empty text.
Note siblings (notes.pl.md, examples.pl.sql) keep every fenced code block, and every .sql file, identical
to the English note outside comments. --complete also lists every missing translation.
Exits with status 1 if any check fails.
"""

import argparse
import json
import re
from collections import Counter

from oracle_lab import content, engines, exams
from oracle_lab.content import i18n as overlays
from oracle_lab.database.connection import Database, DatabaseCatalog
from oracle_lab.database.executor import ScriptRunner
from oracle_lab.database.query import first_line, format_error, single_query
from oracle_lab.database.sample_schema import SampleSchema
from oracle_lab.grading.comparison import compare_results, normalize_rows
from oracle_lab.grading.labs import DML_LAB_VERBS, LabKind, lab_kind, lab_result, run_cleanup
from oracle_lab.resources import NOTES_DIR
from oracle_lab.sqltext.statements import StatementKind, split_statements
from oracle_lab.study.notes import source_files, translated

QUESTION_KEYS = {"id", "topic", "objective", "prompt", "code", "options", "answer", "explanation",
                 "try_sql", "try_error", "try_error_since", "answer_sql", "equivalent_sql", "exams"}
QUESTION_REQUIRED = {"id", "topic", "objective", "prompt", "options", "answer", "explanation"}
CARD_KEYS = {"id", "topic", "objective", "front", "back"}
CARD_OPTIONAL = {"exams", "try_sql", "try_error", "try_error_since", "cleanup"}
LAB_COMMON = {"id", "topic", "objective", "title", "task", "solution"}
LAB_REQUIRED = {
    "query": LAB_COMMON | {"columns", "ordered"},
    "dml": LAB_COMMON | {"kind", "check"},
    "ddl": LAB_COMMON | {"kind", "check", "cleanup"},
}
LAB_OPTIONAL = {"hint", "hint2", "exams", "starter"}
TRY_SQL_VERBS = {"SELECT", "WITH", "INSERT", "UPDATE", "DELETE", "MERGE", "SAVEPOINT", "ROLLBACK"}
# DDL a flashcard sample may run on its own objects (it commits, so the card's cleanup drops them)
CARD_DDL_VERBS = {"CREATE", "ALTER", "DROP", "TRUNCATE", "COMMENT", "RENAME", "GRANT", "REVOKE"}
SQL_COMMENT = re.compile(r"--[^\n]*|/\*.*?\*/", re.DOTALL)
CLEANUP_STATEMENT = re.compile(
    r"\s*DROP\s+((TABLE|VIEW|SEQUENCE|INDEX|SYNONYM)\s+LAB_\w+(\s+CASCADE\s+CONSTRAINTS)?(\s+PURGE)?"
    r"|DOMAIN\s+LAB_\w+(\s+FORCE)?)\s*;?\s*",
    re.IGNORECASE,
)
MAX_OPTIONS = 8  # the quiz labels options A to H
COUNT_WORDS = {"two": 2, "three": 3, "four": 4}


def check_fields(kind, item, allowed, required):
    errors = []
    label = f"{kind} {item.get('id', '?')}"
    pack = content.pack_holding(item)
    if missing := required - item.keys():
        errors.append(f"{label}: missing {', '.join(sorted(missing))}")
    if unknown := item.keys() - allowed:
        errors.append(f"{label}: unknown field {', '.join(sorted(unknown))}")
    for key in item.keys() & allowed:
        if key == "ordered":
            if not isinstance(item[key], bool):
                errors.append(f"{label}: ordered must be True or False")
        elif key == "exams":
            pack_codes = content.pack_exams(pack)
            if not (isinstance(item[key], list) and item[key] and set(item[key]) <= set(pack_codes)):
                errors.append(f"{label}: exams must be a non-empty list of {', '.join(pack_codes)}")
            elif not set(item[key]) <= set(pack.topic_exams.get(item.get("topic"), pack_codes)):
                errors.append(f"{label}: exams lists an exam its topic is not part of")
        elif key not in ("options", "answer", "try_error_since") and not (isinstance(item[key], str) and item[key].strip()):
            errors.append(f"{label}: {key} must be a non-empty string")
    if item.get("topic") not in content.TOPICS:
        errors.append(f"{label}: unknown topic {item.get('topic')!r}")
    if item.get("objective") not in content.OBJECTIVES:
        errors.append(f"{label}: unknown objective {item.get('objective')!r}")
    elif not set(content.item_exams(item, pack)) <= set(
            pack.section_exams.get(item["objective"].split(".")[0], content.pack_exams(pack))):
        errors.append(f"{label}: objective {item['objective']} is not part of {', '.join(content.item_exams(item, pack))}")
    return errors


def try_sql_problems(label, item, ddl_prefix=None):
    """try_sql and its expected error, shared by questions and flashcards. With ddl_prefix
    (a flashcard with a cleanup), DDL is allowed on objects whose names start with it."""
    errors = []
    if "try_error" in item:
        if "try_sql" not in item:
            errors.append(f"{label}: try_error without try_sql")
        if not re.fullmatch(r"ORA-\d{5}", item["try_error"]):
            errors.append(f"{label}: try_error must look like ORA-00904")
    since = item.get("try_error_since", {})
    if since and ("try_error" not in item or not isinstance(since, dict) or not all(
            str(k).isdigit() and isinstance(v, str) and re.fullmatch(r"ORA-\d{5}", v) for k, v in since.items())):
        errors.append(f'{label}: try_error_since must look like {{"21": "ORA-30926"}} next to try_error')
    if "try_sql" in item:
        for stmt in split_statements(item["try_sql"]):
            if ddl_prefix and stmt.kind is StatementKind.SQL and stmt.verb in CARD_DDL_VERBS:
                if ddl_prefix not in SQL_COMMENT.sub("", stmt.text).lower():
                    errors.append(f"{label}: {stmt.verb} in try_sql must work on the card's own objects ({ddl_prefix}...)")
                continue
            if stmt.kind is not StatementKind.SQL or stmt.verb not in TRY_SQL_VERBS:
                errors.append(f"{label}: try_sql may only use {', '.join(sorted(TRY_SQL_VERBS))}, not {stmt.verb or stmt.kind}"
                              " (DDL and COMMIT would change the sample data for good)")
    return errors


def check_question(q):  # noqa: C901 - a flat checklist, one rule after the other
    errors = check_fields("question", q, QUESTION_KEYS, QUESTION_REQUIRED)
    label = f"question {q.get('id', '?')}"
    topic = q.get("topic", "")
    if not re.fullmatch(rf"q{re.escape(topic[1:])}-[a-z0-9-]+", q.get("id", "")):
        errors.append(f"{label}: id should look like q{topic[1:]}-short-name")

    options = q.get("options")
    answer = q.get("answer")
    valid_options = isinstance(options, list) and all(isinstance(o, str) and o.strip() for o in options)
    if not (valid_options and 2 <= len(options) <= MAX_OPTIONS):
        errors.append(f"{label}: options must be 2 to {MAX_OPTIONS} non-empty strings")
        return errors
    if len(set(options)) != len(options):
        errors.append(f"{label}: duplicate options")
    if not (isinstance(answer, list) and answer and all(isinstance(a, int) for a in answer)):
        errors.append(f"{label}: answer must be a non-empty list of option indexes")
        return errors
    if len(set(answer)) != len(answer):
        errors.append(f"{label}: duplicate answer indexes")
    if any(not 0 <= a < len(options) for a in answer):
        errors.append(f"{label}: answer index out of range")
    if len(answer) >= len(options):
        errors.append(f"{label}: every option is correct")

    stated = re.search(r"\bWhich (two|three|four)\b", q.get("prompt", ""), re.IGNORECASE)
    if stated and COUNT_WORDS[stated.group(1).lower()] != len(answer):
        errors.append(f"{label}: prompt says 'which {stated.group(1)}' but {len(answer)} answers are marked")
    if len(answer) > 1 and not stated:
        errors.append(f"{label}: {len(answer)} answers are marked but the prompt does not say 'Which {len(answer)}...'")

    errors += try_sql_problems(label, q)
    if "answer_sql" in q and len(answer) != 1:
        errors.append(f"{label}: answer_sql needs exactly one correct option")
    return errors


def check_card(card):
    errors = check_fields("flashcard", card, CARD_KEYS | CARD_OPTIONAL, CARD_KEYS)
    if not re.fullmatch(r"c\d{3,4}", card.get("id", "")):
        errors.append(f"flashcard {card.get('id', '?')}: id should look like c000")
    label = f"flashcard {card.get('id', '?')}"
    if "cleanup" not in card:
        return errors + try_sql_problems(label, card)
    prefix = f"lab_{card.get('id', '?').lower()}_"
    if "try_sql" not in card:
        errors.append(f"{label}: cleanup without try_sql")
    for stmt in split_statements(card["cleanup"]):
        if not CLEANUP_STATEMENT.fullmatch(stmt.text) or prefix not in stmt.text.lower():
            errors.append(f"{label}: cleanup may only drop the card's own objects (DROP TABLE {prefix}...), not: {stmt.text}")
    names = set(re.findall(r"\blab_\w+", SQL_COMMENT.sub("", card.get("try_sql", "") + "\n" + card["cleanup"]).lower()))
    if foreign := sorted(n for n in names if not n.startswith(prefix)):
        errors.append(f"{label}: LAB_ objects of a card must be named {prefix}..., not {', '.join(foreign)}")
    return errors + try_sql_problems(label, card, ddl_prefix=prefix)


def check_lab(lab):
    label = f"lab {lab.get('id', '?')}"
    kind = lab.get("kind", "query")
    if kind not in LAB_REQUIRED:
        return [f"{label}: kind must be one of {', '.join(LAB_REQUIRED)}"]
    errors = check_fields("lab", lab, LAB_REQUIRED[kind] | LAB_OPTIONAL | {"kind"}, LAB_REQUIRED[kind])
    if not re.fullmatch(r"lab-[a-z0-9-]+", lab.get("id", "")):
        errors.append(f"{label}: id should look like lab-short-name")
    if "check" in lab and not re.search(r"\bORDER\s+BY\b", lab["check"], re.IGNORECASE):
        errors.append(f"{label}: the check query needs an ORDER BY, because its row order is graded")
    if kind == "dml":
        for stmt in split_statements(lab.get("solution", "")):
            if stmt.verb not in DML_LAB_VERBS:
                errors.append(f"{label}: a dml solution may only use {', '.join(sorted(DML_LAB_VERBS))}")
    for stmt in split_statements(lab.get("cleanup", "")):
        if not CLEANUP_STATEMENT.fullmatch(stmt.text):
            errors.append(f"{label}: cleanup may only drop LAB_ objects, not: {stmt.text}")
    if "starter" in lab and kind == "ddl":
        errors.append(f"{label}: starter is for query and dml exercises only")
    if "hint2" in lab and "hint" not in lab:
        errors.append(f"{label}: hint2 without hint")
    return errors


def duplicate_ids(kind, items):
    counts = Counter(item.get("id") for item in items)
    return [f"{kind} id {i!r} is used {n} times" for i, n in counts.items() if n > 1]


def cross_pack_duplicates(packs):
    """Ids used by two packs: the app's id lookups span every pack, so one would hide the other."""
    errors = []
    kinds = {"topic": lambda p: p.topics, "section": lambda p: p.sections, "objective": lambda p: p.objectives,
             "question": lambda p: [q["id"] for q in p.questions],
             "flashcard": lambda p: [c["id"] for c in p.flashcards],
             "lab": lambda p: [lab["id"] for lab in p.labs]}
    for kind, ids_of in kinds.items():
        owner = {}
        for pack in packs.values():
            for item_id in dict.fromkeys(ids_of(pack)):  # repeats within a pack are duplicate_ids' report
                if item_id in owner:
                    errors.append(f"{kind} {item_id} is in two packs: {owner[item_id]} and {pack.id}")
                else:
                    owner[item_id] = pack.id
    return errors


def static_errors():
    errors = cross_pack_duplicates(content.PACKS)
    errors += duplicate_ids("question", content.QUESTIONS)
    errors += duplicate_ids("flashcard", content.FLASHCARDS)
    errors += duplicate_ids("lab", content.LABS)
    for q in content.QUESTIONS:
        errors += check_question(q)
    for card in content.FLASHCARDS:
        errors += check_card(card)
    for lab in content.LABS:
        errors += check_lab(lab)
    for objective in content.OBJECTIVES:
        if objective.split(".")[0] not in content.SECTIONS:
            errors.append(f"objective {objective} has no section")
    return errors


def coverage():
    """Count questions, flashcards and labs per objective."""
    table = {o: [0, 0, 0] for o in content.OBJECTIVES}
    for col, items in enumerate((content.QUESTIONS, content.FLASHCARDS, content.LABS)):
        for item in items:
            if item.get("objective") in table:
                table[item["objective"]][col] += 1
    return table


# --------------------------------------------------------------------------- translations

KIND_LABELS = {"questions": "question", "labs": "lab", "flashcards": "flashcard"}
PACK_LABELS = {"topics": "topic", "sections": "section", "objectives": "objective"}
# An option that is SQL (shown as code): it starts with a statement keyword, or matches the front end's
# inlineCode pattern. A translation must keep it byte-identical.
SQL_OPTION = re.compile(r"(?:SELECT|WITH|INSERT|UPDATE|DELETE|MERGE|CREATE|ALTER|DROP|TRUNCATE|GRANT|REVOKE|"
                        r"COMMIT|ROLLBACK|SAVEPOINT|RENAME|COMMENT|FLASHBACK|PURGE)\b|col |employees ")
# Comments, and the literals and quoted identifiers that may contain "--" or "/*" without starting one.
SQL_PIECES = re.compile(r"""[nN]?[qQ]'\[.*?\]'|[nN]?[qQ]'\{.*?\}'|[nN]?[qQ]'\(.*?\)'|[nN]?[qQ]'<.*?>'"""
                        r"""|[nN]?[qQ]'([^\s\[{(<])(?:.*?)\1'|'(?:[^']|'')*'|"[^"]*"|(--[^\n]*|/\*.*?\*/)""", re.DOTALL)
PLACEHOLDER = re.compile(r"\{\w+\}")
CODE_SPAN = re.compile(r"`[^`\n]+`")
FENCE = re.compile(r"^```[^\n]*\n(.*?)^```", re.DOTALL | re.MULTILINE)


def sql_without_comments(sql: str) -> str:
    """The SQL with its -- and /* */ comments removed, whitespace runs made one space and none kept next to
    ; , ( or ) (so a comment may sit anywhere a space may)."""
    text = SQL_PIECES.sub(lambda m: " " if m.group(2) else m.group(0), sql)
    return re.sub(r" ?([;,()]) ?", r"\1", " ".join(text.split()))


def _text_problems(name: str, value: str, source: str) -> list[str]:
    problems = []
    if Counter(PLACEHOLDER.findall(value)) != Counter(PLACEHOLDER.findall(source)):
        problems.append(f"{name} placeholders differ from the source ({', '.join(PLACEHOLDER.findall(source)) or 'none'})")
    if Counter(CODE_SPAN.findall(value)) != Counter(CODE_SPAN.findall(source)):
        problems.append(f"{name} code spans differ from the source (keep every `...` span byte-identical)")
    return problems


def _field_problems(kind: str, name: str, value, source) -> list[str]:  # noqa: C901 - one rule after the other
    """What is wrong with one translated field (empty when it is fine)."""
    if name == "options":
        if not (isinstance(value, list) and all(isinstance(o, str) for o in value)):
            return ["options must be a list of strings"]
        if len(value) != len(source):
            return [f"options has {len(value)} entries, the source has {len(source)}"]
        problems = []
        for n, (option, original) in enumerate(zip(value, source, strict=True), 1):
            if not option.strip():
                problems.append(f"option {n} is empty")
            elif SQL_OPTION.match(original) and option != original:
                problems.append(f"option {n} is SQL and must stay identical")
            else:
                problems += _text_problems(f"option {n}", option, original)
        return problems
    if not isinstance(value, str):
        return [f"{name} must be a string"]
    if not value.strip():
        return [f"{name} is empty"]
    if source is None:
        return [f"{name} has no source text to translate"]
    if name in overlays.SQL_FIELDS:
        if sql_without_comments(value) != sql_without_comments(source):
            return [f"{name} differs from the source outside comments"]
        return []
    return _text_problems(name, value, source)


def _topic_files(lang: str, topic: str | None) -> list[str]:
    stems = sorted(overlays.load(lang).files)
    return [s for s in stems if s != overlays.PACK_FILE and (topic is None or s == topic)]


def _overlay_problems(lang: str, topic: str | None, complete: bool) -> list[str]:  # noqa: C901
    overlay = overlays.load(lang)
    problems = []
    for stem in _topic_files(lang, topic):
        data = overlay.files[stem]
        label = f"{lang}/{stem}.json"
        if not isinstance(data, dict):
            problems.append(f"{label}: must be a JSON object")
            continue
        for kind in data.keys() - set(overlays.KINDS):
            problems.append(f"{label}: unknown kind {kind!r}")
        for kind in overlays.KINDS:
            entries = data.get(kind, {})
            if not isinstance(entries, dict):
                problems.append(f"{label}: {kind} must map ids to fields")
                continue
            sources = {i["id"]: i for i in _items(kind)}
            for item_id, fields in entries.items():
                where = f"{label}: {KIND_LABELS[kind]} {item_id}"
                item = sources.get(item_id)
                if item is None:
                    problems.append(f"{where}: unknown id")
                    continue
                if _source_language(kind, item) == lang:
                    problems.append(f"{where}: {lang} is the source language of {kind}")
                    continue
                if item["topic"] != stem:
                    problems.append(f"{where}: belongs to {item['topic']}, put it in {lang}/{item['topic']}.json")
                if not isinstance(fields, dict):
                    problems.append(f"{where}: must map fields to texts")
                    continue
                for name in fields.keys() - set(overlays.FIELDS[kind]):
                    problems.append(f"{where}: unknown field {name}")
                for name in fields.keys() & set(overlays.FIELDS[kind]):
                    problems += [f"{where}: {p}" for p in _field_problems(kind, name, fields[name], item.get(name))]
    if complete:
        problems += _missing_items(lang, topic)
    return problems


def _items(kind: str) -> list[dict]:
    return {"questions": content.QUESTIONS, "labs": content.LABS, "flashcards": content.FLASHCARDS}[kind]


def _source_language(kind: str, item: dict) -> str:
    return content.pack_holding(item).source_languages.get(kind, "en")


def _missing_items(lang: str, topic: str | None) -> list[str]:
    overlay = overlays.load(lang)
    problems = []
    for kind in overlays.KINDS:
        for item in _items(kind):
            if _source_language(kind, item) == lang or (topic is not None and item["topic"] != topic):
                continue
            where = f"{lang}/{item['topic']}.json: {KIND_LABELS[kind]} {item['id']}"
            found = overlay.item(kind, item["id"])
            if not found:
                problems.append(f"{where}: missing")
                continue
            problems += [f"{where}: missing {name}" for name in overlays.FIELDS[kind] if name in item and name not in found]
    return problems


def _pack_problems(lang: str, complete: bool) -> list[str]:
    overlay = overlays.load(lang)
    label = f"{lang}/{overlays.PACK_FILE}.json"
    data = overlay.files.get(overlays.PACK_FILE, {})
    problems = []
    if not isinstance(data, dict):
        return [f"{label}: must be a JSON object"]
    for pack in content.PACKS.values():
        if pack.source_languages.get("meta", "en") == lang:
            if data:
                problems.append(f"{label}: {lang} is the source language of the pack names")
            return problems
    names = {"topics": content.TOPICS, "sections": content.SECTIONS, "objectives": content.OBJECTIVES}
    for kind in data.keys() - set(names):
        problems.append(f"{label}: unknown kind {kind!r}")
    for kind, source in names.items():
        given = data.get(kind, {})
        if not isinstance(given, dict):
            problems.append(f"{label}: {kind} must map ids to names")
            continue
        for key, name in given.items():
            where = f"{label}: {PACK_LABELS[kind]} {key}"
            if key not in source:
                problems.append(f"{where}: unknown id")
            elif not (isinstance(name, str) and name.strip()):
                problems.append(f"{where}: name is empty")
        if complete:
            problems += [f"{label}: {PACK_LABELS[kind]} {key}: missing" for key in source if key not in given]
    return problems


def _note_area(rel: str) -> str:
    """The --topic value that selects a note: "docs", or the topic of topics/NN-name/ ("t06")."""
    parts = rel.split("/")
    if parts[0] == "topics" and len(parts) > 1 and parts[1][:2].isdigit():
        return f"t{parts[1][:2]}"
    return parts[0]


def _note_problems(lang: str, topic: str | None, complete: bool) -> list[str]:
    if lang == "en" or not NOTES_DIR.is_dir():
        return []
    problems = []
    english = [f for pattern in ("docs/*.md", "topics/*/*.md", "topics/*/*.sql") for f in source_files(NOTES_DIR, pattern)]
    expected = set()
    for file in english:
        rel = file.relative_to(NOTES_DIR).as_posix()
        if topic is not None and _note_area(rel) != topic:
            continue
        sibling = translated(file, lang)
        expected.add(sibling)
        label = f"notes/{sibling.relative_to(NOTES_DIR).as_posix()}"
        if not sibling.is_file():
            if complete:
                problems.append(f"notes/{rel}: missing")
            continue
        text, source = sibling.read_text("utf-8"), file.read_text("utf-8")
        if not text.strip():
            problems.append(f"{label}: is empty")
        elif file.suffix == ".sql":
            if sql_without_comments(text) != sql_without_comments(source):
                problems.append(f"{label}: differs from the English file outside comments")
        else:
            mine, theirs = FENCE.findall(text), FENCE.findall(source)
            if len(mine) != len(theirs):
                problems.append(f"{label}: {len(mine)} code blocks, the English note has {len(theirs)}")
            else:
                problems += [f"{label}: code block {n} differs from the English one outside comments"
                             for n, (a, b) in enumerate(zip(mine, theirs, strict=True), 1)
                             if sql_without_comments(a) != sql_without_comments(b)]
    for pattern in ("docs/*", "topics/*/*"):
        for file in sorted(NOTES_DIR.glob(pattern)):
            rel = file.relative_to(NOTES_DIR).as_posix()
            if (file.name.endswith((f".{lang}.md", f".{lang}.sql")) and file not in expected
                    and (topic is None or _note_area(rel) == topic)):
                original = file.with_name(file.name.replace(f".{lang}.", ".", 1)).relative_to(NOTES_DIR).as_posix()
                problems.append(f"notes/{rel}: no English note {original}")
    return problems


def translation_problems(lang: str, topic: str | None = None, complete: bool = False) -> list[str]:
    """Problems of the `lang` translations: overlays and note siblings. `topic` narrows the check to one
    topic's overlay file and notes ("t06"), the docs notes ("docs") or the pack names ("_pack")."""
    problems = []
    if topic in (None, overlays.PACK_FILE):
        problems += _pack_problems(lang, complete)
    if topic != overlays.PACK_FILE:
        if topic != "docs":
            problems += _overlay_problems(lang, topic, complete)
        problems += _note_problems(lang, topic, complete)
    return problems


def query_or_error(conn, sql):
    """Return (columns, rows) of a single query, or the error text."""
    try:
        return single_query(conn, sql)
    except Exception as exc:  # noqa: BLE001
        return first_line(format_error(exc))
    finally:
        conn.rollback()


def expected_error(q, major_version):
    """try_error, or the error newer Oracle versions raise instead (try_error_since: {"21": "ORA-30926"})."""
    since = {int(v): code for v, code in q.get("try_error_since", {}).items() if int(v) <= major_version}
    return since[max(since)] if since else q.get("try_error")


def try_sql_db_errors(database, conn, label, item):
    """try_sql runs without errors, or raises exactly its try_error."""
    if "try_sql" not in item:
        return []
    result = ScriptRunner(database).run(item["try_sql"])
    if not result["ok"]:
        return [f"cannot connect: {result['connect_error']}"]
    raised = [first_line(r["error"]) for r in result["results"] if r["type"] == "error"]
    expected = expected_error(item, int(conn.version.split(".")[0]))
    if expected and not any(e.startswith(expected) for e in raised):
        return [f"{label}: try_sql should raise {expected}, got {raised[0] if raised else 'no error'}"]
    if not expected and raised:
        return [f"{label}: try_sql failed: {raised[0]}"]
    return []


def schema_snapshot(conn, own_prefix):
    """The schema's objects, columns and constraints, and the rows of every table: what a
    flashcard sample with DDL (which commits) must leave as it found it. Other LAB_ objects
    (other items, the app's own tables) and system-named ones are left out, so checks may run
    side by side."""
    def kept(col):
        return (f"{col} NOT LIKE 'BIN$%' AND {col} NOT LIKE 'ISEQ$$%' AND {col} NOT LIKE 'SYS\\_%' ESCAPE '\\' "
                f"AND ({col} NOT LIKE 'LAB\\_%' ESCAPE '\\' OR {col} LIKE :own ESCAPE '\\')")
    own = own_prefix.upper().replace("_", "\\_") + "%"
    with conn.cursor() as cur:
        cur.execute(f"SELECT object_type, object_name FROM user_objects WHERE {kept('object_name')} ORDER BY 1, 2", own=own)
        objects = cur.fetchall()
        cur.execute("SELECT table_name, column_name, data_type, data_length, nullable FROM user_tab_columns "
                    f"WHERE {kept('table_name')} ORDER BY 1, 2", own=own)
        columns = cur.fetchall()
        cur.execute("SELECT table_name, constraint_type, status, r_constraint_name FROM user_constraints "
                    f"WHERE {kept('table_name')} ORDER BY 1, 2, 3, 4", own=own)
        constraints = cur.fetchall()
        rows = {}
        cur.execute(f"SELECT table_name FROM user_tables WHERE {kept('table_name')} "
                    "AND temporary = 'N' AND external = 'NO' ORDER BY 1", own=own)
        for (name,) in cur.fetchall():
            cur.execute("SELECT column_name, data_type FROM user_tab_columns WHERE table_name = :t ORDER BY column_id", t=name)
            # Named time zones cannot be fetched in thin mode, so those columns are compared as text
            select = ", ".join(f"TO_CHAR(\"{col}\", 'YYYY-MM-DD HH24:MI:SS.FF TZR')" if "TIME ZONE" in dtype else f'"{col}"'
                               for col, dtype in cur.fetchall())
            cur.execute(f'SELECT {select} FROM "{name}"')
            rows[name] = sorted(map(repr, cur.fetchall()))
    return objects, columns, constraints, rows


def card_db_errors(database, conn, card):
    """A sample with DDL runs between two cleanups and must leave the schema as it found it."""
    label = f"flashcard {card['id']}"
    if "cleanup" not in card:
        return try_sql_db_errors(database, conn, label, card)
    prefix = f"lab_{card['id']}_"
    run_cleanup(conn, card)
    before = schema_snapshot(conn, prefix)
    errors = try_sql_db_errors(database, conn, label, card)
    run_cleanup(conn, card)
    if schema_snapshot(conn, prefix) != before:
        errors.append(f"{label}: try_sql changed the schema or the sample data for good "
                      "(DDL commits: change only the card's own LAB_ objects, and drop them all in cleanup)")
    return errors


def question_db_errors(database, conn, q):
    label = f"question {q['id']}"
    errors = try_sql_db_errors(database, conn, label, q)

    if "answer_sql" in q:
        result = query_or_error(conn, q["answer_sql"])
        correct = q["options"][q["answer"][0]]
        if isinstance(result, str):
            errors.append(f"{label}: answer_sql failed: {result}")
        elif len(result[1]) != 1 or len(result[1][0]) != 1:
            errors.append(f"{label}: answer_sql must return one row with one column")
        elif str(result[1][0][0]) != correct:
            errors.append(f"{label}: answer_sql returns {result[1][0][0]!r}, the correct option is {correct!r}")

    if "equivalent_sql" in q:
        base = query_or_error(conn, q["equivalent_sql"])
        if isinstance(base, str):
            return errors + [f"{label}: equivalent_sql failed: {base}"]
        same = set()
        for i, option in enumerate(q["options"]):
            result = query_or_error(conn, option)
            if (not isinstance(result, str) and len(result[0]) == len(base[0])
                    and sorted(normalize_rows(result[1])) == sorted(normalize_rows(base[1]))):
                same.add(i)
        if same != set(q["answer"]):
            errors.append(f"{label}: options returning the same rows as equivalent_sql are {sorted(same)}, "
                          f"answer is {sorted(q['answer'])}")
    return errors


def starter_errors(conn, lab, columns, rows):
    """A "fix the bug" starter must fail or give a different result than the solution."""
    try:
        got = lab_result(conn, lab, lab["starter"])
    except Exception:  # noqa: BLE001
        return []
    if compare_results(lab, got[0], got[1], columns, rows)["passed"]:
        return [f"lab {lab['id']}: the starter already passes"]
    return []


def lab_db_errors(conn, lab):
    label = f"lab {lab['id']}"
    errors = []
    try:
        columns, rows = lab_result(conn, lab, lab["solution"])
    except Exception as exc:  # noqa: BLE001
        return [f"{label}: solution failed: {first_line(format_error(exc))}"]
    if "starter" in lab:
        errors += starter_errors(conn, lab, columns, rows)

    if lab_kind(lab) is LabKind.QUERY:
        named = [c.strip().upper() for c in lab["columns"].split(",")]
        if [c.upper() for c in columns] != named:
            errors.append(f"{label}: solution returns {', '.join(columns)}, task names {lab['columns']}")
        if not rows:
            errors.append(f"{label}: solution returns no rows")
        if lab["ordered"] and "ORDER" not in lab["solution"].upper():
            errors.append(f"{label}: ordered is True but the solution has no ORDER BY")
        return errors

    again = lab_result(conn, lab, lab["solution"])
    if again != (columns, rows):
        errors.append(f"{label}: the solution gives a different check result when run twice "
                      "(system-generated names, sequences or SYSDATE in the check?)")
    if lab_kind(lab) is LabKind.DDL:
        run_cleanup(conn, lab)
    before = query_or_error(conn, lab["check"])
    if before == (columns, rows):
        errors.append(f"{label}: the check query gives the same result without the solution, so doing nothing passes")
    return errors


def exams_to_check(version: str, only: str | None = None, *, engine: str) -> list[str]:
    """The exam codes to check on an `engine` database of this version: those the registry matches, or just `only`."""
    if only is not None:
        if only not in exams.EXAMS:
            raise SystemExit(f"unknown exam: {only}")
        return [only]
    return [e.code for e in exams.matching(engine, int(version.split(".")[0]))]


def database_to_check(catalog: DatabaseCatalog, only: str | None) -> tuple[Database, str]:
    """The database to check and its engine name: exam `only`'s own (else its fallback's), or the default one."""
    if only is None:
        return catalog.default, exams.engine_of_key(exams.DEFAULT_DATABASE)
    if only not in exams.EXAMS:
        raise SystemExit(f"unknown exam: {only}")
    exam = exams.EXAMS[only]
    database = catalog.for_exam(only)
    if database is None:
        raise SystemExit(f"{only} has no database configured: set {exam.database_env}")
    return database, exam.engine


def db_errors(database: Database, topic=None, only=None, engine: str | None = None):
    """The problems found on `database`, whose engine is `engine` (default: the default database's)."""
    engine = engine or exams.engine_of_key(exams.DEFAULT_DATABASE)
    label = engines.engine(engine).label
    try:
        conn = database.connect()
    except Exception as exc:  # noqa: BLE001
        return [f"cannot connect: {first_line(format_error(exc))}"]
    major = int(conn.version.split(".")[0])
    codes = exams_to_check(conn.version, only, engine=engine)
    if not codes:
        conn.close()
        return [f"no exam is checked on {label} {major}"]
    if only is not None and exams.EXAMS[only] not in exams.matching(engine, major):
        print(f"Warning: {only} is not matched to {label} {major}; its items are checked anyway.")
    errors = []
    print(f"Database: {label} {conn.version}, checking the {' and '.join(codes)} items"
          + (f" of topic {topic}" if topic else "") + ".")

    def wanted(item):
        return any(code in content.item_exams(item) for code in codes) and (topic is None or item["topic"] == topic)

    try:
        for q in filter(wanted, content.QUESTIONS):
            errors += question_db_errors(database, conn, q)
        for card in filter(wanted, content.FLASHCARDS):
            errors += card_db_errors(database, conn, card)
        for lab in filter(wanted, content.LABS):
            errors += lab_db_errors(conn, lab)
    finally:
        conn.rollback()
        conn.close()
    return errors


def run(args: argparse.Namespace, database: Database, engine: str | None = None) -> int:
    """Print the problems found; returns the exit status (1 if there are any)."""
    errors = static_errors()
    print(f"Structure: {len(content.QUESTIONS)} questions, {len(content.FLASHCARDS)} flashcards, "
          f"{len(content.LABS)} labs, {len(errors)} problem(s).")
    if getattr(args, "lang", None):
        try:
            translations = translation_problems(args.lang, args.topic, getattr(args, "complete", False))
        except json.JSONDecodeError as exc:
            translations = [f"{args.lang}: an overlay file is not valid JSON: {exc}"]
        print(f"Translations ({args.lang}): {len(translations)} problem(s).")
        errors += translations

    if not args.static and not errors:
        if args.reset:
            reset = SampleSchema(database).reset()
            if not reset["ok"]:
                print(f"Reset failed: {reset['error']}")
                return 1
        db = db_errors(database, args.topic, getattr(args, "exam", None), engine)
        print(f"Database: {len(db)} problem(s).")
        errors += db

    for e in errors:
        print("  - " + e)

    table = coverage()
    empty = [o for o, counts in table.items() if not any(counts)]
    if args.coverage:
        print("\nObjective  Questions  Cards  Labs  Title")
        for o, (nq, nc, nl) in table.items():
            print(f"{o:<9}  {nq:>9}  {nc:>5}  {nl:>4}  {content.OBJECTIVES[o]}")
    print(f"Coverage: {len(table) - len(empty)} of {len(table)} objectives have material"
          + (f"; none yet for {', '.join(empty)}." if empty else "."))
    return 1 if errors else 0
