from __future__ import annotations

from oracle_lab.services.mock_exams import MockExamService
from oracle_lab.web.controllers import respond
from oracle_lab.web.routing import Router


class MockExamController:
    def __init__(self, mocks: MockExamService):
        self.mocks = mocks

    def register(self, router: Router) -> None:
        router.get("/api/mock", lambda r: respond(lambda: self.mocks.get(r.query("id"))))
        for action, handle in (("start", self.mocks.start), ("answer", self.mocks.answer),
                               ("submit", self.mocks.submit), ("abandon", self.mocks.abandon)):
            router.post(f"/api/mock/{action}", lambda r, handle=handle: respond(lambda: handle(r.json())))
