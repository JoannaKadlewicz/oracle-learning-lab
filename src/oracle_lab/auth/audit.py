"""Security audit trail: every event is stored and written as one log line."""

import logging

from oracle_lab.accounts.repositories import AuditRepository
from oracle_lab.auth.models import AuditEvent
from oracle_lab.services import Clock

_USER_AGENT_LOG_LIMIT = 80


def _clean(value: object) -> str:
    """One log token: no line breaks (log injection), repr-quoted when ambiguous."""
    text = str(value).replace("\r", "").replace("\n", "")
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
        """`detail` must never contain secrets; callers pass only ids, emails and reasons."""
        self._repo.add(AuditEvent(self._clock(), event, outcome, user_id, ip, user_agent, dict(detail)))  # type: ignore[arg-type]
        parts = [f"event={_clean(event)}", f"outcome={_clean(outcome)}", f"user={_clean(user_id or '-')}",
                 f"ip={_clean(ip or '-')}"]
        if user_agent:
            parts.append(f"ua={_clean(user_agent[:_USER_AGENT_LOG_LIMIT])}")
        parts += [f"{k}={_clean(v)}" for k, v in sorted(detail.items())]
        self._logger.info(" ".join(parts))

    def purge(self, older_than_days: int = 90) -> None:
        self._repo.purge(self._clock() - older_than_days * 86400)
