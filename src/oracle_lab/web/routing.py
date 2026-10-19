"""Exact-path routing. Controllers register their routes; the router knows nothing about them."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from oracle_lab.web.http import HttpError, Request, Response

Handler = Callable[[Request], Response]


class Router:
    def __init__(self, fallback: Handler | None = None):
        self._routes: dict[tuple[str, str], Handler] = {}
        self.fallback = fallback  # GET requests no route matches (the static front end)

    def add(self, method: str, path: str, handler: Handler) -> None:
        key = (method.upper(), path)
        if key in self._routes:
            raise ValueError(f"route already registered: {method} {path}")
        self._routes[key] = handler

    def get(self, path: str, handler: Handler) -> None:
        self.add("GET", path, handler)

    def post(self, path: str, handler: Handler) -> None:
        self.add("POST", path, handler)

    def __call__(self, request: Request) -> Response:
        handler = self._routes.get((request.method, request.path))
        if handler is None and request.method == "GET" and self.fallback is not None:
            handler = self.fallback
        if handler is None:
            raise HttpError(404, "Not found")
        return handler(request)


class Controller(Protocol):
    def register(self, router: Router) -> None: ...
