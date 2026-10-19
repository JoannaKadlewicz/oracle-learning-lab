"""Framework-free request and response types. The rest of the web package never touches sockets."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, urlsplit

JSON_TYPE = "application/json; charset=utf-8"
HTML_TYPE = "text/html; charset=utf-8"


class HttpError(Exception):
    """Stops request handling with an error status; the body is {"error": message}."""

    def __init__(self, status: int, message: str, headers: Mapping[str, str] | None = None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.headers = dict(headers or {})

    def to_response(self) -> Response:
        return Response.json({"error": self.message}, self.status, headers=self.headers)


@dataclass(frozen=True)
class Request:
    method: str
    target: str  # path and query string, as sent
    headers: Mapping[str, str]  # keys in lower case
    body: bytes = b""

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
            raise HttpError(400, f"Invalid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise HttpError(400, "Expected a JSON object")
        return data


@dataclass
class Response:
    status: int = 200
    body: bytes = b""
    content_type: str = JSON_TYPE
    headers: dict[str, str] = field(default_factory=dict)

    @classmethod
    def json(cls, payload: Any, status: int = 200, headers: Mapping[str, str] | None = None) -> Response:
        return cls(status, json.dumps(payload).encode(), JSON_TYPE, {"Cache-Control": "no-store", **(headers or {})})

    @classmethod
    def html(cls, text: str, status: int = 200) -> Response:
        return cls(status, text.encode(), HTML_TYPE, {"Cache-Control": "no-store"})
