"""The signed-in user's workspaces: the overview (also before they have one) and their first pick."""

from __future__ import annotations

from oracle_lab.access.service import WorkspaceService
from oracle_lab.services.context import UserContexts
from oracle_lab.web.controllers import respond
from oracle_lab.web.http import Request, Response
from oracle_lab.web.routing import Router


class WorkspacesController:
    def __init__(self, workspaces: WorkspaceService, contexts: UserContexts):
        self.workspaces = workspaces
        self.contexts = contexts

    def register(self, router: Router) -> None:
        router.get("/api/workspaces", self.overview)
        router.post("/api/workspaces/choose", self.choose)

    def overview(self, request: Request) -> Response:
        ctx = self.contexts(request, require_workspace=False)
        settings = ctx.state.load().get("settings", {})
        overview = self.workspaces.overview(ctx.principal, settings.get("exam"), request.language)
        return Response.json({**overview, "language": settings.get("language")})  # the picker's language

    def choose(self, request: Request) -> Response:
        ctx = self.contexts(request, require_workspace=False)
        return respond(lambda: self.workspaces.choose(ctx.principal, request.json().get("workspace"), ip=request.client,
                                                      user_agent=request.header("User-Agent")) or {"ok": True})
