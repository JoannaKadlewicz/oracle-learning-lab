import copy

import pytest

from oracle_lab import content
from oracle_lab.tools import validate_content


def test_content_is_valid():
    assert validate_content.static_errors() == []


def test_every_topic_has_questions_and_flashcards():
    for topic in content.TOPICS:
        assert any(q["topic"] == topic for q in content.QUESTIONS), topic
        assert any(c["topic"] == topic for c in content.FLASHCARDS), topic


def test_exam_tracks_keep_23ai_content_out_of_1z0_071():
    old, new = content.for_exam("1Z0-071"), content.for_exam("1Z0-171")
    assert "t15" not in old.TOPICS and "17.1" not in old.OBJECTIVES
    assert all(q["topic"] != "t15" and q["objective"] in old.OBJECTIVES for q in old.QUESTIONS)
    assert all(q["objective"] in new.OBJECTIVES for q in new.QUESTIONS)
    assert [q for q in old.QUESTIONS if "1Z0-171" not in content.item_exams(q)]  # 19c-only behavior
    assert old.EXAM["questions"] == 63 and new.EXAM["questions"] == 60


@pytest.fixture
def broken_question(monkeypatch):
    """Append a copy of the first two-answer question and return it for breaking."""
    questions = copy.deepcopy(content.QUESTIONS)
    q = copy.deepcopy(next(q for q in questions if len(q["answer"]) == 2))
    q["id"] = q["id"] + "-copy"
    questions.append(q)
    monkeypatch.setattr(content, "QUESTIONS", questions)
    return q


def errors_for(q):
    return [e for e in validate_content.static_errors() if q["id"] in e]


def test_detects_answer_out_of_range(broken_question):
    broken_question["answer"] = [0, 9]
    assert any("out of range" in e for e in errors_for(broken_question))


def test_detects_prompt_and_answer_count_mismatch(broken_question):
    broken_question["answer"] = [0]
    assert any("which two" in e for e in errors_for(broken_question))


def test_detects_unknown_objective(broken_question):
    broken_question["objective"] = "99.9"
    assert any("unknown objective" in e for e in errors_for(broken_question))


def test_detects_unknown_field(broken_question):
    broken_question["anwser"] = [0]
    assert any("unknown field anwser" in e for e in errors_for(broken_question))


def test_detects_duplicate_ids(broken_question):
    broken_question["id"] = content.QUESTIONS[0]["id"]
    assert any("used 2 times" in e for e in validate_content.static_errors())


def test_content_runs_against_the_database(database):
    assert validate_content.db_errors(database) == []


@pytest.fixture
def broken_lab(monkeypatch):
    """Append a copy of the DDL lab and return it for breaking."""
    labs = copy.deepcopy(content.LABS)
    lab = copy.deepcopy(next(lab for lab in labs if lab.get("kind") == "ddl"))
    lab["id"] = lab["id"] + "-copy"
    labs.append(lab)
    monkeypatch.setattr(content, "LABS", labs)
    return lab


def lab_errors_for(lab):
    return [e for e in validate_content.static_errors() if lab["id"] in e]


def test_detects_cleanup_of_sample_tables(broken_lab):
    broken_lab["cleanup"] = "DROP TABLE employees PURGE;"
    assert any("cleanup may only drop LAB_ objects" in e for e in lab_errors_for(broken_lab))


def test_detects_check_query_without_order_by(broken_lab):
    broken_lab["check"] = "SELECT table_name FROM user_tables WHERE table_name = 'LAB_PROJECTS'"
    assert any("needs an ORDER BY" in e for e in lab_errors_for(broken_lab))


def test_detects_missing_fields_for_the_lab_kind(broken_lab):
    del broken_lab["cleanup"]
    assert any("missing cleanup" in e for e in lab_errors_for(broken_lab))


def test_detects_ddl_in_try_sql(broken_question):
    broken_question["try_sql"] = "CREATE TABLE t (x NUMBER);"
    assert any("try_sql may only use" in e for e in errors_for(broken_question))


def test_newer_oracle_versions_can_expect_a_different_error():
    q = {"try_error": "ORA-01427", "try_error_since": {"21": "ORA-30926"}}
    assert validate_content.expected_error(q, 19) == "ORA-01427"
    assert validate_content.expected_error(q, 21) == validate_content.expected_error(q, 23) == "ORA-30926"
    assert validate_content.expected_error({"try_error": "ORA-00904"}, 23) == "ORA-00904"


def test_detects_malformed_try_error_since(broken_question):
    broken_question["try_sql"] = "SELECT 1 FROM dual"
    broken_question["try_error_since"] = {"21": "30926"}
    assert any("try_error_since must look like" in e for e in errors_for(broken_question))
