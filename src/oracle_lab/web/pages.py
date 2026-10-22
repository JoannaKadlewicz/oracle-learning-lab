"""Server-side page routes: the sign-in pages and the admin SPA route."""

from __future__ import annotations

from pathlib import Path

from oracle_lab.web.http import HTML_TYPE, HttpError, Request, Response
from oracle_lab.web.routing import Router
from oracle_lab.web.static import branded

AUTH_PAGES = {"/login": "login.html", "/register": "register.html", "/reset": "reset.html"}


class Pages:
    def __init__(self, static_dir: Path, app_name: str = "Stepwise"):
        self.static_dir = static_dir
        self.app_name = app_name
        self.index = static_dir / "index.html"

    def register(self, router: Router) -> None:
        for path, name in AUTH_PAGES.items():
            router.get(path, lambda _, name=name: self.page(name))
        router.get("/admin", self.admin)

    def page(self, name: str) -> Response:
        return Response(200, branded((self.static_dir / name).read_bytes(), self.app_name), HTML_TYPE,
                        {"Cache-Control": "no-store"})

    def admin(self, request: Request) -> Response:
        """The single-page app, for admins only: anyone else gets 404, like the admin API (which enforces it)."""
        if request.principal is None or request.principal.role != "admin":
            raise HttpError(404, "Not found")
        return Response(200, branded(self.index.read_bytes(), self.app_name), HTML_TYPE, {"Cache-Control": "no-store"})
