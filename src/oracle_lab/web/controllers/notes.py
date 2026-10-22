from __future__ import annotations

from pathlib import Path

from oracle_lab import content
from oracle_lab.access.limits import note_allowed
from oracle_lab.services import NEEDS_SUBSCRIPTION, AccessDenied, Clock
from oracle_lab.services.context import UserContexts
from oracle_lab.study.notes import PERSONAL, NotesLibrary
from oracle_lab.study.tracks import exam_code
from oracle_lab.web.http import HttpError, Request, Response
from oracle_lab.web.routing import Router


class NotesController:
    """The built-in notes and the signed-in user's personal ones."""

    def __init__(self, contexts: UserContexts, builtin_dir: Path, clock: Clock):
        self.contexts = contexts
        self.builtin_dir = builtin_dir
        self.clock = clock

    def allowed(self, request: Request, path: str) -> bool:
        """Personal notes are always the user's; built-in ones follow the workspace level (free: the first lessons)."""
        ctx = self.contexts(request)
        if path.startswith(f"{PERSONAL}/") or ctx.access.limits is None:
            return True
        return note_allowed(path, ctx.level, ctx.access.limits.free_topics)

    def listing(self, request: Request) -> list[dict]:
        return [{**n, "locked": not self.allowed(request, n["path"])}
                for n in self.notes(request).list(self.globs(request), request.language)]

    def notes(self, request: Request) -> NotesLibrary:
        return NotesLibrary(self.builtin_dir, self.contexts(request).notes)

    def globs(self, request: Request) -> tuple[str, ...]:
        """The built-in notes of the signed-in user's current exam: its pack's."""
        return content.pack_of(exam_code(self.contexts(request).state.load())).notes

    def register(self, router: Router) -> None:
        router.get("/api/notes", lambda r: Response.json(self.listing(r)))
        router.get("/api/note", self.read)
        router.post("/api/notes/save", self.save)

    def read(self, request: Request) -> Response:
        path = request.query("path")
        if path and not self.allowed(request, path):
            raise AccessDenied(NEEDS_SUBSCRIPTION)
        text = self.notes(request).read(path, self.globs(request), request.language)
        if text is None:
            raise HttpError(404, "Not found")
        return Response.json({"path": path, "text": text})

    def save(self, request: Request) -> Response:
        notes = self.notes(request)
        data = request.json()
        sql = str(data.get("sql", ""))
        if not sql.strip():
            raise HttpError(400, "Nothing to save")
        return Response.json({"path": notes.save(str(data.get("title", "")), sql, self.clock())})
