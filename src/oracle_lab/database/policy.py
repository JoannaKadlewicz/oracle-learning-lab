"""Statements the lab refuses to run, because they would break the app's own connection."""

from oracle_lab.sqltext.statements import first_words

BLOCKED_MESSAGE = ("ALTER USER is blocked: changing the ORASTUDY password would no longer match "
                   "the password file the app connects with.")


def is_blocked(text: str) -> bool:
    return first_words(text) == ("ALTER", "USER")
