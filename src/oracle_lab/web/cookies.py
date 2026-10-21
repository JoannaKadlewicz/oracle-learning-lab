"""Session and login-flow cookies; the __Host- prefix is used when served over HTTPS."""

from __future__ import annotations

import re
from http.cookies import CookieError, SimpleCookie

from oracle_lab.web.http import Request

_SAFE = re.compile(r"[A-Za-z0-9_-]*")


class CookiePolicy:
    def __init__(self, secure: bool) -> None:
        self.secure = secure
        prefix = "__Host-" if secure else ""
        self.session_name = f"{prefix}oll_session"
        self.flow_name = f"{prefix}oll_flow"

    def set_session(self, token: str, max_age: float) -> str:
        return self._cookie(self.session_name, token, max_age)

    def clear_session(self) -> str:
        return self._cookie(self.session_name, "", 0)

    def set_flow(self, flow_id: str) -> str:
        return self._cookie(self.flow_name, flow_id, 600)

    def clear_flow(self) -> str:
        return self._cookie(self.flow_name, "", 0)

    def read(self, request: Request, name: str) -> str | None:
        header = request.header("cookie")
        if not header:
            return None
        jar: SimpleCookie = SimpleCookie()
        try:
            jar.load(header)
        except CookieError:
            return None
        morsel = jar.get(name)
        if morsel is None or not morsel.value or not _SAFE.fullmatch(morsel.value):
            return None
        return morsel.value

    def _cookie(self, name: str, value: str, max_age: float) -> str:
        if not _SAFE.fullmatch(value) or max_age < 0:
            raise ValueError("unsafe cookie value or negative max_age")
        parts = [f"{name}={value}", "HttpOnly", "SameSite=Lax", "Path=/", f"Max-Age={int(max_age)}"]
        if self.secure:
            parts.insert(1, "Secure")
        return "; ".join(parts)
