from __future__ import annotations

from oracle_lab.i18n import LANGUAGES
from oracle_lab.services import Clock
from oracle_lab.services.context import UserContexts
from oracle_lab.services.study import StudyService
from oracle_lab.web import report
from oracle_lab.web.controllers import respond
from oracle_lab.web.http import Request, Response
from oracle_lab.web.routing import Router


class StudyController:
    """Content of the exam track, progress, quiz answers, flashcards, settings: all of the signed-in user."""

    def __init__(self, contexts: UserContexts, clock: Clock, track_databases: bool):
        self.contexts = contexts
        self.clock = clock
        self.track_databases = track_databases

    def study(self, request: Request, lang: str | None = None) -> StudyService:
        context = self.contexts(request)
        return StudyService(context.state, self.clock, track_databases=self.track_databases,
                            sql_available=context.sql_available, lang=lang or request.language,
                            access=context.access)

    def register(self, router: Router) -> None:
        router.get("/api/content", lambda r: Response.json(self.study(r).track_content(r.language)))
        router.get("/api/state", lambda r: Response.json(self.study(r).state()))
        router.get("/api/progress", lambda r: Response.json(self.study(r).progress()))
        router.get("/report", self.readiness_report)
        router.post("/api/attempt", lambda r: respond(lambda: self.study(r).record_attempt(r.json())))
        router.post("/api/card", lambda r: respond(lambda: self.study(r).record_card(r.json())))
        router.post("/api/lab-solution", lambda r: respond(lambda: self.study(r).mark_solution_seen(r.json().get("id"))))
        router.post("/api/settings", lambda r: respond(lambda: self.study(r).update_settings(r.json())))
        router.post("/api/pick", self.pick)
        router.post("/api/reset-progress", lambda r: Response.json(self.study(r).reset_progress()))

    def readiness_report(self, request: Request) -> Response:
        # Opened in a new tab, so no X-Language header: the app's link names the language.
        lang = request.query("lang") if request.query("lang") in LANGUAGES else request.language
        ctx = self.study(request, lang).report_context()
        return Response.html(report.render(ctx.content, ctx.state, ctx.progress, ctx.now, lang))

    def pick(self, request: Request) -> Response:
        data = request.json()
        study = self.study(request)
        return respond(lambda: {"ids": study.pick_questions(data.get("topics"), data.get("count", 10))})
