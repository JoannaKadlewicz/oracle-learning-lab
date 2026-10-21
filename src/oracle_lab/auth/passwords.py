"""scrypt password hashing and the password policy."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import secrets
from pathlib import Path

_N, _R, _P = 32768, 8, 1
_MAXMEM = 64 * 1024 * 1024
_DKLEN = 32
_SALT_BYTES = 16

MIN_LENGTH = 12
MAX_LENGTH = 128


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, maxmem=_MAXMEM, dklen=_DKLEN)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(_SALT_BYTES)
    key = _scrypt(password, salt, _N, _R, _P)
    return f"scrypt${_N}${_R}${_P}${base64.b64encode(salt).decode('ascii')}${base64.b64encode(key).decode('ascii')}"


def _parse(encoded: str) -> tuple[int, int, int, bytes, bytes] | None:
    try:
        scheme, n, r, p, salt, key = encoded.split("$")
        if scheme != "scrypt":
            return None
        return int(n), int(r), int(p), base64.b64decode(salt, validate=True), base64.b64decode(key, validate=True)
    except (ValueError, binascii.Error, AttributeError):
        return None


def verify_password(password: str, encoded: str) -> bool:
    """True when the password matches; False for a wrong password or an unreadable hash, never an exception."""
    parsed = _parse(encoded)
    if parsed is None:
        return False
    n, r, p, salt, expected = parsed
    try:
        actual = _scrypt(password, salt, n, r, p)
    except (ValueError, MemoryError, OverflowError):
        return False
    return hmac.compare_digest(actual, expected)


def needs_rehash(encoded: str) -> bool:
    parsed = _parse(encoded)
    return parsed is None or parsed[:3] != (_N, _R, _P)


# Verified against when the account does not exist, so that both paths cost about the same.
DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def load_common_passwords(path: Path) -> frozenset[str]:
    words = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            words.add(line.lower())
    return frozenset(words)


class PasswordPolicy:
    def __init__(self, common: frozenset[str]):
        self._common = common

    def problems(self, password: str, email: str) -> list[str]:
        if len(password) < MIN_LENGTH:
            return [f"Use at least {MIN_LENGTH} characters."]
        if len(password) > MAX_LENGTH:
            return [f"Use at most {MAX_LENGTH} characters."]
        found = []
        if password.strip().lower() == email.strip().lower():
            found.append("Don't use your email address as the password.")
        if password.lower() in self._common:
            found.append("This password is too common. Pick something less predictable.")
        return found
