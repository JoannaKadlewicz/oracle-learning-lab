"""The web application: a router wrapped in middleware. Callable as request -> response."""

from __future__ import annotations

from collections.abc import Iterable
from functools import partial

from oracle_lab.web.http import Request, Response
from oracle_lab.web.middleware import Middleware
from oracle_lab.web.routing import Handler, Router


class WebApplication:
    def __init__(self, router: Router, middleware: Iterable[Middleware] = ()):
        self.router = router
        handler: Handler = router
        for layer in reversed(list(middleware)):  # the first middleware is the outermost
            handler = partial(layer, call_next=handler)
        self._handle = handler

    def __call__(self, request: Request) -> Response:
        return self._handle(request)
