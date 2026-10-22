"""Today's usage of the limited things (answers, flashcard ratings, graded exercises) and which lessons a plan reads."""

from __future__ import annotations

import re

from oracle_lab.study import engine
from oracle_lab.study.state import State

_TOPIC = re.compile(r"topics/(\d+)-")
FREE_DOCS = ("docs/exam-guide-",)
KINDS = ("questions", "cards", "exercises")


def used_today(state: State, now: float) -> dict[str, int]:
    """Answers and flashcard ratings since the start of the user's day: the recorded ones, or the day's usage
    counter when it is higher (it survives a progress reset, so resetting cannot refill the allowance)."""
    start = engine.day_start(now)
    questions = sum(1 for history in state.get("attempts", {}).values() for a in history if a.get("t", 0) >= start)
    cards = sum(1 for entry in state.get("cards", {}).values() for r in entry.get("reviews", []) if r[0] >= start)
    usage = state.get("usage", {})
    if usage.get("day") != engine.local_day(now).isoformat():
        usage = {}
    return {"questions": max(questions, usage.get("questions", 0)), "cards": max(cards, usage.get("cards", 0)),
            "exercises": usage.get("exercises", 0)}


def count_use(state: State, kind: str, now: float) -> None:
    """Adds one `kind` ("questions" or "cards") to today's usage counter in the state."""
    day = engine.local_day(now).isoformat()
    usage = state.get("usage", {})
    if usage.get("day") != day:
        usage = {"day": day, **dict.fromkeys(KINDS, 0)}
    usage[kind] = usage.get(kind, 0) + 1
    state["usage"] = usage


def note_allowed(path: str, topics: int | None) -> bool:
    """Every note when `topics` is None; else the first `topics` topics' notes and the exam guide."""
    if topics is None:
        return True
    if path.startswith(FREE_DOCS):
        return True
    match = _TOPIC.match(path)
    return bool(match) and int(match.group(1)) <= topics
