"""Quiz answers, flashcards, settings and progress on the chosen exam track."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from oracle_lab import content
from oracle_lab.engines import engine_for_exam
from oracle_lab.services import Clock, NotFoundError
from oracle_lab.study import engine, recording
from oracle_lab.study.mocks import finalize_expired
from oracle_lab.study.progress import snapshot
from oracle_lab.study.state import State, StateStore
from oracle_lab.study.tracks import track, track_state

DEFAULT_PICK = 10


@dataclass(frozen=True)
class ReportContext:
    """Everything the printable readiness report is rendered from."""

    content: SimpleNamespace
    state: State
    progress: dict[str, Any]
    now: float


class StudyService:
    def __init__(self, store: StateStore, clock: Clock, track_databases: bool = False,
                 sql_available: bool = True):
        self.store = store
        self.clock = clock
        self.track_databases = track_databases
        self.sql_available = sql_available

    def track_content(self) -> dict[str, Any]:
        """The study material of the current exam track, for the front end."""
        view = track(self.store.load())
        db = engine_for_exam(view.CODE)
        return {
            "topics": view.TOPICS,
            "sections": view.SECTIONS,
            "objectives": view.OBJECTIVES,
            "exam": view.EXAM,
            "exams": content.EXAMS,
            "engine": {"name": db.name, "label": db.label, "editor_mode": db.editor_mode},
            "home_notes": list(view.HOME_NOTES),
            "dual_database": self.track_databases,
            "questions": view.QUESTIONS,
            "flashcards": view.FLASHCARDS,
            "labs": view.LABS,
        }

    def state(self) -> State:
        return self.store.load()

    def progress(self) -> dict[str, Any]:
        with self.store.transaction() as state:
            finalize_expired(state, self.clock())
        return snapshot(state, self.clock(), self.sql_available)

    def record_attempt(self, data: dict) -> dict[str, Any]:
        if data.get("id") not in recording.QUESTIONS_BY_ID:
            raise NotFoundError("Unknown question")
        return self._change(lambda state: recording.record_attempt(state, data, self.clock()))

    def record_card(self, data: dict) -> dict[str, Any]:
        return self._change(lambda state: recording.record_card(state, data, self.clock()))

    def mark_solution_seen(self, lab_id: str | None) -> dict[str, Any]:
        if lab_id not in recording.LAB_IDS:
            raise NotFoundError("Unknown exercise")
        return self._change(lambda state: recording.mark_solution_seen(state, lab_id))

    def update_settings(self, data: dict) -> dict[str, Any]:
        return self._change(lambda state: recording.record_settings(state, data))

    def reset_progress(self) -> dict[str, Any]:
        return self._change(recording.reset_progress)

    def pick_questions(self, topics: list[str] | None, count: Any = DEFAULT_PICK) -> list[str]:
        state = self.store.load()
        view = track(state)
        count = max(1, min(int(count), len(view.QUESTIONS)))
        return engine.pick_questions(view, track_state(state), self.clock(), count, topics or None)

    def report_context(self) -> ReportContext:
        state = self.store.load()
        view, seen, now = track(state), track_state(state), self.clock()
        return ReportContext(view, seen, engine.progress(view, seen, now, self.sql_available), now)

    def _change(self, mutate) -> dict[str, Any]:
        with self.store.transaction() as state:
            mutate(state)
        return snapshot(state, self.clock(), self.sql_available)
