"""Quiz answers, flashcards, settings and progress on the chosen exam track."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from oracle_lab import content, exams
from oracle_lab.access.limits import count_use, used_today
from oracle_lab.engines import engine_for_exam
from oracle_lab.i18n import Msg
from oracle_lab.services import NEEDS_PRO, AccessDenied, Clock, LimitReached, NotFoundError
from oracle_lab.services.context import UNRESTRICTED, Access
from oracle_lab.study import engine, recording
from oracle_lab.study.mocks import finalize_expired
from oracle_lab.study.progress import localized, snapshot
from oracle_lab.study.state import State, StateStore
from oracle_lab.study.tracks import track, track_state

DEFAULT_PICK = 10
LIMIT_MESSAGES = {
    "questions": "You have used today's {n} questions. Come back tomorrow.",
    "cards": "You have used today's {n} flashcards. Come back tomorrow.",
    "exercises": "You have used today's {n} exercises. Come back tomorrow.",
}


@dataclass(frozen=True)
class ReportContext:
    """Everything the printable readiness report is rendered from."""

    content: SimpleNamespace
    state: State
    progress: dict[str, Any]
    now: float


class StudyService:
    def __init__(self, store: StateStore, clock: Clock, track_databases: bool = False,
                 sql_available: bool = True, lang: str = "en", access: Access = UNRESTRICTED):
        self.store = store
        self.access = access
        self.clock = clock
        self.track_databases = track_databases
        self.sql_available = sql_available
        self.lang = lang

    def track_content(self, lang: str = "en") -> dict[str, Any]:
        """The study material of the current exam track in `lang`, for the front end."""
        view = track(self.store.load(), lang)
        db = engine_for_exam(view.CODE)
        return {
            "topics": view.TOPICS,
            "sections": view.SECTIONS,
            "objectives": view.OBJECTIVES,
            "exam": view.EXAM,
            "exams": {code: content.public_exam(exam, lang) for code, exam in exams.EXAMS.items()},
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
        return self._snapshot(state)

    def record_attempt(self, data: dict) -> dict[str, Any]:
        if data.get("id") not in recording.QUESTIONS_BY_ID:
            raise NotFoundError("Unknown question")
        return self._change(lambda state: (self._within("questions", state),
                                           recording.record_attempt(state, data, self.clock())))

    def record_card(self, data: dict) -> dict[str, Any]:
        return self._change(lambda state: (self._within("cards", state), recording.record_card(state, data, self.clock())))

    def mark_solution_seen(self, lab_id: str | None) -> dict[str, Any]:
        if lab_id not in recording.LAB_IDS:
            raise NotFoundError("Unknown exercise")
        return self._change(lambda state: recording.mark_solution_seen(state, lab_id))

    def update_settings(self, data: dict) -> dict[str, Any]:
        if self.access.workspace is not None and "exam" in data and data["exam"] not in self.access.usable:
            raise AccessDenied(NEEDS_PRO)  # more than one workspace is the Pro plan
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
        view, seen, now = track(state, self.lang), track_state(state), self.clock()
        return ReportContext(view, seen, localized(engine.progress(view, seen, now, self.sql_available), self.lang), now)

    def _change(self, mutate) -> dict[str, Any]:
        with self.store.transaction() as state:
            mutate(state)
        return self._snapshot(state)

    def _within(self, kind: str, state: State) -> None:
        """LimitReached when the plan's daily allowance of `kind` is used up (checked inside the transaction)."""
        allowed = getattr(self.access.limits, kind)
        if allowed is None:
            return
        if used_today(state, self.clock())[kind] >= allowed:
            raise LimitReached(Msg.of(LIMIT_MESSAGES[kind], n=allowed), kind)
        count_use(state, kind, self.clock())

    def _snapshot(self, state: State) -> dict[str, Any]:
        limits = self.access.limits
        caps = {k: v for k, v in (("questions", limits.questions), ("cards", limits.cards)) if v is not None} or None
        result = snapshot(state, self.clock(), self.sql_available, self.lang, caps)
        result["access"] = self.access.public(state, self.clock())
        return result
