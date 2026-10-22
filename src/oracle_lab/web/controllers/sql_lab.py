from __future__ import annotations

import logging

from oracle_lab.access.limits import count_use, used_today
from oracle_lab.database.query import format_error
from oracle_lab.i18n import Msg, message_of
from oracle_lab.provisioning.guards import RunGuard
from oracle_lab.provisioning.practice import PracticeUnavailable
from oracle_lab.services import NEEDS_ACCOUNT, NEEDS_PRO, AccessDenied, Clock, LimitReached, NotFoundError
from oracle_lab.services.context import UserContexts
from oracle_lab.services.sql_lab import ExerciseService, SqlLabService
from oracle_lab.services.study import LIMIT_MESSAGES
from oracle_lab.study import recording
from oracle_lab.web.http import HttpError, Request, Response
from oracle_lab.web.routing import Router

log = logging.getLogger(__name__)

# Not database problems: an unavailable practice database (503) and the run guard's 409/503 go to error_boundary.
_NOT_SHOWN_IN_PAGE = (PracticeUnavailable, HttpError)


def _sql_context(contexts: UserContexts, request: Request):
    """The user's context; the SQL lab (any SQL outside a graded exercise) is the Pro plan (403 otherwise)."""
    ctx = contexts(request)
    if not ctx.access.can("sql_lab"):
        raise AccessDenied(NEEDS_ACCOUNT if ctx.plan == "guest" else NEEDS_PRO)  # guests first need an account
    return ctx


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
        ctx = _sql_context(self.contexts, request)
        return SqlLabService(ctx.state, ctx.practice, self.guard, self.clock)

    def register(self, router: Router) -> None:
        router.post("/api/run", self.run)
        router.post("/api/visualize", self.visualize)
        router.get("/api/schema", self.schema)
        router.post("/api/reset-data", lambda r: Response.json(self.lab(r).reset_sample_data()))

    def run(self, request: Request) -> Response:
        lab, data = self.lab(request), request.json()
        return Response.json(lab.run(str(data.get("sql", "")), keep=bool(data.get("keep")), card_id=data.get("card"),
                                     lang=request.language))

    def visualize(self, request: Request) -> Response:
        lab = self.lab(request)
        try:
            return Response.json(lab.visualize(str(request.json().get("sql", "")), request.language))
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

    def exercises(self, request: Request, lab_id: object = None) -> ExerciseService:
        """Graded exercises are for accounts; a plan's daily allowance is counted (and kept by a progress reset)
        before the SQL runs, inside the user's state transaction."""
        ctx = self.contexts(request)
        if not ctx.access.can("exercises"):
            raise AccessDenied(NEEDS_ACCOUNT)
        allowed = ctx.access.limits.exercises
        if allowed is not None and lab_id in recording.LAB_IDS:
            with ctx.state.transaction() as state:
                if used_today(state, self.clock())["exercises"] >= allowed:
                    raise LimitReached(Msg.of(LIMIT_MESSAGES["exercises"], n=allowed), "exercises")
                count_use(state, "exercises", self.clock())
        return ExerciseService(ctx.state, ctx.practice, self.guard, self.clock)

    def register(self, router: Router) -> None:
        router.post("/api/grade", self.grade)

    def grade(self, request: Request) -> Response:
        data = request.json()
        exercises = self.exercises(request, data.get("id"))
        try:
            result = exercises.grade(data.get("id"), str(data.get("sql", "")), request.language)
        except NotFoundError as exc:
            raise HttpError(404, message_of(exc)) from exc
        except _NOT_SHOWN_IN_PAGE:
            raise
        except Exception as exc:  # noqa: BLE001
            return _database_failure(exc, passed=False)
        return Response.json(result)
