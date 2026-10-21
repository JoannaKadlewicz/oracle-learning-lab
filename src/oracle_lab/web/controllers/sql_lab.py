from __future__ import annotations

import logging

from oracle_lab.database.query import format_error
from oracle_lab.provisioning.guards import RunGuard
from oracle_lab.provisioning.practice import PracticeUnavailable
from oracle_lab.services import Clock, NotFoundError
from oracle_lab.services.context import UserContexts
from oracle_lab.services.sql_lab import ExerciseService, SqlLabService
from oracle_lab.web.http import HttpError, Request, Response
from oracle_lab.web.routing import Router

log = logging.getLogger(__name__)

# Not database problems: an unavailable practice database (503) and the run guard's 409/503 go to error_boundary.
_NOT_SHOWN_IN_PAGE = (PracticeUnavailable, HttpError)


def _database_failure(exc: Exception, **payload) -> Response:
    """Database problems are shown in the page (status 200), the way the front end expects them."""
    log.warning("database call failed: %s", exc)
    return Response.json({**payload, "error": format_error(exc)})


class SqlLabController:
    """Run scripts, visualize joins and set operators, browse the schema, reset the sample data.
    The history, lab results and practice schema are the signed-in user's."""

    def __init__(self, contexts: UserContexts, guard: RunGuard, clock: Clock):
        self.contexts = contexts
        self.guard = guard
        self.clock = clock

    def lab(self, request: Request) -> SqlLabService:
        ctx = self.contexts(request)
        return SqlLabService(ctx.state, ctx.practice, self.guard, self.clock)

    def register(self, router: Router) -> None:
        router.post("/api/run", self.run)
        router.post("/api/visualize", self.visualize)
        router.get("/api/schema", self.schema)
        router.post("/api/reset-data", lambda r: Response.json(self.lab(r).reset_sample_data()))

    def run(self, request: Request) -> Response:
        lab, data = self.lab(request), request.json()
        return Response.json(lab.run(str(data.get("sql", "")), keep=bool(data.get("keep")), card_id=data.get("card")))

    def visualize(self, request: Request) -> Response:
        lab = self.lab(request)
        try:
            return Response.json(lab.visualize(str(request.json().get("sql", ""))))
        except _NOT_SHOWN_IN_PAGE:
            raise
        except Exception as exc:  # noqa: BLE001
            return _database_failure(exc)

    def schema(self, request: Request) -> Response:
        lab = self.lab(request)
        try:
            return Response.json(lab.schema())
        except _NOT_SHOWN_IN_PAGE:
            raise
        except Exception as exc:  # noqa: BLE001
            return _database_failure(exc, ok=False)


class ExerciseController:
    def __init__(self, contexts: UserContexts, guard: RunGuard, clock: Clock):
        self.contexts = contexts
        self.guard = guard
        self.clock = clock

    def exercises(self, request: Request) -> ExerciseService:
        ctx = self.contexts(request)
        return ExerciseService(ctx.state, ctx.practice, self.guard, self.clock)

    def register(self, router: Router) -> None:
        router.post("/api/grade", self.grade)

    def grade(self, request: Request) -> Response:
        exercises, data = self.exercises(request), request.json()
        try:
            result = exercises.grade(data.get("id"), str(data.get("sql", "")))
        except NotFoundError as exc:
            raise HttpError(404, str(exc)) from exc
        except _NOT_SHOWN_IN_PAGE:
            raise
        except Exception as exc:  # noqa: BLE001
            return _database_failure(exc, passed=False)
        return Response.json(result)
