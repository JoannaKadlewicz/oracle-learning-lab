"""The in-memory stores satisfy the shared account-store contract."""

from __future__ import annotations

import pytest

from accounts_contract import CONTRACT
from oracle_lab.accounts.memory import memory_stores
from oracle_lab.auth.tokens import new_id, new_token, normalise_email, token_hash


@pytest.mark.parametrize("check", CONTRACT, ids=lambda f: f.__name__)
def test_contract(check):
    check(memory_stores())


def test_tokens():
    assert new_token() != new_token() and new_id() != new_id()
    assert token_hash("a") == token_hash("a") != token_hash("b")
    assert len(token_hash("a")) == 64
    assert normalise_email("  Ann@Example.COM ") == "ann@example.com"
