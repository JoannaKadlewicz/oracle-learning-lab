"""Changes to the study state: answers, flashcard reviews, exercises, settings, SQL lab history.

Every function validates its input against the content and raises ValueError for bad input,
so callers never store anything the engine cannot read.
"""

from __future__ import annotations

import datetime
from typing import Any

from oracle_lab import content, exams
from oracle_lab.i18n import LANGUAGES, Msg
from oracle_lab.study import engine
from oracle_lab.study.state import State

QUESTIONS_BY_ID = {q["id"]: q for q in content.QUESTIONS}
CARD_IDS = {c["id"] for c in content.FLASHCARDS}
LAB_IDS = {lab["id"] for lab in content.LABS}
HISTORY_LIMIT = 100
DAILY_MINUTES_RANGE = (5, 480)


def valid_choices(question: dict, chosen: list) -> list[int]:
    """The chosen option indexes that exist, sorted and without duplicates."""
    return sorted({int(i) for i in chosen if 0 <= int(i) < len(question["options"])})


def valid_confidence(value: Any) -> str | None:
    return value if value in engine.CONFIDENCE else None


def record_attempt(state: State, data: dict, now: float) -> None:
    """Record an answer. The server decides whether it is correct; the client's opinion is ignored."""
    q = QUESTIONS_BY_ID[data["id"]]
    chosen = valid_choices(q, data.get("chosen", []))
    state["attempts"].setdefault(q["id"], []).append({
        "t": now,
        "correct": chosen == sorted(q["answer"]),
        "chosen": chosen,
        "confidence": valid_confidence(data.get("confidence")),
        "mode": "exam" if data.get("mode") == "exam" else "practice",
    })


def record_card(state: State, data: dict, now: float) -> None:
    if data.get("id") not in CARD_IDS or data.get("rating") not in engine.CARD_RATINGS:
        raise ValueError("unknown card or rating")
    state["cards"].setdefault(data["id"], {"reviews": []})["reviews"].append([now, data["rating"]])


def _lab_entry(state: State, lab_id: str) -> dict:
    return state["labs"].setdefault(lab_id, {"tries": 0, "passed": False})


def record_lab_result(state: State, lab_id: str, sql: str, passed: bool, now: float) -> None:
    entry = _lab_entry(state, lab_id)
    entry["tries"] += 1
    entry["passed"] = entry["passed"] or passed
    entry["last"] = sql
    entry["t"] = now


def mark_solution_seen(state: State, lab_id: str) -> None:
    _lab_entry(state, lab_id)["solution_seen"] = True


def record_history(state: State, sql: str, result: dict, now: float) -> None:
    """Remember a SQL lab run; re-running the same SQL moves it to the top."""
    if not sql.strip():
        return
    history = [h for h in state.setdefault("history", []) if h["sql"] != sql]
    entries = result.get("results", [])
    history.append({"t": now, "sql": sql, "statements": len(entries),
                    "errors": sum(1 for e in entries if e.get("type") == "error") if result.get("ok") else None})
    state["history"] = history[-HISTORY_LIMIT:]


def record_settings(state: State, data: dict) -> None:
    settings = state.setdefault("settings", {})
    if "exam_date" in data:
        if data["exam_date"]:
            datetime.date.fromisoformat(data["exam_date"])  # raises ValueError if invalid
        settings["exam_date"] = data["exam_date"] or None
    if "daily_minutes" in data:
        minutes = int(data["daily_minutes"])
        low, high = DAILY_MINUTES_RANGE
        if not low <= minutes <= high:
            raise ValueError(Msg.of("daily_minutes must be between {low} and {high}", low=low, high=high))
        settings["daily_minutes"] = minutes
    if "new_cards_per_day" in data:
        count = int(data["new_cards_per_day"])
        low, high = engine.NEW_CARDS_RANGE
        if not low <= count <= high:
            raise ValueError(Msg.of("new_cards_per_day must be between {low} and {high}", low=low, high=high))
        settings["new_cards_per_day"] = count
    if "exam" in data:
        if data["exam"] not in exams.EXAMS:
            raise ValueError(Msg.of("exam must be one of {exams}", exams=", ".join(exams.EXAMS)))
        settings["exam"] = data["exam"]
    if "language" in data:
        if data["language"] not in LANGUAGES:
            raise ValueError(Msg.of("language must be one of {languages}", languages=", ".join(LANGUAGES)))
        settings["language"] = data["language"]


def reset_progress(state: State) -> None:
    """Forget answers, reviews, exercises and mock exams; keep the settings and the SQL history."""
    kept = {"settings": state.get("settings", {}), "history": state.get("history", [])}
    state.clear()
    state.update({"attempts": {}, "cards": {}, "labs": {}, "mocks": [], **kept})
