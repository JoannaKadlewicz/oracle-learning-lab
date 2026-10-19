from __future__ import annotations

from oracle_lab.web.http import Response
from oracle_lab.web.routing import Router


class HealthController:
    """Liveness for Docker and hosting platforms; needs no login and no database."""

    def register(self, router: Router) -> None:
        router.get("/healthz", lambda _: Response.json({"ok": True}))
