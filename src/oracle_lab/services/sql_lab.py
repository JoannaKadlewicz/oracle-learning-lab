"""The SQL lab and graded exercises. Both run on the user's practice database of the current exam track,
one statement at a time per user (RunGuard)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from oracle_lab import content
from oracle_lab.analysis import visualizer
from oracle_lab.database.connection import Database, session
from oracle_lab.database.executor import ScriptRunner
from oracle_lab.database.query import query_rows
from oracle_lab.database.sample_schema import SampleSchema
from oracle_lab.database.schema import describe_schema
from oracle_lab.grading import labs
from oracle_lab.services import Clock, NotFoundError
from oracle_lab.study import recording
from oracle_lab.study.state import StateStore
from oracle_lab.study.tracks import exam_code

if TYPE_CHECKING:
    from oracle_lab.provisioning.guards import RunGuard
    from oracle_lab.provisioning.practice import PracticeDatabases

LABS_BY_ID = {lab["id"]: lab for lab in content.LABS}
CARDS_BY_ID = {card["id"]: card for card in content.FLASHCARDS}


class _TrackDatabase:
    """Resolves the user's database for the exam track chosen in the settings, at the time of each request.
    for_exam raises PracticeUnavailable; guard.run raises HttpError 409/503."""

    def __init__(self, store: StateStore, practice: PracticeDatabases, guard: RunGuard, clock: Clock):
        self.store = store
        self.practice = practice
        self.guard = guard
        self.clock = clock

    def current_database(self) -> Database:
        return self.practice.for_exam(exam_code(self.store.load()))

    def guarded(self):
        return self.guard.run(self.practice.principal.user_id)


class SqlLabService(_TrackDatabase):
    def run(self, sql: str, keep: bool, card_id: str | None = None) -> dict[str, Any]:
        """Run a script. From a flashcard with DDL in its sample, the card's cleanup runs before
        and after, so the sample can be run again and leaves none of its LAB_ objects behind."""
        database = self.current_database()
        card = CARDS_BY_ID.get(card_id, {})
        with self.guarded():
            if card.get("cleanup"):
                with session(database) as conn:
                    labs.run_cleanup(conn, card)
            result = ScriptRunner(database).run(sql, keep_changes=keep, inspect=True)
            if card.get("cleanup"):
                with session(database) as conn:
                    labs.run_cleanup(conn, card)
        with self.store.transaction() as state:
            recording.record_history(state, sql, result, self.clock())
        return {**result, "history": state["history"]}

    def visualize(self, sql: str) -> dict[str, Any]:
        database = self.current_database()
        with self.guarded(), session(database) as conn:
            return visualizer.visualize(conn, sql, query_rows)

    def schema(self) -> dict[str, Any]:
        database = self.current_database()
        with self.guarded():
            return describe_schema(database)

    def reset_sample_data(self) -> dict[str, Any]:
        """Drops and recreates the sample tables in the user's own schema."""
        database = self.current_database()
        with self.guarded():
            return SampleSchema(database).reset()


class ExerciseService(_TrackDatabase):
    def grade(self, lab_id: str | None, sql: str) -> dict[str, Any]:
        lab = LABS_BY_ID.get(lab_id)
        if lab is None:
            raise NotFoundError("Unknown exercise")
        database = self.current_database()
        with self.guarded():
            result = labs.grade(database, lab, sql)
        with self.store.transaction() as state:
            recording.record_lab_result(state, lab["id"], sql, result["passed"], self.clock())
        return result
