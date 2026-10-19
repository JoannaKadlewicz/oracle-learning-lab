from __future__ import annotations

from oracle_lab.services.study import StudyService
from oracle_lab.web import report
from oracle_lab.web.controllers import respond
from oracle_lab.web.http import Request, Response
from oracle_lab.web.routing import Router


class StudyController:
    """Content of the exam track, progress, quiz answers, flashcards, settings."""

    def __init__(self, study: StudyService):
        self.study = study

    def register(self, router: Router) -> None:
        router.get("/api/content", lambda _: Response.json(self.study.track_content()))
        router.get("/api/state", lambda _: Response.json(self.study.state()))
        router.get("/api/progress", lambda _: Response.json(self.study.progress()))
        router.get("/report", self.readiness_report)
        router.post("/api/attempt", lambda r: respond(lambda: self.study.record_attempt(r.json())))
        router.post("/api/card", lambda r: respond(lambda: self.study.record_card(r.json())))
        router.post("/api/lab-solution", lambda r: respond(lambda: self.study.mark_solution_seen(r.json().get("id"))))
        router.post("/api/settings", lambda r: respond(lambda: self.study.update_settings(r.json())))
        router.post("/api/pick", self.pick)
        router.post("/api/reset-progress", lambda _: Response.json(self.study.reset_progress()))

    def readiness_report(self, _: Request) -> Response:
        ctx = self.study.report_context()
        return Response.html(report.render(ctx.content, ctx.state, ctx.progress, ctx.now))

    def pick(self, request: Request) -> Response:
        data = request.json()
        return respond(lambda: {"ids": self.study.pick_questions(data.get("topics"), data.get("count", 10))})
