"""The exam track chosen in the settings, and what the engine sees of it."""

from __future__ import annotations

from types import SimpleNamespace

from oracle_lab import content, exams
from oracle_lab.study.state import State


def exam_code(state: State) -> str:
    """The saved exam, if the registry knows it now, else the default exam."""
    code = state.get("settings", {}).get("exam")
    return code if isinstance(code, str) and code in exams.EXAMS else exams.DEFAULT_EXAM


def track(state: State, lang: str = "en") -> SimpleNamespace:
    """The content of the exam track chosen in the settings, in `lang`."""
    return content.for_exam(exam_code(state), lang)


def mock_exam(mock: dict) -> str:
    return mock.get("exam") or content.DEFAULT_EXAM


def track_state(state: State) -> State:
    """The state as the engine sees it on the current track: only that track's mock exams."""
    code = exam_code(state)
    return {**state, "mocks": [m for m in state.get("mocks", []) if mock_exam(m) == code]}
