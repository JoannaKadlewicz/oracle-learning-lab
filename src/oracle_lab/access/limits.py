"""The free plan: how much of a workspace a free user gets per day, and what they used today."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from oracle_lab.i18n import Msg
from oracle_lab.study import engine
from oracle_lab.study.state import State

KEYS = {"questions_per_day": "free_questions_per_day", "cards_per_day": "free_cards_per_day",
        "free_topics": "free_topics"}
MAXIMUM = {"questions_per_day": 1000, "cards_per_day": 1000, "free_topics": 15}
_TOPIC = re.compile(r"topics/(\d+)-")
FREE_DOCS = ("docs/exam-guide-",)


@dataclass(frozen=True)
class FreeLimits:
    questions_per_day: int = 20
    cards_per_day: int = 20
    free_topics: int = 2

    @classmethod
    def parse(cls, data: dict[str, Any]) -> FreeLimits:
        """The limits in `data` (missing ones keep their defaults); ValueError when one is not a whole number
        in range."""
        values = {}
        for name, default in vars(cls()).items():
            value = data.get(name, default)
            if isinstance(value, bool) or not isinstance(value, int) and not (isinstance(value, str) and value.isdigit()):
                raise ValueError(Msg.of("{name} must be a whole number.", name=name))
            value = int(value)
            if not 0 <= value <= MAXIMUM[name]:
                raise ValueError(Msg.of("{name} must be between 0 and {max}.", name=name, max=MAXIMUM[name]))
            values[name] = value
        return cls(**values)

    @classmethod
    def load(cls, settings) -> FreeLimits:
        """The limits an admin saved, the defaults for the ones never saved (or no longer valid)."""
        saved = {name: value for name, key in KEYS.items() if (value := settings.get(key)) is not None}
        try:
            return cls.parse(saved)
        except ValueError:
            return cls()

    def save(self, settings) -> None:
        for name, key in KEYS.items():
            settings.set(key, str(getattr(self, name)))

    def public(self) -> dict[str, int]:
        return {"questions": self.questions_per_day, "cards": self.cards_per_day, "topics": self.free_topics}


def used_today(state: State, now: float) -> dict[str, int]:
    """Answers and flashcard ratings since the start of the user's day: the recorded ones, or the day's usage
    counter when it is higher (it survives a progress reset, so resetting cannot refill the allowance)."""
    start = engine.day_start(now)
    questions = sum(1 for history in state.get("attempts", {}).values() for a in history if a.get("t", 0) >= start)
    cards = sum(1 for entry in state.get("cards", {}).values() for r in entry.get("reviews", []) if r[0] >= start)
    usage = state.get("usage", {})
    if usage.get("day") != engine.local_day(now).isoformat():
        usage = {}
    return {"questions": max(questions, usage.get("questions", 0)), "cards": max(cards, usage.get("cards", 0))}


def count_use(state: State, kind: str, now: float) -> None:
    """Adds one `kind` ("questions" or "cards") to today's usage counter in the state."""
    day = engine.local_day(now).isoformat()
    usage = state.get("usage", {})
    if usage.get("day") != day:
        usage = {"day": day, "questions": 0, "cards": 0}
    usage[kind] = usage.get(kind, 0) + 1
    state["usage"] = usage


def note_allowed(path: str, level: str, free_topics: int) -> bool:
    """Subscribers read every note; a free user the first `free_topics` topics' notes and the exam guide."""
    if level == "subscribed":
        return True
    if path.startswith(FREE_DOCS):
        return True
    match = _TOPIC.match(path)
    return bool(match) and int(match.group(1)) <= free_topics
