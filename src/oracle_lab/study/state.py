"""Persistence of the study progress (the `state` dict described in study.engine)."""

from __future__ import annotations

import copy
import json
import os
import tempfile
import threading
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from typing import Any, Protocol

State = dict[str, Any]


def new_state() -> State:
    return {"attempts": {}, "cards": {}, "labs": {}, "settings": {}, "mocks": []}


class StateStore(Protocol):
    def load(self) -> State:
        """A snapshot of the saved state (changes to it are not saved)."""

    def transaction(self) -> AbstractContextManager[State]:
        """Yield the state for changing; it is saved when the block ends without an exception."""


class JsonStateStore:
    """The state in one JSON file. Writes are serialized and atomic (write to a temp file, rename)."""

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()

    def load(self) -> State:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return new_state()

    @contextmanager
    def transaction(self) -> Iterator[State]:
        with self._lock:
            state = self.load()
            yield state
            self._save(state)

    def _save(self, state: State) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=f".{self.path.name}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=1)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise


class MemoryStateStore:
    """The state in memory, for tests and simulations."""

    def __init__(self, state: State | None = None):
        self.state = state if state is not None else new_state()
        self._lock = threading.Lock()

    def load(self) -> State:
        return copy.deepcopy(self.state)

    @contextmanager
    def transaction(self) -> Iterator[State]:
        with self._lock:
            state = self.load()
            yield state
            self.state = state
