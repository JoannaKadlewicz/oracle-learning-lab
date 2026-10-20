"""Server-side page routes: the sign-in pages (placeholders until the real ones) and the admin SPA route."""

from __future__ import annotations

from pathlib import Path

from oracle_lab.web.http import HTML_TYPE, Request, Response
from oracle_lab.web.routing import Router

_PLACEHOLDER = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>{title} - Oracle Learning Lab</title>
<link rel="stylesheet" href="/css/app.css"></head>
<body><main><h1>{title}</h1>
<form id="{form}" method="post">{fields}<button type="submit">{title}</button></form>
</main></body></html>
"""
_EMAIL = '<label>Email <input name="email" type="email" autocomplete="username" required></label>'
_PASSWORD = '<label>Password <input name="password" type="password" autocomplete="{ac}" required></label>'
PAGES = {
    "/login": ("Sign in", "login-form", _EMAIL + _PASSWORD.format(ac="current-password")),
    "/register": ("Create account", "register-form", _EMAIL + _PASSWORD.format(ac="new-password")),
    "/reset": ("Reset password", "reset-form", _PASSWORD.format(ac="new-password")),
}


class Pages:
    def __init__(self, static_dir: Path):
        self.index = static_dir / "index.html"

    def register(self, router: Router) -> None:
        for path, (title, form, fields) in PAGES.items():
            html = _PLACEHOLDER.format(title=title, form=form, fields=fields)
            router.get(path, lambda _, html=html: Response.html(html))
        router.get("/admin", self.admin)

    def admin(self, _: Request) -> Response:
        """The single-page app; the admin view checks the role (and the admin API enforces it)."""
        return Response(200, self.index.read_bytes(), HTML_TYPE, {"Cache-Control": "no-store"})
