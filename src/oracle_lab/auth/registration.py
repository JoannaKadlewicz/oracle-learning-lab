"""Sign-up policy (open/closed, user cap) and password registration."""

from __future__ import annotations

import re
import threading
from collections.abc import Callable

from oracle_lab.accounts.repositories import AppStores, SettingsRepository, UserRepository
from oracle_lab.auth.audit import AuditLog
from oracle_lab.auth.models import AuthError, EmailTaken, Identity, LoginResult, RegistrationClosed, User, WeakPassword
from oracle_lab.auth.passwords import PasswordPolicy, hash_password
from oracle_lab.auth.sessions import SessionManager
from oracle_lab.auth.throttle import Throttle
from oracle_lab.auth.tokens import new_id, normalise_email
from oracle_lab.services import Clock

_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
_MAX_EMAIL = 254


class RegistrationPolicy:
    def __init__(self, settings_repo: SettingsRepository, users: UserRepository, default_open: bool, default_max: int):
        self._settings = settings_repo
        self._users = users
        self._default_open = default_open
        self._default_max = default_max

    def is_open(self) -> bool:
        value = self._settings.get("registration_open")
        return self._default_open if value is None else value == "1"

    def max_users(self) -> int:
        value = self._settings.get("max_users")
        try:
            return self._default_max if value is None else int(value)
        except ValueError:
            return self._default_max

    def set(self, open: bool | None = None, max_users: int | None = None) -> None:  # noqa: A002
        if open is not None:
            self._settings.set("registration_open", "1" if open else "0")
        if max_users is not None:
            self._settings.set("max_users", str(max_users))

    def check(self) -> None:
        if not self.is_open() or self._users.count() >= self.max_users():
            raise RegistrationClosed("Registration is closed.")


class Registration:
    def __init__(self, stores: AppStores, policy: PasswordPolicy, registration: RegistrationPolicy,
                 sessions: SessionManager, throttle: Throttle, audit: AuditLog, clock: Clock,
                 on_user_created: Callable[[User], None] = lambda user: None,
                 first_user_is_admin: bool = False):
        self._users = stores.users
        self._policy = policy
        self._registration = registration
        self._sessions = sessions
        self._throttle = throttle
        self._audit = audit
        self._clock = clock
        self._on_user_created = on_user_created
        self._first_user_is_admin = first_user_is_admin
        # The app is one process: this lock makes "cap check + first-admin decision + users.add" atomic,
        # so concurrent sign-ups can neither exceed max_users nor create two first admins.
        self._lock = threading.Lock()

    def with_password(self, email: str, password: str, ip: str, user_agent: str) -> LoginResult:
        email = normalise_email(email)
        self._throttle.check_register(ip)
        self._registration.check()  # early, cheap; repeated under the lock
        if len(email) > _MAX_EMAIL or not _EMAIL.fullmatch(email):
            raise AuthError("Enter a valid email address.")
        problems = self._policy.problems(password, email)
        if problems:
            raise WeakPassword("Choose a stronger password.", problems)
        encoded = hash_password(password)  # slow: outside the lock
        try:
            user = self.create_user(email, email.split("@")[0], lambda uid: Identity("password", uid, uid, encoded))
        except EmailTaken:
            # Probing taken emails costs a scrypt each, so it counts toward the per-IP limit.
            self._throttle.registered(ip)
            self._audit.record("register", "fail", ip=ip, user_agent=user_agent, reason="email_taken")
            raise
        self._throttle.registered(ip)
        token, _ = self._sessions.start(user.id, ip, user_agent)
        self._audit.record("register", "ok", user_id=user.id, ip=ip, user_agent=user_agent, role=user.role)
        return LoginResult(token, user)

    def create_user(self, email: str, display_name: str, identity: Callable[[str], Identity],
                    admin: bool = False) -> User:
        """Creates an account under the registration lock (shared by password and Google sign-up): cap check,
        first-admin decision and insert are atomic. `identity` maps the new user id to its first Identity.
        Raises RegistrationClosed or EmailTaken; calls on_user_created after the lock is released."""
        with self._lock:
            self._registration.check()
            first = self._first_user_is_admin and self._users.count() == 0
            now = self._clock()
            uid = new_id()
            ident = identity(uid)
            user = User(id=uid, email=email, display_name=display_name,
                        role="admin" if admin or first else "learner", status="active", created_at=now,
                        last_login_at=None, password_changed_at=now if ident.provider == "password" else None)
            self._users.add(user, ident)
        self._on_user_created(user)
        return user
