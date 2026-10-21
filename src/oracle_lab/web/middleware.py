"""Cross-cutting request handling, applied around the router in the order given to the application."""

from __future__ import annotations

import hmac
import logging
import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import PurePosixPath
from urllib.parse import quote, urlsplit

from oracle_lab.accounts.repositories import UserRepository
from oracle_lab.auth.models import AuthError, Principal, Throttled, WeakPassword
from oracle_lab.auth.sessions import SessionManager
from oracle_lab.provisioning.practice import PracticeUnavailable
from oracle_lab.web.cookies import CookiePolicy
from oracle_lab.web.http import HttpError, Request, Response, is_clean_path
from oracle_lab.web.routing import Handler

Middleware = Callable[[Request, Handler], Response]

log = logging.getLogger("oracle_lab.access")


def error_boundary(request: Request, call_next: Handler) -> Response:
    """Turn HttpError, AuthError and PracticeUnavailable into their responses and unexpected exceptions into a
    logged 500."""
    try:
        return call_next(request)
    except HttpError as exc:
        return exc.to_response()
    except AuthError as exc:
        return auth_error_response(exc)
    except PracticeUnavailable as exc:
        return Response.json({"error": str(exc), "practice": "unavailable"}, 503)
    except Exception:
        logging.getLogger(__name__).exception("unhandled error in %s %s", request.method, request.path)
        return Response.json({"error": "Internal server error"}, 500)


def auth_error_response(exc: AuthError) -> Response:
    """Its status and {"error": message}, plus the problems of a WeakPassword and Retry-After for Throttled."""
    payload: dict = {"error": str(exc)}
    if isinstance(exc, WeakPassword):
        payload["problems"] = exc.problems
    headers = {"Retry-After": str(exc.retry_after)} if isinstance(exc, Throttled) else {}
    return Response.json(payload, exc.status, headers)


def access_log(request: Request, call_next: Handler) -> Response:
    started = time.perf_counter()
    response = call_next(request)
    log.info("%s %s %d %.0fms", request.method, request.path, response.status,
             (time.perf_counter() - started) * 1000)
    return response


PUBLIC_PATHS = frozenset({
    "/login", "/register", "/reset", "/healthz",
    "/api/auth/login", "/api/auth/register", "/api/auth/reset", "/api/auth/config",
    "/auth/google/start", "/auth/google/callback", "/js/core/dom.js",
})
PUBLIC_PREFIXES = ("/css/", "/js/auth/")  # directories only; with PUBLIC_PATHS, all that the auth pages load
_LOGGED_OUT_ONLY = ("/login", "/register")


def safe_next(value: str) -> str:
    """`value` when it is a path on this site without control characters, else "/" (no open redirect)."""
    if (not isinstance(value, str) or not value.startswith("/") or value.startswith(("//", "/\\"))
            or any(ord(c) < 0x20 or 0x7F <= ord(c) < 0xA0 for c in value)):
        return "/"
    return value


class Authenticate:
    """Sets request.principal from the session cookie; private paths without one get a 401 (API) or the login page."""

    def __init__(self, sessions: SessionManager, users: UserRepository, cookies: CookiePolicy,
                 public_paths: frozenset[str] = PUBLIC_PATHS, public_prefixes: tuple[str, ...] = PUBLIC_PREFIXES):
        self.sessions = sessions
        self.users = users
        self.cookies = cookies
        self.public_paths = public_paths
        self.public_prefixes = public_prefixes

    def __call__(self, request: Request, call_next: Handler) -> Response:
        path = request.path
        if not is_clean_path(path):  # "/css/../js/main.js" must not pass as "/css/"
            raise HttpError(404, "Not found")
        principal = self._principal(request)
        if principal is not None:
            if request.method == "GET" and path in _LOGGED_OUT_ONLY:
                return Response.redirect("/")
            return call_next(replace(request, principal=principal))
        if path in self.public_paths or path.startswith(self.public_prefixes):
            return call_next(request)
        if request.method == "GET" and not path.startswith("/api/") and not PurePosixPath(path).suffix:
            return Response.redirect("/login?next=" + quote(safe_next(request.target), safe=""))
        raise HttpError(401, "Login required")

    def _principal(self, request: Request) -> Principal | None:
        token = self.cookies.read(request, self.cookies.session_name)
        record = self.sessions.resolve(token) if token else None
        if token is None or record is None:
            return None
        user = self.users.get(record.user_id)
        if user is None or user.status != "active":
            self.sessions.end(token)  # a locked or deleted account is signed out everywhere it is used
            return None
        return Principal(user.id, user.email, user.role, record.token_hash, record.csrf_token, record.reauth_until)


# Public auth POSTs run without a session; a signed-in browser (an old cookie) must still reach them.
# They are protected by same_origin_only instead of a token.
CSRF_EXEMPT = frozenset({"/api/auth/login", "/api/auth/register", "/api/auth/reset"})


def csrf(request: Request, call_next: Handler) -> Response:
    """A signed-in request that changes something must echo the session's CSRF token in X-CSRF-Token."""
    principal = request.principal
    if principal is not None and request.method != "GET" and request.path not in CSRF_EXEMPT:
        given = request.header("X-CSRF-Token").encode()
        if not hmac.compare_digest(given, principal.csrf_token.encode()):
            raise HttpError(403, "Invalid CSRF token")
    return call_next(request)


def same_origin_only(request: Request, call_next: Handler) -> Response:
    """Refuse cross-origin POSTs, so another web page cannot make the browser run SQL here."""
    origin, fetch_site = request.header("Origin"), request.header("Sec-Fetch-Site")
    if request.method == "POST" and ((origin and urlsplit(origin).netloc != request.header("Host"))
                                     or (fetch_site and fetch_site != "same-origin")):
        raise HttpError(403, "Cross-origin requests are not allowed.")
    return call_next(request)


class ClientAddress:
    """Use the right-most X-Forwarded-For entry (the one our own proxy appended) as the client, if trusted."""

    def __init__(self, trust_proxy: bool):
        self.trust_proxy = trust_proxy

    def __call__(self, request: Request, call_next: Handler) -> Response:
        forwarded = request.header("X-Forwarded-For").rsplit(",", 1)[-1].strip()
        if self.trust_proxy and forwarded:
            request = replace(request, client=forwarded)
        return call_next(request)


CSP_TEMPLATE = (
    "default-src 'self'; script-src 'self' https://cdnjs.cloudflare.com{hashes}; "
    "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://fonts.googleapis.com; "
    "font-src https://fonts.gstatic.com; "
    "img-src 'self' data:; connect-src 'self'; form-action 'self' https://accounts.google.com; "
    "frame-ancestors 'none'; base-uri 'none'; object-src 'none'"
)
PERMISSIONS_POLICY = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"


class SecurityHeaders:
    """Add the browser hardening headers to every response; HSTS only when the site is served over https."""

    def __init__(self, hsts: bool, inline_script_hashes: tuple[str, ...]):
        hashes = "".join(f" '{h}'" for h in inline_script_hashes)
        self.headers = {
            "Content-Security-Policy": CSP_TEMPLATE.format(hashes=hashes),
            "Referrer-Policy": "same-origin",
            "Cross-Origin-Opener-Policy": "same-origin",
            "Permissions-Policy": PERMISSIONS_POLICY,
            "X-Frame-Options": "DENY",
        }
        if hsts:
            self.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    def __call__(self, request: Request, call_next: Handler) -> Response:
        response = call_next(request)
        response.headers.update(self.headers)
        return response
