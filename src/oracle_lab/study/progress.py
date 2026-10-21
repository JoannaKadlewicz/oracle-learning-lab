"""What the front end needs after every change: the raw state and the computed progress."""

from __future__ import annotations

from typing import Any

from oracle_lab.study import engine
from oracle_lab.study.state import State
from oracle_lab.study.tracks import exam_code, track, track_state


def snapshot(state: State, now: float, sql_available: bool = True) -> dict[str, Any]:
    progress = engine.progress(track(state), track_state(state), now, sql_available)
    return {"state": state, "progress": {**progress, "exam": exam_code(state)}, "sql_available": sql_available}
