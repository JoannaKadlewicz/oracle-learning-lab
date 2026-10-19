"""Success messages worded like SQL*Plus prints them."""

from oracle_lab.sqltext.statements import first_words

_FIXED = {
    "COMMIT": "Commit complete.",
    "ROLLBACK": "Rollback complete.",
    "SAVEPOINT": "Savepoint created.",
    "GRANT": "Grant succeeded.",
    "REVOKE": "Revoke succeeded.",
    "TRUNCATE": "Table truncated.",
    "FLASHBACK": "Flashback complete.",
    "COMMENT": "Comment created.",
}
_ROW_VERBS = {"INSERT": "inserted", "UPDATE": "updated", "DELETE": "deleted", "MERGE": "merged"}
_DDL_VERBS = {"CREATE": "created", "ALTER": "altered", "DROP": "dropped", "RENAME": "renamed", "PURGE": "purged"}
_NOT_A_NOUN = {"OR", "GLOBAL", "PUBLIC", "UNIQUE"}  # CREATE OR REPLACE VIEW, CREATE UNIQUE INDEX, ...

PLSQL_DONE = "PL/SQL procedure successfully completed."


def describe_success(text: str, rowcount: int) -> str:
    verb, obj = first_words(text)
    if verb in _ROW_VERBS:
        return f"{rowcount} {'row' if rowcount == 1 else 'rows'} {_ROW_VERBS[verb]}."
    if verb in _FIXED:
        return _FIXED[verb]
    if verb in _DDL_VERBS:
        noun = obj.capitalize() if obj and obj not in _NOT_A_NOUN else "Object"
        return f"{noun} {_DDL_VERBS[verb]}."
    return "Statement executed."
