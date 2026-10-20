"""Sign-up, sign-in, sign-out, password reset and Google sign-in."""

from __future__ import annotations

from urllib.parse import quote

from oracle_lab.auth.account_settings import AccountSettings
from oracle_lab.auth.google import GoogleSignIn
from oracle_lab.auth.login import PasswordLogin
from oracle_lab.auth.models import AuthError, LoginResult, Principal
from oracle_lab.auth.registration import Registration, RegistrationPolicy
from oracle_lab.auth.sessions import SessionManager
from oracle_lab.web.cookies import CookiePolicy
from oracle_lab.web.http import HttpError, Request, Response
from oracle_lab.web.middleware import auth_error_response, safe_next
from oracle_lab.web.routing import Router

SESSION_MAX_AGE = 30 * 86400
GOOGLE_FAILED = "/login?error=google"
_LOCATION_SAFE = "/?&=#%:@!$'()*+,;~"  # keeps a URL's structure; spaces and non-ASCII get percent-encoded


def principal_of(request: Request) -> Principal:
    if request.principal is None:  # Authenticate keeps logged-out requests away from private routes
        raise HttpError(401, "Login required")
    return request.principal


def text(data: dict, name: str) -> str:
    value = data.get(name, "")
    if not isinstance(value, str):
        raise HttpError(400, f"{name} must be a string")
    return value


class AuthController:
    def __init__(self, login: PasswordLogin, registration: Registration, policy: RegistrationPolicy,
                 account: AccountSettings, sessions: SessionManager, cookies: CookiePolicy,
                 google: GoogleSignIn | None):
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
        return self._signed_in(request, result, data)

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
        response = Response.json({"ok": True})
        response.cookies.append(self.cookies.clear_session())
        return response

    def me(self, request: Request) -> Response:
        principal = principal_of(request)
        return Response.json({"user": self.account.profile(principal), "csrf_token": principal.csrf_token})

    def config(self, _: Request) -> Response:
        return Response.json({"google": self.google is not None, "registration_open": self.policy.is_open()})

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
        url, flow_id = google.start(intent, safe_next(request.query("next", "/")), request.principal, request.client)
        return Response.redirect(url, cookies=[self.cookies.set_flow(flow_id)])

    def google_callback(self, request: Request) -> Response:
        google = self._google()
        try:
            outcome = google.finish(self.cookies.read(request, self.cookies.flow_name) or "", request.query("state"),
                                    request.query("code"), request.client, request.header("User-Agent"),
                                    request.principal)
        except AuthError as exc:  # the flow is single-use: clear its cookie on every way out
            response = auth_error_response(exc)
            response.cookies.append(self.cookies.clear_flow())
            return response
        cookies = [self.cookies.clear_flow()]
        location = safe_next(outcome.next_path)
        if outcome.message is not None:
            if outcome.intent == "login":
                return Response.redirect(GOOGLE_FAILED, cookies=cookies)
            location += ("&" if "?" in location else "?") + "google_error=1"  # a signed-in user stays where they were
        if outcome.token is not None:
            cookies.append(self.new_session_cookie(request, outcome.token))
        return Response.redirect(quote(location, safe=_LOCATION_SAFE), cookies=cookies)

    def _google(self) -> GoogleSignIn:
        if self.google is None:
            raise HttpError(404, "Not found")
        return self.google
