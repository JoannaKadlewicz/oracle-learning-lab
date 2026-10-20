"""Security audit trail: every event is stored and written as one log line."""

import logging
import re

from oracle_lab.accounts.repositories import AuditRepository
from oracle_lab.auth.models import AuditEvent
from oracle_lab.services import Clock

_USER_AGENT_LOG_LIMIT = 80
_USER_AGENT_STORE_LIMIT = 200  # same as the session store
_OUTCOMES = ("ok", "fail", "denied")
_KEY = re.compile(r"[a-z][a-z0-9_]{0,40}")
_RESERVED = {"event", "outcome", "user", "ip", "ua"}
_SENSITIVE = ("password", "passwd", "secret", "token", "code", "cookie", "authorization", "csrf")
REDACTED = "[redacted]"


def _clean(value: object) -> str:
    """One log token: no line breaks (log injection), repr-quoted when ambiguous."""
    text = "".join(c if c.isprintable() else (f"\\x{ord(c):02x}" if ord(c) < 256 else f"\\u{ord(c):04x}")
                   for c in str(value))
    if not text or any(c.isspace() or c == "=" for c in text):
        return repr(text)
    return text


class AuditLog:
    def __init__(self, repo: AuditRepository, clock: Clock, logger: logging.Logger | None = None):
        self._repo = repo
        self._clock = clock
        self._logger = logger or logging.getLogger("oracle_lab.audit")

    def record(self, event: str, outcome: str, *, user_id: str | None = None, ip: str = "",
               user_agent: str = "", **detail) -> None:
        """`detail` keys are validated and values of sensitive-looking keys are redacted; still, callers
        should pass only ids, emails and reasons."""
        if outcome not in _OUTCOMES:
            raise ValueError(f"invalid audit outcome: {outcome!r}")
        for key in detail:
            if not _KEY.fullmatch(key) or key in _RESERVED:
                raise ValueError(f"invalid audit detail key: {key!r}")
        safe = {k: REDACTED if any(w in k for w in _SENSITIVE) else v for k, v in detail.items()}
        parts = [f"event={_clean(event)}", f"outcome={_clean(outcome)}", f"user={_clean(user_id or '-')}",
                 f"ip={_clean(ip or '-')}"]
        if user_agent:
            parts.append(f"ua={_clean(user_agent[:_USER_AGENT_LOG_LIMIT])}")
        parts += [f"{k}={_clean(v)}" for k, v in sorted(safe.items())]
        self._logger.info(" ".join(parts))  # logged first, so a failing store still leaves a trace
        self._repo.add(AuditEvent(self._clock(), event, outcome, user_id, ip,  # type: ignore[arg-type]
                                  user_agent[:_USER_AGENT_STORE_LIMIT], safe))

    def purge(self, older_than_days: int = 90) -> None:
        self._repo.purge(self._clock() - older_than_days * 86400)
