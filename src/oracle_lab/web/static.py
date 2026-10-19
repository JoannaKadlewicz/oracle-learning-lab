"""The single-page front end: files under the static directory, index.html for app routes."""

from __future__ import annotations

from pathlib import Path

from oracle_lab.web.http import HttpError, Request, Response

CONTENT_TYPES = {".html": "text/html", ".css": "text/css", ".js": "text/javascript", ".svg": "image/svg+xml"}


class StaticFiles:
    def __init__(self, root: Path, index: str = "index.html"):
        self.root = root.resolve()
        self.index = self.root / index

    def __call__(self, request: Request) -> Response:
        path = request.path
        target = (self.root / path.lstrip("/")).resolve()
        if path in ("", "/"):
            target = self.index
        elif self.root not in target.parents or not target.is_file():
            if Path(path).suffix:  # a missing asset is a 404, not the app shell
                raise HttpError(404, "Not found")
            target = self.index  # a client-side route such as /quiz
        content_type = CONTENT_TYPES.get(target.suffix, "application/octet-stream") + "; charset=utf-8"
        return Response(200, target.read_bytes(), content_type, {"Cache-Control": "no-cache"})
