"""Limits on learner sessions: one statement at a time per user, and a cap on all of them together."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager

from oracle_lab.web.http import HttpError

ALREADY_RUNNING = "Another statement of yours is still running."
BUSY = "The practice database is busy. Try again in a moment."


class RunGuard:
    """`with guard.run(user_id):` around everything that opens a learner session."""

    def __init__(self, max_concurrent: int = 8, wait_seconds: float = 5.0):
        self.wait_seconds = wait_seconds
        self._slots = threading.BoundedSemaphore(max_concurrent)
        self._running: set[str] = set()
        self._lock = threading.Lock()

    @contextmanager
    def run(self, user_id: str) -> Iterator[None]:
        """409 when the user already runs something (no waiting); 503 when no slot frees up within wait_seconds."""
        with self._lock:
            if user_id in self._running:
                raise HttpError(409, ALREADY_RUNNING)
            self._running.add(user_id)
        try:
            if not self._slots.acquire(timeout=self.wait_seconds):
                raise HttpError(503, BUSY)
            try:
                yield
            finally:
                self._slots.release()
        finally:
            with self._lock:
                self._running.discard(user_id)
