"""Server-side sessions: only the token hash is stored; idle and absolute lifetimes are enforced here."""

from __future__ import annotations

import dataclasses

from oracle_lab.accounts.repositories import SessionRepository
from oracle_lab.auth.models import SessionRecord
from oracle_lab.auth.tokens import new_token, token_hash
from oracle_lab.services import Clock

DAY = 86400
TOUCH_INTERVAL = 60.0


class SessionManager:
    """`expires_at` on the record is the hard (absolute) deadline, so repository purges never drop a live
    session; the idle deadline is last_seen_at + idle, computed on resolve."""

    def __init__(self, repo: SessionRepository, clock: Clock, idle: float = 7 * DAY, absolute: float = 30 * DAY) -> None:
        self._repo = repo
        self._clock = clock
        self._idle = idle
        self._absolute = absolute

    def start(self, user_id: str, ip: str, user_agent: str) -> tuple[str, SessionRecord]:
        now = self._clock()
        token = new_token()
        rec = SessionRecord(
            token_hash=token_hash(token),
            user_id=user_id,
            csrf_token=new_token(),
            created_at=now,
            last_seen_at=now,
            expires_at=now + self._absolute,
            ip=ip,
            user_agent=user_agent[:200],
        )
        self._repo.add(rec)
        return token, rec

    def resolve(self, token: str) -> SessionRecord | None:
        digest = token_hash(token)
        rec = self._repo.get(digest)
        if rec is None:
            return None
        now = self._clock()
        if now >= rec.created_at + self._absolute or now >= rec.last_seen_at + self._idle:
            self._repo.delete(digest)
            return None
        if now - rec.last_seen_at >= TOUCH_INTERVAL:
            self._repo.touch(digest, now)
            rec = dataclasses.replace(rec, last_seen_at=now)
        return rec

    def live(self, user_id: str) -> list[SessionRecord]:
        """The user's sessions that have not passed their idle or absolute deadline (read only)."""
        now = self._clock()
        return [rec for rec in self._repo.for_user(user_id)
                if now < rec.created_at + self._absolute and now < rec.last_seen_at + self._idle]

    def end(self, token: str) -> None:
        self._repo.delete(token_hash(token))

    def end_all(self, user_id: str, keep_token: str | None = None) -> None:
        self._repo.delete_for_user(user_id, token_hash(keep_token) if keep_token else None)

    def mark_reauth(self, token: str, seconds: float = 300) -> None:
        self.mark_reauth_hash(token_hash(token), seconds)

    def mark_reauth_hash(self, digest: str, seconds: float = 300) -> None:
        """For callers that only hold a Principal (which carries the session hash, not the token)."""
        self._repo.set_reauth(digest, self._clock() + seconds)
