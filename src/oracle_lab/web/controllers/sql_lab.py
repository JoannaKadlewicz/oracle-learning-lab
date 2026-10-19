from __future__ import annotations

import logging

from oracle_lab.database.query import format_error
from oracle_lab.services import NotFoundError
from oracle_lab.services.sql_lab import ExerciseService, SqlLabService
from oracle_lab.web.http import HttpError, Request, Response
from oracle_lab.web.routing import Router

log = logging.getLogger(__name__)


def _database_failure(exc: Exception, **payload) -> Response:
    """Database problems are shown in the page (status 200), the way the front end expects them."""
    log.warning("database call failed: %s", exc)
    return Response.json({**payload, "error": format_error(exc)})


class SqlLabController:
    """Run scripts, visualize joins and set operators, browse the schema, reset the sample data."""

    def __init__(self, lab: SqlLabService):
        self.lab = lab

    def register(self, router: Router) -> None:
        router.post("/api/run", self.run)
        router.post("/api/visualize", self.visualize)
        router.get("/api/schema", self.schema)
        router.post("/api/reset-data", lambda _: Response.json(self.lab.reset_sample_data()))

    def run(self, request: Request) -> Response:
        data = request.json()
        return Response.json(self.lab.run(str(data.get("sql", "")), keep=bool(data.get("keep"))))

    def visualize(self, request: Request) -> Response:
        try:
            return Response.json(self.lab.visualize(str(request.json().get("sql", ""))))
        except Exception as exc:  # noqa: BLE001
            return _database_failure(exc)

    def schema(self, _: Request) -> Response:
        try:
            return Response.json(self.lab.schema())
        except Exception as exc:  # noqa: BLE001
            return _database_failure(exc, ok=False)


class ExerciseController:
    def __init__(self, exercises: ExerciseService):
        self.exercises = exercises

    def register(self, router: Router) -> None:
        router.post("/api/grade", self.grade)

    def grade(self, request: Request) -> Response:
        data = request.json()
        try:
            result = self.exercises.grade(data.get("id"), str(data.get("sql", "")))
        except NotFoundError as exc:
            raise HttpError(404, str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            return _database_failure(exc, passed=False)
        return Response.json(result)
