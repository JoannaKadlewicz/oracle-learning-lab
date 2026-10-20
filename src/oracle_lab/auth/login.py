"""Password sign-in and sign-out."""

from __future__ import annotations

import dataclasses

from oracle_lab.accounts.repositories import AppStores
from oracle_lab.auth.audit import AuditLog
from oracle_lab.auth.models import InvalidCredentials, LoginResult
from oracle_lab.auth.passwords import DUMMY_HASH, hash_password, needs_rehash, verify_password
from oracle_lab.auth.sessions import SessionManager
from oracle_lab.auth.throttle import Throttle
from oracle_lab.auth.tokens import normalise_email
from oracle_lab.services import Clock


class PasswordLogin:
    def __init__(self, stores: AppStores, sessions: SessionManager, throttle: Throttle, audit: AuditLog,
                 clock: Clock):
        self._users = stores.users
        self._sessions = sessions
        self._throttle = throttle
        self._audit = audit
        self._clock = clock

    def login(self, email: str, password: str, ip: str, user_agent: str) -> LoginResult:
        email = normalise_email(email)
        self._throttle.check_login(email, ip)
        user = self._users.by_email(email)
        identity = None
        if user is not None:
            identity = next((i for i in self._users.identities(user.id) if i.provider == "password"), None)
        stored = identity.password_hash if identity and identity.password_hash else None
        # Exactly one scrypt per attempt, whatever went wrong, so timing does not reveal the reason.
        matches = verify_password(password, stored or DUMMY_HASH)
        reason = None
        if user is None:
            reason = "unknown_email"
        elif stored is None:
            reason = "no_password"
        elif not matches:
            reason = "bad_password"
        elif user.status == "locked":
            reason = "locked"
        if reason is not None or user is None:
            self._throttle.login_failed(email, ip)
            self._audit.record("login", "fail", user_id=user.id if user else None, ip=ip,
                               user_agent=user_agent, reason=reason)
            raise InvalidCredentials("Email or password is incorrect.")
        self._throttle.login_succeeded(email)
        if stored and needs_rehash(stored):
            self._users.set_password(user.id, hash_password(password), self._clock())
        user = dataclasses.replace(user, last_login_at=self._clock())
        self._users.update(user)
        token, _ = self._sessions.start(user.id, ip, user_agent)
        self._audit.record("login", "ok", user_id=user.id, ip=ip, user_agent=user_agent)
        return LoginResult(token, user)

    def logout(self, token: str) -> None:
        rec = self._sessions.resolve(token)
        self._sessions.end(token)
        if rec is not None:
            self._audit.record("logout", "ok", user_id=rec.user_id, ip=rec.ip, user_agent=rec.user_agent)
