"""Server-side page routes: the sign-in pages and the admin SPA route."""

from __future__ import annotations

from pathlib import Path

from oracle_lab.web.http import HTML_TYPE, Request, Response
from oracle_lab.web.routing import Router

AUTH_PAGES = {"/login": "login.html", "/register": "register.html", "/reset": "reset.html"}


class Pages:
    def __init__(self, static_dir: Path):
        self.static_dir = static_dir
        self.index = static_dir / "index.html"

    def register(self, router: Router) -> None:
        for path, name in AUTH_PAGES.items():
            router.get(path, lambda _, name=name: self.page(name))
        router.get("/admin", self.admin)

    def page(self, name: str) -> Response:
        return Response(200, (self.static_dir / name).read_bytes(), HTML_TYPE, {"Cache-Control": "no-store"})

    def admin(self, _: Request) -> Response:
        """The single-page app; the admin view checks the role (and the admin API enforces it)."""
        return Response(200, self.index.read_bytes(), HTML_TYPE, {"Cache-Control": "no-store"})
