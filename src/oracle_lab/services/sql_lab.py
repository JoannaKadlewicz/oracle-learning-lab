"""The SQL lab and graded exercises. Both run on the database of the current exam track."""

from __future__ import annotations

from typing import Any

from oracle_lab import content
from oracle_lab.analysis import visualizer
from oracle_lab.database.connection import Database, DatabaseCatalog, session
from oracle_lab.database.executor import ScriptRunner
from oracle_lab.database.query import query_rows
from oracle_lab.database.sample_schema import SampleSchema
from oracle_lab.database.schema import describe_schema
from oracle_lab.grading import labs
from oracle_lab.services import Clock, NotFoundError
from oracle_lab.study import recording
from oracle_lab.study.state import StateStore
from oracle_lab.study.tracks import exam_code

LABS_BY_ID = {lab["id"]: lab for lab in content.LABS}


class _TrackDatabase:
    """Resolves the database of the exam track chosen in the settings, at the time of each request."""

    def __init__(self, store: StateStore, catalog: DatabaseCatalog, clock: Clock):
        self.store = store
        self.catalog = catalog
        self.clock = clock

    def current_database(self) -> Database:
        return self.catalog.for_exam(exam_code(self.store.load()))


class SqlLabService(_TrackDatabase):
    def run(self, sql: str, keep: bool) -> dict[str, Any]:
        result = ScriptRunner(self.current_database()).run(sql, keep_changes=keep, inspect=True)
        with self.store.transaction() as state:
            recording.record_history(state, sql, result, self.clock())
        return {**result, "history": state["history"]}

    def visualize(self, sql: str) -> dict[str, Any]:
        with session(self.current_database()) as conn:
            return visualizer.visualize(conn, sql, query_rows)

    def schema(self) -> dict[str, Any]:
        return describe_schema(self.current_database())

    def reset_sample_data(self) -> dict[str, Any]:
        return SampleSchema(self.current_database()).reset()


class ExerciseService(_TrackDatabase):
    def grade(self, lab_id: str | None, sql: str) -> dict[str, Any]:
        lab = LABS_BY_ID.get(lab_id)
        if lab is None:
            raise NotFoundError("Unknown exercise")
        result = labs.grade(self.current_database(), lab, sql)
        with self.store.transaction() as state:
            recording.record_lab_result(state, lab["id"], sql, result["passed"], self.clock())
        return result
