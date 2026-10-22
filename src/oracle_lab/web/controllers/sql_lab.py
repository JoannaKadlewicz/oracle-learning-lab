from __future__ import annotations

import logging

from oracle_lab.access.limits import CHECKS_PER_EXERCISE, count_solved, count_use, used_today
from oracle_lab.database.query import format_error
from oracle_lab.i18n import Msg, message_of
from oracle_lab.provisioning.guards import RunGuard
from oracle_lab.provisioning.practice import PracticeUnavailable
from oracle_lab.services import NEEDS_ACCOUNT, NEEDS_PRO, AccessDenied, Clock, LimitReached, NotFoundError
from oracle_lab.services.context import UserContext, UserContexts
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

    def exercises(self, request: Request) -> tuple[ExerciseService, UserContext]:
        """Graded exercises are for accounts (guests get 403)."""
        ctx = self.contexts(request)
        if not ctx.access.can("exercises"):
            raise AccessDenied(NEEDS_ACCOUNT)
        return ExerciseService(ctx.state, ctx.practice, self.guard, self.clock), ctx

    def _check_allowance(self, ctx: UserContext) -> None:
        """Before the SQL runs: the plan's daily exercises (solved ones) and its cap on checked answers."""
        allowed = ctx.access.limits.exercises
        if allowed is None:
            return
        with ctx.state.transaction() as state:
            used = used_today(state, self.clock())
            if used["exercises"] >= allowed:
                raise LimitReached(Msg.of(LIMIT_MESSAGES["exercises"], n=allowed), "exercises", allowed)
            if used["checks"] >= allowed * CHECKS_PER_EXERCISE:
                checks = allowed * CHECKS_PER_EXERCISE
                raise LimitReached(Msg.of(LIMIT_MESSAGES["checks"], n=checks), "checks", checks)

    def _count(self, ctx: UserContext, lab_id: str, passed: bool) -> None:
        """After a run: one checked answer, and the exercise once a day when it passed (an outage, a busy guard or
        SQL that did not run costs nothing). Kept by a progress reset."""
        if ctx.access.limits.exercises is None:
            return
        with ctx.state.transaction() as state:
            count_use(state, "checks", self.clock())
            if passed:
                count_solved(state, lab_id, self.clock())

    def register(self, router: Router) -> None:
        router.post("/api/grade", self.grade)

    def grade(self, request: Request) -> Response:
        data = request.json()
        lab_id = data.get("id")
        if not isinstance(lab_id, str) or lab_id not in recording.LAB_IDS:
            raise HttpError(404, "Unknown exercise")
        exercises, ctx = self.exercises(request)
        self._check_allowance(ctx)
        try:
            result = exercises.grade(lab_id, str(data.get("sql", "")), request.language)
        except NotFoundError as exc:
            raise HttpError(404, message_of(exc)) from exc
        except _NOT_SHOWN_IN_PAGE:
            raise
        except Exception as exc:  # noqa: BLE001
            return _database_failure(exc, passed=False)
        if not result.get("error"):
            self._count(ctx, lab_id, bool(result.get("passed")))
        return Response.json(result)
