"""Brute-force and abuse limits for login, sign-up and Google sign-in."""

import hashlib
import math

from oracle_lab.accounts.repositories import ThrottleRepository
from oracle_lab.auth.models import Throttled
from oracle_lab.auth.tokens import normalise_email
from oracle_lab.services import Clock

MESSAGE = "Too many attempts. Try again in a few minutes."  # never reveals whether the account exists
WINDOW = 900.0
ACCOUNT_FREE_FAILURES = 5
IP_FAILURES = 30
REGISTER_PER_IP = 3
REGISTER_WINDOW = 3600.0
GOOGLE_PER_IP = 30


class Throttle:
    def __init__(self, repo: ThrottleRepository, clock: Clock):
        self._repo = repo
        self._clock = clock

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
                raise Throttled(MESSAGE, retry_after=math.ceil(wait - (now - last)))
        if self._repo.count_since(f"login:ip:{ip}", now - WINDOW) >= IP_FAILURES:
            # The repository cannot give the oldest failure, so use the whole window (conservative).
            raise Throttled(MESSAGE, retry_after=int(WINDOW))

    def login_failed(self, email: str, ip: str) -> None:
        now = self._clock()
        self._repo.record(self._acct_key(email), now)
        self._repo.record(f"login:ip:{ip}", now)

    def login_succeeded(self, email: str) -> None:
        """Clears the account's failures only; the IP's failures stay."""
        self._repo.clear(self._acct_key(email))

    def check_register(self, ip: str) -> None:
        if self._repo.count_since(f"register:ip:{ip}", self._clock() - REGISTER_WINDOW) >= REGISTER_PER_IP:
            # Conservative: the oldest registration is not known, so assume the whole window.
            raise Throttled(MESSAGE, retry_after=int(REGISTER_WINDOW))

    def registered(self, ip: str) -> None:
        self._repo.record(f"register:ip:{ip}", self._clock())

    def check_google(self, ip: str) -> None:
        """Checks, then records the attempt: every call counts toward the 30 per 15 minutes."""
        now = self._clock()
        key = f"google:ip:{ip}"
        if self._repo.count_since(key, now - WINDOW) >= GOOGLE_PER_IP:
            raise Throttled(MESSAGE, retry_after=int(WINDOW))
        self._repo.record(key, now)
