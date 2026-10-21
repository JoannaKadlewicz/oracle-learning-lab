from __future__ import annotations

from oracle_lab.services import Clock
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

    def mocks(self, request: Request) -> MockExamService:
        context = self.contexts(request)
        return MockExamService(context.state, self.clock, context.sql_available)

    def register(self, router: Router) -> None:
        router.get("/api/mock", lambda r: respond(lambda: self.mocks(r).get(r.query("id"))))
        for action, handle in ACTIONS.items():
            router.post(f"/api/mock/{action}", lambda r, handle=handle: respond(lambda: handle(self.mocks(r), r.json())))
