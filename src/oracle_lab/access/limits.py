"""Today's usage of the limited things (answers, flashcard ratings, solved exercises and checked answers) and which
lessons a plan reads."""

from __future__ import annotations

import re

from oracle_lab.study import engine
from oracle_lab.study.state import State

_TOPIC = re.compile(r"topics/(\d+)-")
FREE_DOCS = ("docs/exam-guide-",)
KINDS = ("questions", "cards", "exercises", "checks")
# A plan's daily exercises count only the solved ones; checking answers has its own cap, this many per exercise,
# so "Check" cannot stand in for the SQL lab (a wrong answer still shows the rows the query returned).
CHECKS_PER_EXERCISE = 10


def used_today(state: State, now: float) -> dict[str, int]:
    """Answers and flashcard ratings since the start of the user's day: the recorded ones, or the day's usage
    counter when it is higher (it survives a progress reset, so resetting cannot refill the allowance). Solved
    exercises and checked answers come from the counter only."""
    start = engine.day_start(now)
    questions = sum(1 for history in state.get("attempts", {}).values() for a in history if a.get("t", 0) >= start)
    cards = sum(1 for entry in state.get("cards", {}).values() for r in entry.get("reviews", []) if r[0] >= start)
    usage = state.get("usage", {})
    if usage.get("day") != engine.local_day(now).isoformat():
        usage = {}
    return {"questions": max(questions, usage.get("questions", 0)), "cards": max(cards, usage.get("cards", 0)),
            "exercises": usage.get("exercises", 0), "checks": usage.get("checks", 0)}


def _today(state: State, now: float) -> dict:
    """Today's usage counter in the state, started afresh on a new day."""
    day = engine.local_day(now).isoformat()
    if state.get("usage", {}).get("day") != day:
        state["usage"] = {"day": day, **dict.fromkeys(KINDS, 0), "solved": []}
    return state["usage"]


def count_use(state: State, kind: str, now: float) -> None:
    """Adds one `kind` (one of KINDS) to today's usage counter in the state."""
    usage = _today(state, now)
    usage[kind] = usage.get(kind, 0) + 1


def count_solved(state: State, lab_id: str, now: float) -> bool:
    """Counts a solved exercise once a day: True when `lab_id` was not solved yet today."""
    usage = _today(state, now)
    solved = usage.setdefault("solved", [])
    if lab_id in solved:
        return False
    solved.append(lab_id)
    usage["exercises"] = usage.get("exercises", 0) + 1
    return True


def note_allowed(path: str, topics: int | None) -> bool:
    """Every note when `topics` is None; else the first `topics` topics' notes and the exam guide."""
    if topics is None:
        return True
    if path.startswith(FREE_DOCS):
        return True
    match = _TOPIC.match(path)
    return bool(match) and int(match.group(1)) <= topics
