"""Brute-force and abuse limits for login, sign-up and Google sign-in."""

from __future__ import annotations

import hashlib
import logging
import math

from oracle_lab.accounts.repositories import ThrottleRepository
from oracle_lab.auth.audit import AuditLog
from oracle_lab.auth.models import Throttled
from oracle_lab.auth.tokens import normalise_email
from oracle_lab.services import Clock

log = logging.getLogger(__name__)

MESSAGE = "Too many attempts. Try again in a few minutes."  # never reveals whether the account exists
WINDOW = 900.0
ACCOUNT_FREE_FAILURES = 5
IP_FAILURES = 30
REGISTER_PER_IP = 3
REGISTER_WINDOW = 3600.0
GOOGLE_PER_IP = 30
AUDITS_PER_HOUR = 10  # "throttled" audit records per throttle key an hour; the rest are refused unrecorded
_AUDIT_PREFIX = "audit_throttled:"


class Throttle:
    """`audit` records each refusal as a "throttled" event (at most AUDITS_PER_HOUR per key an hour, so a flood
    cannot flood the audit trail), naming the kind of limit and the IP but never the email."""

    def __init__(self, repo: ThrottleRepository, clock: Clock, audit: AuditLog | None = None):
        self._repo = repo
        self._clock = clock
        self._audit = audit

    def _refuse(self, key: str, kind: str, ip: str, retry_after: int) -> Throttled:
        """The Throttled error to raise, audited first (an audit failure is logged and never stops the refusal)."""
        if self._audit is not None:
            try:
                now = self._clock()
                audit_key = _AUDIT_PREFIX + key
                if self._repo.count_since(audit_key, now - 3600) < AUDITS_PER_HOUR:
                    self._repo.record(audit_key, now)
                    self._audit.record("throttled", "denied", ip=ip, kind=kind)
            except Exception:  # noqa: BLE001
                log.exception("could not audit a throttled %s attempt", kind)
        return Throttled(MESSAGE, retry_after=retry_after)

    @staticmethod
    def _acct_key(email: str) -> str:
        return "login:acct:" + hashlib.sha256(normalise_email(email).encode()).hexdigest()

    def check_login(self, email: str, ip: str) -> None:
        """From the 5th failure on, the account waits min(2 ** (n - 5), 900) s after its last failure;
        an IP with 30 failures in 15 minutes is blocked."""
        now = self._clock()
        key = self._acct_key(email)
        n = self._repo.count_since(key, now - WINDOW)
        last = self._repo.last(key)
        if n >= ACCOUNT_FREE_FAILURES and last is not None:
            wait = min(2 ** (n - ACCOUNT_FREE_FAILURES), WINDOW)
            if now - last < wait:
                # wait > elapsed here, so the ceiling is at least 1
                raise self._refuse(key, "login_account", ip, math.ceil(wait - (now - last)))
        if self._repo.count_since(f"login:ip:{ip}", now - WINDOW) >= IP_FAILURES:
            # The repository cannot give the oldest failure, so use the whole window (conservative).
            raise self._refuse(f"login:ip:{ip}", "login_ip", ip, int(WINDOW))

    def login_failed(self, email: str, ip: str) -> None:
        now = self._clock()
        self._repo.record(self._acct_key(email), now)
        self._repo.record(f"login:ip:{ip}", now)

    def login_succeeded(self, email: str) -> None:
        """Clears the account's failures only; the IP's failures stay."""
        self._repo.clear(self._acct_key(email))

    def check_register(self, ip: str) -> None:
        key = f"register:ip:{ip}"
        if self._repo.count_since(key, self._clock() - REGISTER_WINDOW) >= REGISTER_PER_IP:
            # Conservative: the oldest registration is not known, so assume the whole window.
            raise self._refuse(key, "register", ip, int(REGISTER_WINDOW))

    def registered(self, ip: str) -> None:
        self._repo.record(f"register:ip:{ip}", self._clock())

    def check_google(self, ip: str) -> None:
        """Checks, then records the attempt: every call counts toward the 30 per 15 minutes."""
        now = self._clock()
        key = f"google:ip:{ip}"
        if self._repo.count_since(key, now - WINDOW) >= GOOGLE_PER_IP:
            raise self._refuse(key, "google", ip, int(WINDOW))
        self._repo.record(key, now)
