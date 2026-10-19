"""Passwords, kept out of the code, the logs and (preferably) the environment.

A setting NAME is resolved in this order:

1. NAME_FILE: path of a file holding the value (Docker/Kubernetes secrets, e.g. /run/secrets/...)
2. NAME: the value itself (convenient for CI; visible in `docker inspect`, so avoid it in production)
3. a fallback file, if the caller names one (e.g. ~/.orastudy_pwd for local development)

Files are read when the value is needed, not at startup, so a rotated secret file takes effect
without a restart. `Secret` never shows its value in repr() or str(), so it cannot leak into logs.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from pathlib import Path


class SecretNotFoundError(LookupError):
    """A required secret has no configured source, or its file cannot be read."""


class Secret:
    """A credential that is read from its source on demand."""

    __slots__ = ("_read", "source")

    def __init__(self, read: Callable[[], str], source: str):
        self._read = read
        self.source = source

    @classmethod
    def from_file(cls, path: Path) -> Secret:
        def read() -> str:
            try:
                return path.read_text(encoding="utf-8").strip()
            except OSError as exc:
                raise SecretNotFoundError(f"cannot read secret file {path}: {exc.strerror}") from exc

        return cls(read, f"file {path}")

    @classmethod
    def from_value(cls, value: str, source: str) -> Secret:
        return cls(lambda: value, source)

    @classmethod
    def missing(cls, name: str) -> Secret:
        def read() -> str:
            raise SecretNotFoundError(f"no password configured: set {name}_FILE (or {name})")

        return cls(read, "not configured")

    def reveal(self) -> str:
        return self._read()

    def __repr__(self) -> str:
        return f"Secret(<{self.source}>)"

    __str__ = __repr__


def resolve_secret(name: str, env: Mapping[str, str] = os.environ,
                   fallback_file: Path | None = None) -> Secret | None:
    """The secret for setting `name`, or None when no source is configured."""
    if file := env.get(f"{name}_FILE"):
        return Secret.from_file(Path(file).expanduser())
    if value := env.get(name):
        return Secret.from_value(value, f"environment variable {name}")
    if fallback_file is not None and fallback_file.is_file():
        return Secret.from_file(fallback_file)
    return None
