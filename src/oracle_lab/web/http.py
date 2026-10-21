"""Framework-free request and response types. The rest of the web package never touches sockets."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlsplit

from oracle_lab.i18n import DEFAULT_LANGUAGE, Msg, translate

if TYPE_CHECKING:
    from oracle_lab.auth.models import Principal

JSON_TYPE = "application/json; charset=utf-8"
HTML_TYPE = "text/html; charset=utf-8"


_ENCODED_SEPARATORS = re.compile(r"%(2e|2f|5c)", re.IGNORECASE)


def is_clean_path(path: str) -> bool:
    """False for paths a file lookup could resolve somewhere else: empty, "." or ".." segments (a trailing "/"
    is fine), backslashes, and percent-encoded dots, slashes or backslashes."""
    if not path.startswith("/") or "\\" in path or _ENCODED_SEPARATORS.search(path):
        return False
    segments = path[1:].split("/")
    return not any(seg in ("", ".", "..") for seg in segments[:-1]) and segments[-1] not in (".", "..")


class HttpError(Exception):
    """Stops request handling with an error status; the body is {"error": message}, in the request's language."""

    def __init__(self, status: int, message: str, headers: Mapping[str, str] | None = None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.headers = dict(headers or {})

    def to_response(self, lang: str = DEFAULT_LANGUAGE) -> Response:
        return Response.json({"error": translate(lang, self.message)}, self.status, headers=self.headers)


@dataclass(frozen=True)
class Request:
    method: str
    target: str  # path and query string, as sent
    headers: Mapping[str, str]  # keys in lower case
    body: bytes = b""
    client: str = ""  # the peer IP; ClientAddress may replace it behind a trusted proxy
    principal: Principal | None = None  # the signed-in account, set by the auth middleware
    language: str = DEFAULT_LANGUAGE  # of the messages sent back, set by the language middleware

    @property
    def path(self) -> str:
        return urlsplit(self.target).path

    def query(self, name: str, default: str = "") -> str:
        return parse_qs(urlsplit(self.target).query).get(name, [default])[0]

    def header(self, name: str, default: str = "") -> str:
        return self.headers.get(name.lower(), default)

    def json(self) -> dict[str, Any]:
        """The body as a JSON object; an empty body is {}."""
        try:
            data = json.loads(self.body or b"{}")
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HttpError(400, Msg.of("Invalid JSON: {detail}", detail=exc)) from exc
        if not isinstance(data, dict):
            raise HttpError(400, "Expected a JSON object")
        return data


@dataclass
class Response:
    status: int = 200
    body: bytes = b""
    content_type: str = JSON_TYPE
    headers: dict[str, str] = field(default_factory=dict)
    cookies: list[str] = field(default_factory=list)  # raw Set-Cookie values, one header each

    @classmethod
    def json(cls, payload: Any, status: int = 200, headers: Mapping[str, str] | None = None) -> Response:
        return cls(status, json.dumps(payload).encode(), JSON_TYPE, {"Cache-Control": "no-store", **(headers or {})})

    @classmethod
    def html(cls, text: str, status: int = 200) -> Response:
        return cls(status, text.encode(), HTML_TYPE, {"Cache-Control": "no-store"})

    @classmethod
    def redirect(cls, location: str, status: int = 302, cookies: list[str] | None = None) -> Response:
        return cls(status, b"", HTML_TYPE, {"Location": location, "Cache-Control": "no-store"}, list(cookies or []))
