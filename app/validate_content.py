"""Check the study content before using it.

Run from the repository root:
    .venv/bin/python app/validate_content.py            # structure + database checks
    .venv/bin/python app/validate_content.py --static   # structure only, no database
    .venv/bin/python app/validate_content.py --reset    # reset the sample data first
    .venv/bin/python app/validate_content.py --topic t08  # database checks for one topic only

Structure checks: unique IDs, valid topics and objectives, valid answer indexes,
"Which two/three" prompts matching the number of answers, known fields only,
try_sql without DDL or COMMIT, lab cleanup that only drops LAB_ objects.
Database checks:
  - every try_sql runs, or raises exactly its try_error
  - answer_sql returns exactly the text of the correct option
  - equivalent_sql: exactly the correct options return the same rows as this query
  - query labs: the solution runs, returns rows and the columns the task names
  - dml/ddl labs: the solution changes the check result, and gives the same result twice
  - labs with a starter (a "fix the bug" exercise): the starter does not already pass
Items are checked on the database of their exam track: Oracle 23ai or later checks the 1Z0-171
items, older versions the 1Z0-071 items (an item's "exams" field, else its topic's, else both).
Changes are rolled back. --reset drops and recreates the ORASTUDY sample tables.
Exits with status 1 if any check fails.
"""

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import content  # noqa: E402
import server  # noqa: E402

QUESTION_KEYS = {"id", "topic", "objective", "prompt", "code", "options", "answer", "explanation",
                 "try_sql", "try_error", "try_error_since", "answer_sql", "equivalent_sql", "exams"}
QUESTION_REQUIRED = {"id", "topic", "objective", "prompt", "options", "answer", "explanation"}
CARD_KEYS = {"id", "topic", "objective", "front", "back"}
CARD_OPTIONAL = {"exams"}
LAB_COMMON = {"id", "topic", "objective", "title", "task", "solution"}
LAB_REQUIRED = {
    "query": LAB_COMMON | {"columns", "ordered"},
    "dml": LAB_COMMON | {"kind", "check"},
    "ddl": LAB_COMMON | {"kind", "check", "cleanup"},
}
LAB_OPTIONAL = {"hint", "hint2", "exams", "starter"}
TRY_SQL_VERBS = {"SELECT", "WITH", "INSERT", "UPDATE", "DELETE", "MERGE", "SAVEPOINT", "ROLLBACK"}
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
    if missing := required - item.keys():
        errors.append(f"{label}: missing {', '.join(sorted(missing))}")
    if unknown := item.keys() - allowed:
        errors.append(f"{label}: unknown field {', '.join(sorted(unknown))}")
    for key in item.keys() & allowed:
        if key == "ordered":
            if not isinstance(item[key], bool):
                errors.append(f"{label}: ordered must be True or False")
        elif key == "exams":
            if not (isinstance(item[key], list) and item[key] and set(item[key]) <= set(content.EXAMS)):
                errors.append(f"{label}: exams must be a non-empty list of {', '.join(content.EXAMS)}")
            elif not set(item[key]) <= set(content.TOPIC_EXAMS.get(item.get("topic"), content.EXAMS)):
                errors.append(f"{label}: exams lists an exam its topic is not part of")
        elif key not in ("options", "answer", "try_error_since") and not (isinstance(item[key], str) and item[key].strip()):
            errors.append(f"{label}: {key} must be a non-empty string")
    if item.get("topic") not in content.TOPICS:
        errors.append(f"{label}: unknown topic {item.get('topic')!r}")
    if item.get("objective") not in content.OBJECTIVES:
        errors.append(f"{label}: unknown objective {item.get('objective')!r}")
    elif not set(content.item_exams(item)) <= set(content.SECTION_EXAMS.get(item["objective"].split(".")[0], content.EXAMS)):
        errors.append(f"{label}: objective {item['objective']} is not part of {', '.join(content.item_exams(item))}")
    return errors


def check_question(q):
    errors = check_fields("question", q, QUESTION_KEYS, QUESTION_REQUIRED)
    label = f"question {q.get('id', '?')}"
    topic = q.get("topic", "")
    if not re.fullmatch(rf"q{re.escape(topic[1:])}-[a-z0-9-]+", q.get("id", "")):
        errors.append(f"{label}: id should look like q{topic[1:]}-short-name")

    options = q.get("options")
    answer = q.get("answer")
    if not (isinstance(options, list) and 2 <= len(options) <= MAX_OPTIONS and all(isinstance(o, str) and o.strip() for o in options)):
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

    if "try_error" in q:
        if "try_sql" not in q:
            errors.append(f"{label}: try_error without try_sql")
        if not re.fullmatch(r"ORA-\d{5}", q["try_error"]):
            errors.append(f"{label}: try_error must look like ORA-00904")
    since = q.get("try_error_since", {})
    if since and ("try_error" not in q or not isinstance(since, dict) or not all(
            str(k).isdigit() and isinstance(v, str) and re.fullmatch(r"ORA-\d{5}", v) for k, v in since.items())):
        errors.append(f'{label}: try_error_since must look like {{"21": "ORA-30926"}} next to try_error')
    if "try_sql" in q:
        for stmt in server.split_statements(q["try_sql"]):
            verb = server.first_word(stmt["text"])[0]
            if stmt["kind"] != "sql" or verb not in TRY_SQL_VERBS:
                errors.append(f"{label}: try_sql may only use {', '.join(sorted(TRY_SQL_VERBS))}, not {verb or stmt['kind']}"
                              " (DDL and COMMIT would change the sample data for good)")
    if "answer_sql" in q and len(answer) != 1:
        errors.append(f"{label}: answer_sql needs exactly one correct option")
    return errors


def check_card(card):
    errors = check_fields("flashcard", card, CARD_KEYS | CARD_OPTIONAL, CARD_KEYS)
    if not re.fullmatch(r"c\d{3,4}", card.get("id", "")):
        errors.append(f"flashcard {card.get('id', '?')}: id should look like c000")
    return errors


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
        for stmt in server.split_statements(lab.get("solution", "")):
            if server.first_word(stmt["text"])[0] not in server.DML_LAB_VERBS:
                errors.append(f"{label}: a dml solution may only use {', '.join(sorted(server.DML_LAB_VERBS))}")
    for stmt in server.split_statements(lab.get("cleanup", "")):
        if not CLEANUP_STATEMENT.fullmatch(stmt["text"]):
            errors.append(f"{label}: cleanup may only drop LAB_ objects, not: {stmt['text']}")
    if "starter" in lab and kind == "ddl":
        errors.append(f"{label}: starter is for query and dml exercises only")
    if "hint2" in lab and "hint" not in lab:
        errors.append(f"{label}: hint2 without hint")
    return errors


def duplicate_ids(kind, items):
    counts = Counter(item.get("id") for item in items)
    return [f"{kind} id {i!r} is used {n} times" for i, n in counts.items() if n > 1]


def static_errors():
    errors = []
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


def first_line(text):
    return text.strip().splitlines()[0] if text.strip() else text


def query_or_error(conn, sql):
    """Return (columns, rows) of a single query, or the error text."""
    try:
        return server.single_query(conn, sql)
    except Exception as exc:  # noqa: BLE001
        return first_line(server.format_error(exc))
    finally:
        conn.rollback()


def expected_error(q, major_version):
    """try_error, or the error newer Oracle versions raise instead (try_error_since: {"21": "ORA-30926"})."""
    since = {int(v): code for v, code in q.get("try_error_since", {}).items() if int(v) <= major_version}
    return since[max(since)] if since else q.get("try_error")


def question_db_errors(conn, q):
    errors = []
    label = f"question {q['id']}"
    if "try_sql" in q:
        result = server.run_script(q["try_sql"])
        if not result["ok"]:
            return [f"cannot connect: {result['connect_error']}"]
        raised = [first_line(r["error"]) for r in result["results"] if r["type"] == "error"]
        expected = expected_error(q, int(conn.version.split(".")[0]))
        if expected and not any(e.startswith(expected) for e in raised):
            errors.append(f"{label}: try_sql should raise {expected}, got {raised[0] if raised else 'no error'}")
        elif not expected and raised:
            errors.append(f"{label}: try_sql failed: {raised[0]}")

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
                    and sorted(server.normalize_rows(result[1])) == sorted(server.normalize_rows(base[1]))):
                same.add(i)
        if same != set(q["answer"]):
            errors.append(f"{label}: options returning the same rows as equivalent_sql are {sorted(same)}, "
                          f"answer is {sorted(q['answer'])}")
    return errors


def starter_errors(conn, lab, columns, rows):
    """A "fix the bug" starter must fail or give a different result than the solution."""
    try:
        got = server.lab_result(conn, lab, lab["starter"])
    except Exception:  # noqa: BLE001
        return []
    if server.compare_results(lab, got[0], got[1], columns, rows)["passed"]:
        return [f"lab {lab['id']}: the starter already passes"]
    return []


def lab_db_errors(conn, lab):
    label = f"lab {lab['id']}"
    errors = []
    try:
        columns, rows = server.lab_result(conn, lab, lab["solution"])
    except Exception as exc:  # noqa: BLE001
        return [f"{label}: solution failed: {first_line(server.format_error(exc))}"]
    if "starter" in lab:
        errors += starter_errors(conn, lab, columns, rows)

    if server.lab_kind(lab) == "query":
        named = [c.strip().upper() for c in lab["columns"].split(",")]
        if [c.upper() for c in columns] != named:
            errors.append(f"{label}: solution returns {', '.join(columns)}, task names {lab['columns']}")
        if not rows:
            errors.append(f"{label}: solution returns no rows")
        if lab["ordered"] and "ORDER" not in lab["solution"].upper():
            errors.append(f"{label}: ordered is True but the solution has no ORDER BY")
        return errors

    again = server.lab_result(conn, lab, lab["solution"])
    if again != (columns, rows):
        errors.append(f"{label}: the solution gives a different check result when run twice "
                      "(system-generated names, sequences or SYSDATE in the check?)")
    if server.lab_kind(lab) == "ddl":
        server.run_cleanup(conn, lab)
    before = query_or_error(conn, lab["check"])
    if before == (columns, rows):
        errors.append(f"{label}: the check query gives the same result without the solution, so doing nothing passes")
    return errors


def track_of(conn):
    """The exam track a database checks: 1Z0-171 on Oracle 23ai or later, else 1Z0-071."""
    return "1Z0-171" if int(conn.version.split(".")[0]) >= 23 else "1Z0-071"


def db_errors(topic=None):
    try:
        conn = server.connect()
    except Exception as exc:  # noqa: BLE001
        return [f"cannot connect: {first_line(server.format_error(exc))}"]
    errors = []
    track = track_of(conn)
    print(f"Database: Oracle {conn.version}, checking the {track} items"
          + (f" of topic {topic}" if topic else "") + ".")

    def wanted(item):
        return track in content.item_exams(item) and (topic is None or item["topic"] == topic)

    try:
        for q in filter(wanted, content.QUESTIONS):
            errors += question_db_errors(conn, q)
        for lab in filter(wanted, content.LABS):
            errors += lab_db_errors(conn, lab)
    finally:
        conn.rollback()
        conn.close()
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--static", action="store_true", help="skip the database checks")
    parser.add_argument("--reset", action="store_true", help="reset the sample data before the database checks")
    parser.add_argument("--coverage", action="store_true", help="print item counts per objective")
    parser.add_argument("--topic", help="run the database checks for one topic only, for example t08")
    args = parser.parse_args()

    errors = static_errors()
    print(f"Structure: {len(content.QUESTIONS)} questions, {len(content.FLASHCARDS)} flashcards, "
          f"{len(content.LABS)} labs, {len(errors)} problem(s).")

    if not args.static and not errors:
        if args.reset:
            reset = server.reset_sample_data()
            if not reset["ok"]:
                print(f"Reset failed: {reset['error']}")
                return 1
        db = db_errors(args.topic)
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


if __name__ == "__main__":
    sys.exit(main())
