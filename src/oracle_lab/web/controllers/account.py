"""Settings of the signed-in account: password, sessions, Google connection."""

from __future__ import annotations

from oracle_lab.accounts.deletion import AccountDeletion
from oracle_lab.auth.account_settings import AccountSettings
from oracle_lab.auth.models import LoginResult
from oracle_lab.services import NEEDS_ACCOUNT
from oracle_lab.web.controllers.auth import SESSION_MAX_AGE, principal_of, text
from oracle_lab.web.cookies import CookiePolicy
from oracle_lab.web.http import HttpError, Request, Response
from oracle_lab.web.routing import Router

OK = {"ok": True}


class AccountController:
    def __init__(self, account: AccountSettings, cookies: CookiePolicy, deletion: AccountDeletion):
        self.account = account
        self.deletion = deletion
        self.cookies = cookies

    def _account_only(self, handler):
        """Password, sessions, Google and deletion belong to accounts: a guest has nothing to change (403)."""
        def run(request: Request) -> Response:
            if request.principal is not None and request.principal.role == "guest":
                raise HttpError(403, NEEDS_ACCOUNT)
            return handler(request)
        return run

    def register(self, router: Router) -> None:
        router.post("/api/account/password", self._account_only(self.change_password))
        router.post("/api/account/set-password", self._account_only(self.set_password))
        router.get("/api/account/sessions", self.sessions)
        router.post("/api/account/sessions/end", self._account_only(self.end_session))
        router.post("/api/account/sessions/end-others", self._account_only(self.end_other_sessions))
        router.post("/api/account/google/unlink", self._account_only(self.unlink_google))
        router.post("/api/account/delete", self._account_only(self.delete))

    def change_password(self, request: Request) -> Response:
        data = request.json()
        result = self.account.change_password(principal_of(request), text(data, "current"), text(data, "new"),
                                              self._token(request), ip=request.client)
        return self._rotated(result)

    def set_password(self, request: Request) -> Response:
        result = self.account.set_password(principal_of(request), text(request.json(), "new"), self._token(request))
        return self._rotated(result)

    def sessions(self, request: Request) -> Response:
        return Response.json({"sessions": self.account.sessions(principal_of(request))})

    def end_session(self, request: Request) -> Response:
        self.account.end_session(principal_of(request), text(request.json(), "id"))
        return Response.json(OK)

    def end_other_sessions(self, request: Request) -> Response:
        self.account.end_other_sessions(principal_of(request))
        return Response.json(OK)

    def unlink_google(self, request: Request) -> Response:
        self.account.unlink_google(principal_of(request))
        return Response.json(OK)

    def delete(self, request: Request) -> Response:
        principal = principal_of(request)
        self.account.confirm_deletion(principal, text(request.json(), "password"), ip=request.client,
                                      user_agent=request.header("User-Agent"))
        self.deletion.delete(principal.user_id, principal.user_id, ip=request.client,
                             user_agent=request.header("User-Agent"))
        response = Response.json(OK)
        response.cookies.append(self.cookies.clear_session())
        return response

    def _token(self, request: Request) -> str:
        return self.cookies.read(request, self.cookies.session_name) or ""

    def _rotated(self, result: LoginResult) -> Response:
        """Every session of the account was ended; the browser gets the new one."""
        response = Response.json(OK)
        response.cookies.append(self.cookies.set_session(result.token, SESSION_MAX_AGE))
        return response
