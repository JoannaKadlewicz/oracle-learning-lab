"""Random tokens, their stored hashes and email normalisation."""

from __future__ import annotations

import hashlib
import secrets


def new_token() -> str:
    return secrets.token_urlsafe(32)


def new_id() -> str:
    return secrets.token_urlsafe(16)


def token_hash(token: str) -> str:
    """What is stored instead of the token itself."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def normalise_email(email: str) -> str:
    """The form emails are compared and stored in; it does not validate."""
    return email.strip().lower()
