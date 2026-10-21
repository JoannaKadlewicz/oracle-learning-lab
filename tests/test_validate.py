import pytest

from oracle_lab.tools import validate_content as v


def test_exams_to_check_by_version():
    assert v.exams_to_check("19.3.0.0.0") == ["1Z0-071"]
    assert v.exams_to_check("21.3.0.0.0") == ["1Z0-071"]
    assert v.exams_to_check("23.5.0.24.7") == ["1Z0-171"]
    assert v.exams_to_check("19.3.0.0.0", only="1Z0-171") == ["1Z0-171"]


def test_exams_to_check_unknown_exam():
    with pytest.raises(SystemExit, match="unknown exam: X"):
        v.exams_to_check("19.3.0.0.0", only="X")
