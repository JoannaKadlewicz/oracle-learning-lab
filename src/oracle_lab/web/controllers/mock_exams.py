from __future__ import annotations

from oracle_lab.services import NEEDS_SUBSCRIPTION, AccessDenied, Clock
from oracle_lab.services.context import UserContexts
from oracle_lab.services.mock_exams import MockExamService
from oracle_lab.web.controllers import respond
from oracle_lab.web.http import Request
from oracle_lab.web.routing import Router

ACTIONS = {"start": MockExamService.start, "answer": MockExamService.answer,
           "submit": MockExamService.submit, "abandon": MockExamService.abandon}


class MockExamController:
    """The signed-in user's mock exams."""

    def __init__(self, contexts: UserContexts, clock: Clock):
        self.contexts = contexts
        self.clock = clock

    def mocks(self, request: Request, starting: bool = False) -> MockExamService:
        """The user's mock exams; starting one needs a subscription (a running one can still be finished)."""
        context = self.contexts(request)
        if starting and context.level != "subscribed":
            raise AccessDenied(NEEDS_SUBSCRIPTION)
        return MockExamService(context.state, self.clock, context.sql_available, request.language)

    def register(self, router: Router) -> None:
        router.get("/api/mock", lambda r: respond(lambda: self.mocks(r).get(r.query("id"))))
        for action, handle in ACTIONS.items():
            router.post(f"/api/mock/{action}", lambda r, handle=handle, start=action == "start":
                        respond(lambda: handle(self.mocks(r, start), r.json())))
