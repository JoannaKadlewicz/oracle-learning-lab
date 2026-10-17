"""Grading of dml and ddl labs against the database. Skipped when Oracle is not reachable."""

import pytest

import content
import server

LABS = {lab["id"]: lab for lab in content.LABS}


@pytest.fixture(scope="module", autouse=True)
def database():
    try:
        server.connect().close()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"database not reachable: {exc}")


def scalar(sql):
    conn = server.connect()
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            return cur.fetchone()[0]
    finally:
        conn.close()


def test_dml_lab_passes_the_solution_and_leaves_no_changes():
    lab = LABS["lab-programmer-raise"]
    before = scalar("SELECT SUM(salary) FROM employees")
    assert server.grade(lab, lab["solution"])["passed"]
    assert scalar("SELECT SUM(salary) FROM employees") == before


def test_dml_lab_fails_a_wrong_update():
    lab = LABS["lab-programmer-raise"]
    result = server.grade(lab, "UPDATE employees SET salary = salary * 1.1")
    assert not result["passed"]
    assert result["expected_rows"]


def test_dml_lab_rejects_commit():
    lab = LABS["lab-programmer-raise"]
    result = server.grade(lab, lab["solution"] + "\nCOMMIT;")
    assert "COMMIT is not allowed" in result["error"]


def test_dml_lab_rejects_an_empty_submission():
    assert server.grade(LABS["lab-programmer-raise"], "-- nothing")["error"] == "Write at least one statement."


def test_ddl_lab_grades_and_drops_its_objects():
    lab = LABS["lab-create-projects"]
    assert server.grade(lab, lab["solution"])["passed"]
    missing_fk = lab["solution"].replace("CONSTRAINT lab_projects_dept_fk REFERENCES departments (department_id)", "")
    assert not server.grade(lab, missing_fk)["passed"]
    assert scalar("SELECT COUNT(*) FROM user_tables WHERE table_name = 'LAB_PROJECTS'") == 0


def test_time_zone_columns_are_fetched_as_text():
    result = server.run_script("SELECT starts_at, duration, warranty FROM events WHERE event_id = 1")
    assert result["results"][0]["rows"] == [["2024-03-31 01:30:00 EUROPE/WARSAW", "+00 01:30:00", None]]


def test_join_visualizer_classifies_rows():
    result = server.visualize("SELECT e.last_name, d.department_name FROM employees e "
                              "LEFT JOIN departments d ON d.department_id = e.department_id")
    employees, departments = result["sides"]
    status = {r["cells"][2]: r["status"] for r in employees["rows"]}
    assert status["Grant"] == "null-extended" and status["King"] == "matched"
    assert [r["status"] for r in departments["rows"] if r["cells"][1] == "Research"] == ["dropped"]
    assert result["result_rows"] == 9


def test_set_visualizer_counts_rows_per_query():
    result = server.visualize("SELECT d.department_id FROM departments d MINUS SELECT e.department_id FROM employees e")
    assert [(r["cells"], r["result"]) for r in result["rows"] if r["result"]] == [(["40"], 1)]


def test_lab_run_shows_rows_before_and_after_and_rolls_back():
    before = scalar("SELECT SUM(salary) FROM employees")
    result = server.run_script("UPDATE employees SET salary = salary + 1 WHERE employee_id = 100;", inspect=True)
    entry = result["results"][0]
    change = entry["changes"]["updated"][0]
    salary = entry["changes"]["columns"].index("SALARY")
    assert change["changed"] == [salary] and int(change["after"][salary]) == int(change["before"][salary]) + 1
    assert entry["tx"]["pending"] == 1
    assert scalar("SELECT SUM(salary) FROM employees") == before


def test_lab_errors_come_with_an_explanation():
    entry = server.run_script("SELECT e.salry FROM employees e;", inspect=True)["results"][0]
    assert entry["explain"]["code"] == "ORA-00904" and "SALARY" in entry["explain"]["hint"]
