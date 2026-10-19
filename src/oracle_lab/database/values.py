"""Convert fetched Oracle values to JSON, formatted the way SQL*Plus shows them."""

from __future__ import annotations

import datetime
import decimal
from typing import Any

import oracledb


def to_json_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, decimal.Decimal):
        return format(value.normalize(), "f") if value == value.to_integral() else str(value.normalize())
    if isinstance(value, datetime.datetime):
        if value.microsecond:
            return value.isoformat(sep=" ")
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, datetime.timedelta):
        return format_interval_ds(value)
    if isinstance(value, oracledb.IntervalYM):
        sign = "-" if value.years < 0 or value.months < 0 else "+"
        return f"{sign}{abs(value.years):02d}-{abs(value.months):02d}"
    if isinstance(value, datetime.date):
        return str(value)
    if isinstance(value, (bytes, bytearray)):
        return value.hex().upper()
    if hasattr(value, "read"):  # LOB
        return value.read()
    if isinstance(value, float):
        return repr(value)
    return value if isinstance(value, (int, str, bool)) else str(value)


def to_json_row(row: tuple) -> list:
    return [to_json_value(v) for v in row]


def format_interval_ds(delta: datetime.timedelta) -> str:
    """Format like SQL*Plus shows INTERVAL DAY TO SECOND: +01 02:03:04 or -00 00:00:01.500000."""
    sign = "-" if delta < datetime.timedelta(0) else "+"
    delta = abs(delta)
    hours, rest = divmod(delta.seconds, 3600)
    minutes, seconds = divmod(rest, 60)
    text = f"{sign}{delta.days:02d} {hours:02d}:{minutes:02d}:{seconds:02d}"
    return text + (f".{delta.microseconds:06d}" if delta.microseconds else "")
