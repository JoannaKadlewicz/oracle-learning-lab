"""Cross-cutting request handling, applied around the router in the order given to the application."""

from __future__ import annotations

import base64
import binascii
import hmac
import logging
import time
from collections.abc import Callable
from urllib.parse import urlsplit

from oracle_lab.config import BasicAuthConfig
from oracle_lab.web.http import HttpError, Request, Response
from oracle_lab.web.routing import Handler

Middleware = Callable[[Request, Handler], Response]

log = logging.getLogger("oracle_lab.access")


def error_boundary(request: Request, call_next: Handler) -> Response:
    """Turn HttpError into its response and unexpected exceptions into a logged 500."""
    try:
        return call_next(request)
    except HttpError as exc:
        return exc.to_response()
    except Exception:
        logging.getLogger(__name__).exception("unhandled error in %s %s", request.method, request.path)
        return Response.json({"error": "Internal server error"}, 500)


def access_log(request: Request, call_next: Handler) -> Response:
    started = time.perf_counter()
    response = call_next(request)
    log.info("%s %s %d %.0fms", request.method, request.path, response.status,
             (time.perf_counter() - started) * 1000)
    return response


class BasicAuth:
    """HTTP basic auth on every path except the public ones (the health check)."""

    def __init__(self, config: BasicAuthConfig, public_paths: frozenset[str] = frozenset({"/healthz"}),
                 realm: str = "Oracle Learning Lab"):
        self.expected = f"{config.user}:{config.password}".encode()
        self.public_paths = public_paths
        self.challenge = {"WWW-Authenticate": f'Basic realm="{realm}", charset="UTF-8"'}

    def __call__(self, request: Request, call_next: Handler) -> Response:
        if request.path in self.public_paths or self._authorized(request.header("Authorization")):
            return call_next(request)
        raise HttpError(401, "Login required", self.challenge)

    def _authorized(self, header: str) -> bool:
        scheme, _, encoded = header.partition(" ")
        if scheme.lower() != "basic":
            return False
        try:
            given = base64.b64decode(encoded.strip(), validate=True)
        except (binascii.Error, ValueError):
            return False
        return hmac.compare_digest(given, self.expected)


def same_origin_only(request: Request, call_next: Handler) -> Response:
    """Refuse cross-origin POSTs, so another web page cannot make the browser run SQL here."""
    origin = request.header("Origin")
    if request.method == "POST" and origin and urlsplit(origin).netloc != request.header("Host"):
        raise HttpError(403, "Cross-origin requests are not allowed.")
    return call_next(request)
