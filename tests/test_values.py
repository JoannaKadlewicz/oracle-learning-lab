import datetime
import decimal

import oracledb

from oracle_lab.database.values import to_json_value
from oracle_lab.sqltext.messages import describe_success


def test_numbers_are_shown_without_trailing_zeros():
    assert to_json_value(decimal.Decimal("12.50")) == "12.5"
    assert to_json_value(decimal.Decimal("100")) == "100"
    assert to_json_value(decimal.Decimal("1E+2")) == "100"
    assert to_json_value(decimal.Decimal("0.0889")) == "0.0889"


def test_dates_and_timestamps():
    assert to_json_value(datetime.datetime(2024, 1, 2, 3, 4, 5)) == "2024-01-02 03:04:05"
    assert to_json_value(datetime.datetime(2024, 1, 2, 3, 4, 5, 120000)) == "2024-01-02 03:04:05.120000"
    assert to_json_value(datetime.date(2024, 1, 2)) == "2024-01-02"


def test_other_values():
    assert to_json_value(None) is None
    assert to_json_value(b"\x0a\xff") == "0AFF"
    assert to_json_value(0.1) == "0.1"
    assert to_json_value("text") == "text"


def test_success_messages_match_sqlplus():
    assert describe_success("insert into t values (1)", 1) == "1 row inserted."
    assert describe_success("-- comment\nUPDATE t SET x = 1", 2) == "2 rows updated."
    assert describe_success("CREATE TABLE t (x NUMBER)", 0) == "Table created."
    assert describe_success("DROP INDEX i", 0) == "Index dropped."
    assert describe_success("COMMIT", 0) == "Commit complete."


def test_intervals_are_shown_like_sqlplus():
    assert to_json_value(datetime.timedelta(days=1)) == "+01 00:00:00"
    assert to_json_value(datetime.timedelta(hours=1, minutes=30)) == "+00 01:30:00"
    assert to_json_value(-datetime.timedelta(days=1, hours=2, minutes=3, seconds=4.5)) == "-01 02:03:04.500000"
    assert to_json_value(oracledb.IntervalYM(1, 6)) == "+01-06"
    assert to_json_value(oracledb.IntervalYM(0, -3)) == "-00-03"
