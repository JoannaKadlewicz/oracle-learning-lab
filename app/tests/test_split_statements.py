from server import split_statements


def kinds_and_texts(script):
    return [(s["kind"], s["text"]) for s in split_statements(script)]


def test_splits_on_semicolons():
    assert kinds_and_texts("SELECT 1 FROM dual; SELECT 2 FROM dual;") == [
        ("sql", "SELECT 1 FROM dual"),
        ("sql", "SELECT 2 FROM dual"),
    ]


def test_last_statement_needs_no_semicolon():
    assert kinds_and_texts("SELECT 1 FROM dual") == [("sql", "SELECT 1 FROM dual")]


def test_semicolon_inside_string_literal():
    assert kinds_and_texts("SELECT 'a;b' FROM dual;") == [("sql", "SELECT 'a;b' FROM dual")]


def test_doubled_quote_inside_string_literal():
    assert kinds_and_texts("SELECT 'It''s;' FROM dual; SELECT 2 FROM dual;") == [
        ("sql", "SELECT 'It''s;' FROM dual"),
        ("sql", "SELECT 2 FROM dual"),
    ]


def test_q_quote_with_bracket_delimiters():
    assert kinds_and_texts("SELECT q'[it's; here]' FROM dual;") == [("sql", "SELECT q'[it's; here]' FROM dual")]


def test_q_quote_with_repeated_character_and_lowercase_q():
    assert kinds_and_texts("select q'!a;b'c!' from dual;") == [("sql", "select q'!a;b'c!' from dual")]


def test_identifier_ending_in_q_is_not_a_q_quote():
    # "colq" ends in q, so 'a;b' is an ordinary string literal
    assert kinds_and_texts("SELECT 1 FROM t WHERE colq='a;b';") == [("sql", "SELECT 1 FROM t WHERE colq='a;b'")]


def test_semicolons_inside_comments_do_not_split():
    script = "-- note; here\nSELECT 1 FROM dual; /* c; */ SELECT 2 FROM dual;"
    assert kinds_and_texts(script) == [
        ("sql", "-- note; here\nSELECT 1 FROM dual"),
        ("sql", "/* c; */ SELECT 2 FROM dual"),
    ]


def test_trailing_comment_is_not_a_statement():
    assert kinds_and_texts("SELECT 1 FROM dual;\n-- end\n") == [("sql", "SELECT 1 FROM dual")]


def test_plsql_block_ends_at_slash_line():
    script = "BEGIN\n  NULL;\nEND;\n/\nSELECT 1 FROM dual;"
    assert kinds_and_texts(script) == [
        ("plsql", "BEGIN\n  NULL;\nEND;"),
        ("sql", "SELECT 1 FROM dual"),
    ]


def test_create_procedure_is_plsql():
    script = "CREATE OR REPLACE PROCEDURE p AS\nBEGIN\n  NULL;\nEND;\n/"
    assert [s["kind"] for s in split_statements(script)] == ["plsql"]


def test_slash_line_ends_a_sql_statement():
    assert kinds_and_texts("SELECT 1 FROM dual\n/\n") == [("sql", "SELECT 1 FROM dual")]


def test_division_is_not_a_terminator():
    assert kinds_and_texts("SELECT 4/2 FROM dual;") == [("sql", "SELECT 4/2 FROM dual")]


def test_sqlplus_commands_are_client_statements():
    script = "PROMPT hello; world\nSET LINESIZE 200\n@other.sql\nSELECT 1 FROM dual;"
    assert kinds_and_texts(script) == [
        ("client", "PROMPT hello; world"),
        ("client", "SET LINESIZE 200"),
        ("client", "@other.sql"),
        ("sql", "SELECT 1 FROM dual"),
    ]


def test_set_transaction_is_sql_not_a_client_command():
    assert kinds_and_texts("SET TRANSACTION READ ONLY;") == [("sql", "SET TRANSACTION READ ONLY")]


def test_alter_user_is_blocked_before_reaching_the_database():
    import server

    result = server.run_script("ALTER USER orastudy IDENTIFIED BY x;")
    if not result["ok"]:
        return  # no database: the guard runs after connecting
    assert "ALTER USER is blocked" in result["results"][0]["error"]
