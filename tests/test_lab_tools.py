"""Error explanations, SQL text helpers, history and personal notes (no database needed)."""

from oracle_lab.analysis import error_hints as errors
from oracle_lab.database.executor import DML_TARGET, Transaction
from oracle_lab.sqltext import clauses as sqltext
from oracle_lab.study.notes import FileNotes, NotesLibrary
from oracle_lab.study.recording import HISTORY_LIMIT, record_history


class FakeSchema:
    def columns(self):
        return {"EMPLOYEES": ["EMPLOYEE_ID", "LAST_NAME", "SALARY", "DEPARTMENT_ID"],
                "DEPARTMENTS": ["DEPARTMENT_ID", "DEPARTMENT_NAME"]}

    def constraint(self, name):
        return {"table": "ORDERS", "type": "R", "condition": None, "r_table": "CUSTOMERS",
                "columns": ["CUSTOMER_ID"], "r_columns": ["CUSTOMER_ID"]}


def test_every_explained_error_links_to_a_topic_note():
    for code, (title, text, topic) in errors.ERRORS.items():
        assert code.startswith("ORA-") and title and text and topic in errors.NOTES


def test_alias_used_in_where():
    hint = errors.explain('ORA-00904: "ANNUAL": invalid identifier',
                          "SELECT e.salary * 12 annual FROM employees e WHERE annual > 1", FakeSchema())["hint"]
    assert "ANNUAL is a column alias" in hint and "WHERE" in hint


def test_misspelled_column_gets_a_suggestion():
    hint = errors.explain('ORA-00904: "E"."SALRY": invalid identifier', "SELECT e.salry FROM employees e", FakeSchema())["hint"]
    assert hint == "No column is called SALRY. Did you mean SALARY (EMPLOYEES)?"


def test_group_by_hint_names_the_missing_column():
    hint = errors.explain("ORA-00979: not a GROUP BY expression",
                          "SELECT e.department_id, e.last_name, COUNT(*) FROM employees e GROUP BY e.department_id",
                          FakeSchema())["hint"]
    assert "e.last_name is not inside a group function" in hint


def test_foreign_key_hint_names_the_parent():
    hint = errors.explain("ORA-02291: integrity constraint (ORASTUDY.ORDERS_CUSTOMER_FK) violated - parent key not found",
                          "INSERT INTO orders ...", FakeSchema())["hint"]
    assert hint.startswith("ORDERS.CUSTOMER_ID must match an existing CUSTOMER_ID in CUSTOMERS")


def test_unknown_codes_and_broken_hints_are_safe():
    assert errors.explain("ORA-99999: something", "SELECT 1 FROM dual", FakeSchema()) is None
    assert errors.explain("no code at all", "", FakeSchema()) is None
    broken = errors.explain('ORA-00904: "X": invalid identifier', "SELECT (((", None)  # ctx None: hint fails quietly
    assert broken["hint"] is None and broken["title"] == "Invalid identifier"


def test_select_parts_and_from_tables():
    parts = sqltext.select_parts("SELECT DISTINCT e.a, b x FROM employees e LEFT OUTER JOIN departments d ON 1 = 1 "
                                 "WHERE (SELECT 1 FROM dual) = 1 GROUP BY e.a ORDER BY 1;")
    assert parts["distinct"] and parts["select"] == "e.a, b x" and parts["group"] == "e.a"
    assert sqltext.from_tables(parts["from"]) == [
        {"table": "EMPLOYEES", "alias": "E", "join": None}, {"table": "DEPARTMENTS", "alias": "D", "join": "LEFT JOIN"}]
    assert sqltext.from_tables("(SELECT 1 FROM dual) x") is None


def test_set_operators_keep_the_final_order_by_apart():
    assert sqltext.split_set_operators("SELECT a FROM t UNION ALL (SELECT b FROM u) ORDER BY 1") == (
        ["SELECT a FROM t", "SELECT b FROM u"], ["UNION ALL"], "ORDER BY 1")
    assert sqltext.split_set_operators("SELECT 'a UNION b' FROM t") is None


def test_transaction_tracks_savepoints_and_ddl_commits():
    tx = Transaction()
    assert tx.after("UPDATE t SET x = 1", 3)["pending"] == 3
    assert tx.after("SAVEPOINT a", 0)["savepoints"] == ["A"]
    assert tx.after("DELETE FROM t", 2)["pending"] == 5
    assert tx.after("ROLLBACK TO SAVEPOINT a", 0) == {"pending": 3, "savepoints": ["A"], "note": None}
    state = tx.after("CREATE TABLE x (n NUMBER)", 0)
    assert state["pending"] == 0 and "committed 3 pending row changes" in state["note"]


def test_history_moves_repeated_sql_to_the_top_and_is_capped():
    state = {}
    for n in range(HISTORY_LIMIT + 5):
        record_history(state, f"SELECT {n} FROM dual", {"ok": True, "results": [{"type": "rows"}]}, n)
    record_history(state, "SELECT 10 FROM dual", {"ok": True, "results": [{"type": "error"}]}, 999)
    assert len(state["history"]) == HISTORY_LIMIT
    assert state["history"][-1] == {"t": 999, "sql": "SELECT 10 FROM dual", "statements": 1, "errors": 1}


def test_personal_notes_get_unique_safe_file_names(tmp_path):
    notes = NotesLibrary(tmp_path / "builtin", FileNotes(tmp_path / "personal"))
    first = notes.save("Outer joins: ../../etc", "SELECT 1 FROM dual;", 1_800_000_000)
    second = notes.save("Outer joins: ../../etc", "SELECT 2 FROM dual;", 1_800_000_000)
    assert first.startswith("personal/") and first.endswith("-outer-joins-etc.md")
    assert second.endswith("-outer-joins-etc-2.md")
    assert "```sql\nSELECT 1 FROM dual;\n```" in (tmp_path / first).read_text()
    assert [n["title"] for n in notes.list() if n["path"].startswith("personal/")] == [
        "My notes / Outer joins: ../../etc"] * 2


def test_only_listed_notes_can_be_read(tmp_path):
    (tmp_path / "builtin" / "docs").mkdir(parents=True)
    (tmp_path / "builtin" / "docs" / "cheat-sheet.md").write_text("# Cheat sheet")
    (tmp_path / "secret.txt").write_text("password")
    notes = NotesLibrary(tmp_path / "builtin", FileNotes(tmp_path / "personal"))
    assert notes.read("docs/cheat-sheet.md") == "# Cheat sheet"
    assert notes.read("../secret.txt") is None and notes.read("personal/../../secret.txt") is None


def test_dml_target_table_is_found_for_every_dml_form():
    found = {sql: DML_TARGET.match(sql).group(1) for sql in (
        "DELETE FROM order_items WHERE 1 = 1", "DELETE order_items", "UPDATE employees e SET x = 1",
        "INSERT INTO departments VALUES (1)", "MERGE INTO orastudy.products p USING dual ON (1 = 1)")}
    assert list(found.values()) == ["order_items", "order_items", "employees", "departments", "orastudy.products"]


def test_notes_listing_can_be_limited_to_a_packs_globs(tmp_path):
    builtin = tmp_path / "builtin"
    (builtin / "docs").mkdir(parents=True)
    (builtin / "topics" / "01-select").mkdir(parents=True)
    (builtin / "docs" / "cheat-sheet.md").write_text("# Cheat sheet")
    (builtin / "topics" / "01-select" / "notes.md").write_text("# Select")
    notes = NotesLibrary(builtin, FileNotes(tmp_path / "personal"))
    notes.save("Mine", "SELECT 1 FROM dual;", 1_800_000_000)
    everything = [n["path"] for n in notes.list()]
    assert notes.list(None) == notes.list() and "topics/01-select/notes.md" in everything
    limited = [n["path"] for n in notes.list(("docs/*.md",))]
    assert "docs/cheat-sheet.md" in limited and not [p for p in limited if p.startswith("topics/")]
    assert [p for p in limited if p.startswith("personal/")]
    assert notes.read("topics/01-select/notes.md", globs=("docs/*.md",)) is None
    assert notes.read("topics/01-select/notes.md") == "# Select"
