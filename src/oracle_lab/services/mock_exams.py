"""Timed mock exams."""

from __future__ import annotations

from typing import Any

from oracle_lab import content
from oracle_lab.services import Clock, NotFoundError
from oracle_lab.study import engine, mocks
from oracle_lab.study.progress import snapshot
from oracle_lab.study.state import StateStore
from oracle_lab.study.tracks import mock_exam


def _report(mock: dict) -> dict[str, Any]:
    return engine.mock_report(content.for_exam(mock_exam(mock)), mock)


class MockExamService:
    def __init__(self, store: StateStore, clock: Clock, sql_available: bool = True):
        self.store = store
        self.clock = clock
        self.sql_available = sql_available

    def get(self, mock_id: str) -> dict[str, Any]:
        try:
            mock = mocks.find_mock(self.store.load(), mock_id)
        except ValueError as exc:
            raise NotFoundError(str(exc)) from exc
        return {"mock": {**mock, "position": mock.get("position")}, "report": _report(mock) if mock["submitted"] else None}

    def start(self, data: dict) -> dict[str, Any]:
        with self.store.transaction() as state:
            mock = mocks.start_mock(state, data, self.clock())
        return {**snapshot(state, self.clock(), self.sql_available), "mock": mock}

    def answer(self, data: dict) -> dict[str, Any]:
        with self.store.transaction() as state:
            mocks.answer_mock(state, data, self.clock())
        return {"ok": True}

    def submit(self, data: dict) -> dict[str, Any]:
        with self.store.transaction() as state:
            mock = mocks.submit_mock_by_id(state, data, self.clock())
        return {**snapshot(state, self.clock(), self.sql_available), "report": _report(mock)}

    def abandon(self, data: dict) -> dict[str, Any]:
        with self.store.transaction() as state:
            mocks.abandon_mock(state, data.get("mock_id"), self.clock())
        return snapshot(state, self.clock(), self.sql_available)
