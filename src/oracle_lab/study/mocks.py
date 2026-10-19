"""Timed mock exams: start, answer, submit (or abandon), and auto-submit after the deadline."""

from __future__ import annotations

from types import SimpleNamespace

from oracle_lab.study import engine
from oracle_lab.study.recording import QUESTIONS_BY_ID, record_attempt, valid_choices, valid_confidence
from oracle_lab.study.state import State
from oracle_lab.study.tracks import track, track_state

MAX_MINUTES = 300


def find_mock(state: State, mock_id: str | None) -> dict:
    mock = next((m for m in state.setdefault("mocks", []) if m["id"] == mock_id), None)
    if mock is None:
        raise ValueError("unknown mock exam")
    return mock


def is_running(mock: dict) -> bool:
    return not mock["submitted"] and not mock["abandoned"]


def is_over(mock: dict, now: float) -> bool:
    return now > engine.mock_deadline(mock) + engine.MOCK_GRACE


def start_mock(state: State, data: dict, now: float) -> dict:
    """Abandon any running mock and start a new one on the current exam track."""
    for mock in state.setdefault("mocks", []):
        if is_running(mock):
            mock["abandoned"] = now
    view = track(state)
    topics = [t for t in data.get("topics") or [] if t in view.TOPICS] or None
    count = int(data.get("count") or view.EXAM["questions"])
    minutes = int(data.get("minutes") or view.EXAM["minutes"])
    if not (1 <= count <= len(view.QUESTIONS) and 1 <= minutes <= MAX_MINUTES):
        raise ValueError("count or minutes out of range")
    track_ids = {q["id"] for q in view.QUESTIONS}
    ids = {i for i in data.get("ids") or [] if i in track_ids}
    if ids:  # a timed drill on chosen questions (for example only "Which error?" questions)
        pool = SimpleNamespace(**{**vars(view), "QUESTIONS": [q for q in view.QUESTIONS if q["id"] in ids]})
        mock = engine.build_mock(pool, track_state(state), now, len(ids), minutes, None)
        mock["topics"] = sorted({q["topic"] for q in pool.QUESTIONS})
    else:
        mock = engine.build_mock(view, track_state(state), now, count, minutes, topics)
    mock["exam"] = view.CODE
    state["mocks"].append(mock)
    return mock


def record_time_on(mock: dict, time_on: dict | None) -> None:
    """Seconds spent per question, as measured by the browser; unknown questions are ignored."""
    if time_on:
        mock["time_on"] = {qid: float(v) for qid, v in time_on.items() if qid in mock["items"]}


def answer_mock(state: State, data: dict, now: float) -> None:
    mock = find_mock(state, data.get("mock_id"))
    if not is_running(mock) or is_over(mock, now):
        raise ValueError("this mock exam is over")
    record_time_on(mock, data.get("time_on"))
    qid = data.get("id")
    if qid is None:
        return
    if qid not in mock["items"]:
        raise ValueError("question is not part of this mock exam")
    answer = mock["answers"].setdefault(qid, {"chosen": [], "confidence": None, "flagged": False})
    if "chosen" in data:
        answer["chosen"] = valid_choices(QUESTIONS_BY_ID[qid], data["chosen"])
        mock["events"].append([now, qid, answer["chosen"]])
    if "confidence" in data:
        answer["confidence"] = valid_confidence(data["confidence"])
    if "flagged" in data:
        answer["flagged"] = bool(data["flagged"])


def submit_mock(state: State, mock: dict, now: float) -> None:
    """Close a mock. Answered questions become exam-mode attempts. Unanswered ones score zero in the
    mock report but are not recorded as answers, so they stay fresh evidence for readiness."""
    mock["submitted"] = min(now, engine.mock_deadline(mock))
    for qid in mock["items"]:
        answer = mock["answers"].get(qid, {})
        if qid in QUESTIONS_BY_ID and answer.get("chosen"):
            record_attempt(state, {"id": qid, "chosen": answer.get("chosen", []),
                                   "confidence": answer.get("confidence"), "mode": "exam"}, mock["submitted"])


def submit_mock_by_id(state: State, data: dict, now: float) -> dict:
    mock = find_mock(state, data.get("mock_id"))
    if mock["abandoned"]:
        raise ValueError("this mock exam was abandoned")
    record_time_on(mock, data.get("time_on"))
    if not mock["submitted"]:
        submit_mock(state, mock, now)
    return mock


def abandon_mock(state: State, mock_id: str | None, now: float) -> None:
    mock = find_mock(state, mock_id)
    if not mock["submitted"]:
        mock["abandoned"] = now


def finalize_expired(state: State, now: float) -> None:
    """Submit mocks whose time ran out while the app was closed."""
    for mock in state.get("mocks", []):
        if is_running(mock) and is_over(mock, now):
            submit_mock(state, mock, now)
