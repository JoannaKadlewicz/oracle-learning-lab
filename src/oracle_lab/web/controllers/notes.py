from __future__ import annotations

from oracle_lab.services import Clock
from oracle_lab.study.notes import NotesLibrary
from oracle_lab.web.http import HttpError, Request, Response
from oracle_lab.web.routing import Router


class NotesController:
    def __init__(self, notes: NotesLibrary, clock: Clock):
        self.notes = notes
        self.clock = clock

    def register(self, router: Router) -> None:
        router.get("/api/notes", lambda _: Response.json(self.notes.list()))
        router.get("/api/note", self.read)
        router.post("/api/notes/save", self.save)

    def read(self, request: Request) -> Response:
        path = request.query("path")
        text = self.notes.read(path)
        if text is None:
            raise HttpError(404, "Not found")
        return Response.json({"path": path, "text": text})

    def save(self, request: Request) -> Response:
        data = request.json()
        sql = str(data.get("sql", ""))
        if not sql.strip():
            raise HttpError(400, "Nothing to save")
        return Response.json({"path": self.notes.save(str(data.get("title", "")), sql, self.clock())})
