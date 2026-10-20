"""The single-page front end: files under the static directory, index.html for app routes."""

from __future__ import annotations

import base64
import hashlib
import re
from pathlib import Path

from oracle_lab.web.http import HttpError, Request, Response, is_clean_path

CONTENT_TYPES = {".html": "text/html", ".css": "text/css", ".js": "text/javascript", ".svg": "image/svg+xml"}

INLINE_SCRIPT = re.compile(r"<script(?![^>]*\bsrc\b)[^>]*>(.*?)</script>", re.DOTALL | re.IGNORECASE)


def inline_script_hashes(html: str) -> tuple[str, ...]:
    """CSP source entries (sha256-base64) for each inline <script> in a page."""
    return tuple("sha256-" + base64.b64encode(hashlib.sha256(body.encode()).digest()).decode()
                 for body in INLINE_SCRIPT.findall(html))


class StaticFiles:
    def __init__(self, root: Path, index: str = "index.html"):
        self.root = root.resolve()
        self.index = self.root / index

    def __call__(self, request: Request) -> Response:
        path = request.path
        if not is_clean_path(path):  # defence in depth: Authenticate refuses these first
            raise HttpError(404, "Not found")
        target = (self.root / path.lstrip("/")).resolve()
        if path in ("", "/"):
            target = self.index
        elif self.root not in target.parents or not target.is_file():
            if Path(path).suffix:  # a missing asset is a 404, not the app shell
                raise HttpError(404, "Not found")
            target = self.index  # a client-side route such as /quiz
        content_type = CONTENT_TYPES.get(target.suffix, "application/octet-stream") + "; charset=utf-8"
        cache = "no-store" if target.suffix == ".html" else "no-cache"  # pages may carry per-session state
        return Response(200, target.read_bytes(), content_type, {"Cache-Control": cache})
