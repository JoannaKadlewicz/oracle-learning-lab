"""Password changes, resets, session management and the profile of the signed-in user."""

from __future__ import annotations

from oracle_lab.accounts.repositories import AppStores
from oracle_lab.auth.audit import AuditLog
from oracle_lab.auth.models import AuthError, Identity, InvalidCredentials, LoginResult, Principal, ReauthRequired, WeakPassword
from oracle_lab.auth.passwords import PasswordPolicy, hash_password, verify_password
from oracle_lab.auth.sessions import SessionManager
from oracle_lab.auth.throttle import Throttle
from oracle_lab.auth.tokens import token_hash
from oracle_lab.services import Clock


class AccountSettings:
    def __init__(self, stores: AppStores, policy: PasswordPolicy, sessions: SessionManager, audit: AuditLog,
                 clock: Clock, throttle: Throttle):
        self._users = stores.users
        self._sessions_repo = stores.sessions
        self._resets = stores.resets
        self._policy = policy
        self._sessions = sessions
        self._audit = audit
        self._clock = clock
        self._throttle = throttle

    def _check_new(self, password: str, email: str) -> None:
        problems = self._policy.problems(password, email)
        if problems:
            raise WeakPassword("Choose a stronger password.", problems)

    def _rotate(self, principal: Principal, event: str) -> LoginResult:
        """Ends every session of the user and starts a fresh one (the old token must stop working)."""
        user = self._users.get(principal.user_id)
        if user is None:
            raise AuthError("This account no longer exists.")
        ip, ua = "", ""
        current = self._sessions_repo.get(principal.session_hash)
        if current is not None:
            ip, ua = current.ip, current.user_agent
        self._sessions.end_all(user.id)
        token, _ = self._sessions.start(user.id, ip, ua)
        self._audit.record(event, "ok", user_id=user.id, ip=ip, user_agent=ua)
        return LoginResult(token, user)

    def change_password(self, principal: Principal, current: str, new: str, token: str,
                        ip: str = "") -> LoginResult:
        """`token` is the caller's session token; the new session replaces it. `ip` keys the guess throttle."""
        self._throttle.check_login(principal.email, ip)
        identity = self._password_identity(principal.user_id)
        if identity is None or not identity.password_hash or not verify_password(current, identity.password_hash):
            self._throttle.login_failed(principal.email, ip)
            self._audit.record("password_changed", "fail", user_id=principal.user_id, ip=ip, reason="bad_current")
            raise InvalidCredentials("Your current password is incorrect.")
        self._throttle.login_succeeded(principal.email)
        self._check_new(new, principal.email)
        self._users.set_password(principal.user_id, hash_password(new), self._clock())
        return self._rotate(principal, "password_changed")

    def set_password(self, principal: Principal, new: str, token: str) -> LoginResult:
        if self._password_identity(principal.user_id) is not None:
            raise AuthError("This account already has a password.")
        if principal.reauth_until <= self._clock():
            raise ReauthRequired("Confirm with Google first.")
        self._check_new(new, principal.email)
        hashed = hash_password(new)
        self._users.add_identity(Identity("password", principal.user_id, principal.user_id, hashed))
        self._users.set_password(principal.user_id, hashed, self._clock())
        return self._rotate(principal, "password_set")

    def confirm_deletion(self, principal: Principal, password: str, ip: str = "", user_agent: str = "") -> None:
        """Deleting needs the password (accounts that have one) or a recent Google confirmation."""
        identity = self._password_identity(principal.user_id)
        if identity is None:
            if principal.reauth_until <= self._clock():
                raise ReauthRequired("Confirm with Google first.")
            return
        self._throttle.check_login(principal.email, ip)
        if not identity.password_hash or not verify_password(password, identity.password_hash):
            self._throttle.login_failed(principal.email, ip)
            self._audit.record("account_deleted", "fail", user_id=principal.user_id, ip=ip, user_agent=user_agent,
                               reason="bad_password")
            raise InvalidCredentials("Your password is incorrect.")
        self._throttle.login_succeeded(principal.email)

    def reset_with_token(self, reset_token: str, new_password: str, ip: str, ua: str) -> None:
        # Email-independent rules first, so a weak password does not burn the single-use link.
        self._check_new(new_password, "")
        tok = self._resets.take(token_hash(reset_token), self._clock())
        if tok is None:
            self._audit.record("password_reset", "fail", ip=ip, user_agent=ua, reason="invalid_token")
            raise AuthError("This reset link is invalid or has expired.")
        user = self._users.get(tok.user_id)
        if user is None:
            self._audit.record("password_reset", "fail", ip=ip, user_agent=ua, reason="user_missing")
            raise AuthError("This reset link is invalid or has expired.")
        self._check_new(new_password, user.email)
        hashed = hash_password(new_password)
        if self._password_identity(user.id) is None:
            self._users.add_identity(Identity("password", user.id, user.id, hashed))
        self._users.set_password(user.id, hashed, self._clock())
        self._sessions.end_all(user.id)
        self._audit.record("password_reset", "ok", user_id=user.id, ip=ip, user_agent=ua)

    def sessions(self, principal: Principal) -> list[dict]:
        return [{"id": r.token_hash, "created": r.created_at, "last_seen": r.last_seen_at, "ip": r.ip,
                 "user_agent": r.user_agent, "current": r.token_hash == principal.session_hash}
                for r in self._sessions_repo.for_user(principal.user_id)]

    def end_session(self, principal: Principal, session_id: str) -> None:
        rec = self._sessions_repo.get(session_id)
        if rec is not None and rec.user_id == principal.user_id:
            self._sessions_repo.delete(session_id)
            self._audit.record("session_ended", "ok", user_id=principal.user_id)

    def end_other_sessions(self, principal: Principal) -> None:
        self._sessions_repo.delete_for_user(principal.user_id, principal.session_hash)
        self._audit.record("other_sessions_ended", "ok", user_id=principal.user_id)

    def unlink_google(self, principal: Principal) -> None:
        """Refused without a password: the account would have no way to sign in."""
        if self._password_identity(principal.user_id) is None:
            raise AuthError("Set a password before disconnecting Google.")
        self._users.remove_identity(principal.user_id, "google")
        self._audit.record("google_unlinked", "ok", user_id=principal.user_id)

    def profile(self, principal: Principal) -> dict:
        user = self._users.get(principal.user_id)
        if user is None:
            raise AuthError("This account no longer exists.")
        methods = sorted(i.provider for i in self._users.identities(user.id))
        return {"id": user.id, "email": user.email, "display_name": user.display_name, "role": user.role, "methods": methods}

    def _password_identity(self, user_id: str) -> Identity | None:
        return next((i for i in self._users.identities(user_id) if i.provider == "password"), None)
