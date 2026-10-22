"""Sign-up, sign-in, sign-out, password reset and Google sign-in."""

from __future__ import annotations

from collections.abc import Callable
from urllib.parse import quote

from oracle_lab.access.service import workspace_facts
from oracle_lab.auth.account_settings import AccountSettings
from oracle_lab.auth.google import GoogleSignIn
from oracle_lab.auth.guest import GuestAccess
from oracle_lab.auth.login import PasswordLogin
from oracle_lab.auth.models import AuthError, LoginResult, Principal, Throttled
from oracle_lab.auth.registration import Registration, RegistrationPolicy
from oracle_lab.auth.sessions import SessionManager
from oracle_lab.exams import EXAMS
from oracle_lab.i18n import Msg
from oracle_lab.services import NEEDS_ACCOUNT
from oracle_lab.web.cookies import CookiePolicy
from oracle_lab.web.http import HttpError, Request, Response
from oracle_lab.web.middleware import auth_error_response, safe_next
from oracle_lab.web.routing import Router

SESSION_MAX_AGE = 30 * 86400
GOOGLE_LOGIN_ERRORS = {"exists", "closed", "throttled", "failed"}  # GoogleOutcome.code on sign-in
_LOCATION_SAFE = "/?&=#%:@!$'()*+,;~"  # keeps a URL's structure; spaces and non-ASCII get percent-encoded


def login_error(code: str) -> str:
    """The login page naming why Google sign-in failed; the page maps the code to a fixed message."""
    return "/login?error=google_" + (code if code in GOOGLE_LOGIN_ERRORS else "failed")


def with_google_error(location: str, code: str) -> str:
    """`location` with google_error=<code> in its query, before any #fragment."""
    path, hash_, fragment = location.partition("#")
    path += ("&" if "?" in path else "?") + "google_error=" + quote(code, safe="")
    return path + hash_ + fragment


def _quoted(location: str) -> str:
    return quote(location, safe=_LOCATION_SAFE)


def principal_of(request: Request) -> Principal:
    if request.principal is None:  # Authenticate keeps logged-out requests away from private routes
        raise HttpError(401, "Login required")
    return request.principal


def text(data: dict, name: str) -> str:
    value = data.get(name, "")
    if not isinstance(value, str):
        raise HttpError(400, Msg.of("{name} must be a string", name=name))
    return value



class AuthController:
    def __init__(self, login: PasswordLogin, registration: Registration, policy: RegistrationPolicy,
                 account: AccountSettings, sessions: SessionManager, cookies: CookiePolicy,
                 google: GoogleSignIn | None, guests: GuestAccess | None = None,
                 adopt: Callable[[str, str], None] = lambda guest_id, user_id: None,
                 guest_workspace: Callable[[str, str], None] = lambda user_id, workspace: None,
                 drop_guest: Callable[[str], None] = lambda guest_id: None):
        self.guests = guests
        self.guest_workspace = guest_workspace
        self.adopt = adopt  # moves a guest's progress into the account created from its session
        self.drop_guest = drop_guest  # deletes a guest whose session this app ends: nobody could reach it again
        self.login = login
        self.registration = registration
        self.policy = policy
        self.account = account
        self.sessions = sessions
        self.cookies = cookies
        self.google = google

    def register(self, router: Router) -> None:
        router.post("/api/auth/login", self.sign_in)
        router.post("/api/auth/register", self.sign_up)
        router.post("/api/auth/guest", self.guest)
        router.post("/api/auth/logout", self.sign_out)
        router.get("/api/auth/me", self.me)
        router.get("/api/auth/config", self.config)
        router.post("/api/auth/reset", self.reset)
        router.get("/auth/google/start", self.google_start)
        router.get("/auth/google/callback", self.google_callback)

    def sign_in(self, request: Request) -> Response:
        data = request.json()
        result = self.login.login(text(data, "email"), text(data, "password"), request.client,
                                  request.header("User-Agent"))
        return self._signed_in(request, result, data)

    def sign_up(self, request: Request) -> Response:
        data = request.json()
        result = self.registration.with_password(text(data, "email"), text(data, "password"), request.client,
                                                 request.header("User-Agent"))
        self._adopt_guest(request, result.user.id)
        return self._signed_in(request, result, data)

    def guest(self, request: Request) -> Response:
        """"Try it without an account": a guest session (any earlier session cookie of this browser ends)."""
        if self.guests is None:
            raise HttpError(404, "Not found")
        token, record = self.guests.start(request.client, request.header("User-Agent"))
        workspace = request.json().get("workspace")
        if isinstance(workspace, str) and workspace in EXAMS:  # a landing tile: straight into that workspace
            self.guest_workspace(record.user_id, workspace)
        response = Response.json({"ok": True, "next": "/"})
        response.cookies.append(self.new_session_cookie(request, token))
        self._drop_guest_of(request)  # this browser's earlier guest, if any
        return response

    def _drop_guest_of(self, request: Request) -> None:
        """Deletes the guest of the session the request came with (its session has just been ended)."""
        principal = request.principal
        if principal is not None and principal.role == "guest":
            self.drop_guest(principal.user_id)

    def _adopt_guest(self, request: Request, user_id: str) -> None:
        principal = request.principal
        if principal is not None and principal.role == "guest":
            self.adopt(principal.user_id, user_id)

    def _signed_in(self, request: Request, result: LoginResult, data: dict) -> Response:
        response = Response.json({"ok": True, "next": safe_next(text(data, "next") or "/")})
        response.cookies.append(self.new_session_cookie(request, result.token))
        return response

    def new_session_cookie(self, request: Request, token: str) -> str:
        """Ends the session of the cookie the browser sent (no session fixation) and sets the new one."""
        old = self.cookies.read(request, self.cookies.session_name)
        if old is not None:
            self.sessions.end(old)
        return self.cookies.set_session(token, SESSION_MAX_AGE)

    def sign_out(self, request: Request) -> Response:
        token = self.cookies.read(request, self.cookies.session_name)
        if token is not None:
            self.login.logout(token)
            self._drop_guest_of(request)
        response = Response.json({"ok": True})
        response.cookies.append(self.cookies.clear_session())
        return response

    def me(self, request: Request) -> Response:
        principal = principal_of(request)
        return Response.json({"user": self.account.profile(principal), "csrf_token": principal.csrf_token})

    def config(self, request: Request) -> Response:
        exams = [{"code": e.code, "database": e.database_label} for e in EXAMS.values()]
        return Response.json({"google": self.google is not None, "registration_open": self.policy.is_open(),
                              "guests": self.guests is not None and self.guests.allowed(),
                              "exams": exams, "workspaces": workspace_facts(request.language)})

    def reset(self, request: Request) -> Response:
        data = request.json()
        self.account.reset_with_token(text(data, "token"), text(data, "password"), request.client,
                                      request.header("User-Agent"))
        return Response.json({"ok": True})

    def google_start(self, request: Request) -> Response:
        google = self._google()
        intent = request.query("intent", "login")
        if intent not in ("login", "link", "reauth"):
            raise HttpError(400, "Unknown sign-in intent")
        if intent != "login" and request.principal is not None and request.principal.role == "guest":
            raise HttpError(403, NEEDS_ACCOUNT)  # a guest account has no sign-in of its own to link to
        next_path = safe_next(request.query("next", "/"))
        try:
            url, flow_id = google.start(intent, next_path, request.principal, request.client)
        except Throttled:  # a browser navigation: back to a page that can say so
            if intent == "login":
                return Response.redirect(login_error("throttled"))
            return Response.redirect(_quoted(with_google_error(next_path, "throttled")))
        return Response.redirect(url, cookies=[self.cookies.set_flow(flow_id)])

    def google_callback(self, request: Request) -> Response:
        google = self._google()
        try:
            outcome = google.finish(self.cookies.read(request, self.cookies.flow_name) or "", request.query("state"),
                                    request.query("code"), request.client, request.header("User-Agent"),
                                    request.principal)
        except AuthError as exc:  # the flow is single-use: clear its cookie on every way out
            response = auth_error_response(exc, request.language)
            response.cookies.append(self.cookies.clear_flow())
            return response
        cookies = [self.cookies.clear_flow()]
        location = safe_next(outcome.next_path)
        if outcome.code is not None:
            if outcome.intent == "login":
                return Response.redirect(login_error(outcome.code), cookies=cookies)
            location = with_google_error(location, outcome.code)  # a signed-in user stays where they were
        if outcome.created_user_id is not None:
            self._adopt_guest(request, outcome.created_user_id)
        if outcome.token is not None:
            cookies.append(self.new_session_cookie(request, outcome.token))
        return Response.redirect(_quoted(location), cookies=cookies)

    def _google(self) -> GoogleSignIn:
        if self.google is None:
            raise HttpError(404, "Not found")
        return self.google
