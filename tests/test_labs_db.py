"""Grading, the SQL lab and the visualizer against the database. Skipped when Oracle is not reachable."""

import pytest

from oracle_lab import content
from oracle_lab.database.connection import DatabaseCatalog
from oracle_lab.database.executor import ScriptRunner
from oracle_lab.grading.labs import grade
from oracle_lab.services.sql_lab import SqlLabService
from oracle_lab.study.state import MemoryStateStore

LABS = {lab["id"]: lab for lab in content.LABS}


@pytest.fixture
def scalar(database):
    def run(sql):
        conn = database.connect()
        try:
            with conn.cursor() as cur:
                cur.execute(sql)
                return cur.fetchone()[0]
        finally:
            conn.close()

    return run


@pytest.fixture
def lab_service(database):
    return SqlLabService(MemoryStateStore(), DatabaseCatalog(database), clock=lambda: 1_800_000_000)


def test_dml_lab_passes_the_solution_and_leaves_no_changes(database, scalar):
    lab = LABS["lab-programmer-raise"]
    before = scalar("SELECT SUM(salary) FROM employees")
    assert grade(database, lab, lab["solution"])["passed"]
    assert scalar("SELECT SUM(salary) FROM employees") == before


def test_dml_lab_fails_a_wrong_update(database):
    result = grade(database, LABS["lab-programmer-raise"], "UPDATE employees SET salary = salary * 1.1")
    assert not result["passed"]
    assert result["expected_rows"]


def test_dml_lab_rejects_commit(database):
    lab = LABS["lab-programmer-raise"]
    assert "COMMIT is not allowed" in grade(database, lab, lab["solution"] + "\nCOMMIT;")["error"]


def test_dml_lab_rejects_an_empty_submission(database):
    assert grade(database, LABS["lab-programmer-raise"], "-- nothing")["error"] == "Write at least one statement."


def test_ddl_lab_grades_and_drops_its_objects(database, scalar):
    lab = LABS["lab-create-projects"]
    assert grade(database, lab, lab["solution"])["passed"]
    missing_fk = lab["solution"].replace("CONSTRAINT lab_projects_dept_fk REFERENCES departments (department_id)", "")
    assert not grade(database, lab, missing_fk)["passed"]
    assert scalar("SELECT COUNT(*) FROM user_tables WHERE table_name = 'LAB_PROJECTS'") == 0


def test_time_zone_columns_are_fetched_as_text(database):
    result = ScriptRunner(database).run("SELECT starts_at, duration, warranty FROM events WHERE event_id = 1")
    assert result["results"][0]["rows"] == [["2024-03-31 01:30:00 EUROPE/WARSAW", "+00 01:30:00", None]]


def test_join_visualizer_classifies_rows(lab_service):
    result = lab_service.visualize("SELECT e.last_name, d.department_name FROM employees e "
                                   "LEFT JOIN departments d ON d.department_id = e.department_id")
    employees, departments = result["sides"]
    status = {r["cells"][2]: r["status"] for r in employees["rows"]}
    assert status["Grant"] == "null-extended" and status["King"] == "matched"
    assert [r["status"] for r in departments["rows"] if r["cells"][1] == "Research"] == ["dropped"]
    assert result["result_rows"] == 9


def test_set_visualizer_counts_rows_per_query(lab_service):
    result = lab_service.visualize("SELECT d.department_id FROM departments d MINUS SELECT e.department_id FROM employees e")
    assert [(r["cells"], r["result"]) for r in result["rows"] if r["result"]] == [(["40"], 1)]


def test_lab_run_shows_rows_before_and_after_and_rolls_back(lab_service, scalar):
    before = scalar("SELECT SUM(salary) FROM employees")
    result = lab_service.run("UPDATE employees SET salary = salary + 1 WHERE employee_id = 100;", keep=False)
    entry = result["results"][0]
    change = entry["changes"]["updated"][0]
    salary = entry["changes"]["columns"].index("SALARY")
    assert change["changed"] == [salary] and int(change["after"][salary]) == int(change["before"][salary]) + 1
    assert entry["tx"]["pending"] == 1
    assert scalar("SELECT SUM(salary) FROM employees") == before
    assert result["history"][-1]["sql"].startswith("UPDATE employees")


def test_lab_errors_come_with_an_explanation(lab_service):
    entry = lab_service.run("SELECT e.salry FROM employees e;", keep=False)["results"][0]
    assert entry["explain"]["code"] == "ORA-00904" and "SALARY" in entry["explain"]["hint"]


def test_schema_browser_lists_the_sample_tables(lab_service):
    schema = lab_service.schema()
    assert schema["ok"] and "EMPLOYEES" in {t["name"] for t in schema["tables"]}
    assert schema["database"]["major"] >= 19
