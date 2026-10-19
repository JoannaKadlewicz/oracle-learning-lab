"""The exam track (1Z0-071 or 1Z0-171) chosen in the settings, and what the engine sees of it."""

from __future__ import annotations

from types import SimpleNamespace

from oracle_lab import content
from oracle_lab.study.state import State


def exam_code(state: State) -> str:
    code = state.get("settings", {}).get("exam")
    return code if code in content.EXAMS else content.DEFAULT_EXAM


def track(state: State) -> SimpleNamespace:
    """The content of the exam track chosen in the settings."""
    return content.for_exam(exam_code(state))


def mock_exam(mock: dict) -> str:
    return mock.get("exam") or content.DEFAULT_EXAM


def track_state(state: State) -> State:
    """The state as the engine sees it on the current track: only that track's mock exams."""
    code = exam_code(state)
    return {**state, "mocks": [m for m in state.get("mocks", []) if mock_exam(m) == code]}
