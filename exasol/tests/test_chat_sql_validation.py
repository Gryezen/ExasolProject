"""
tests/test_chat_sql_validation.py — the chat agent's validate_sql() is the
first line of defense before a generated query touches even the read-only
identity. These tests don't need a live Exasol connection.
"""

import pytest

from agents.chat import SQLValidationError, validate_sql


def test_allows_simple_select():
    assert validate_sql("SELECT * FROM DOCUMENTS") == "SELECT * FROM DOCUMENTS"


def test_allows_select_with_trailing_semicolon():
    assert validate_sql("SELECT doc_id FROM DOCUMENTS;") == "SELECT doc_id FROM DOCUMENTS"


def test_rejects_insert():
    with pytest.raises(SQLValidationError):
        validate_sql("INSERT INTO DOCUMENTS (doc_id) VALUES ('x')")


def test_rejects_update():
    with pytest.raises(SQLValidationError):
        validate_sql("UPDATE DOCUMENTS SET status = 'complete'")


def test_rejects_delete():
    with pytest.raises(SQLValidationError):
        validate_sql("DELETE FROM DOCUMENTS")


def test_rejects_drop():
    with pytest.raises(SQLValidationError):
        validate_sql("DROP TABLE DOCUMENTS")


def test_rejects_statement_chaining():
    with pytest.raises(SQLValidationError):
        validate_sql("SELECT 1; DROP TABLE DOCUMENTS;")


def test_rejects_non_select_start():
    with pytest.raises(SQLValidationError):
        validate_sql("WITH x AS (SELECT 1) DELETE FROM DOCUMENTS")


def test_rejects_keyword_hidden_in_select():
    # A SELECT that embeds a forbidden keyword (e.g. via a subquery attempt)
    # should still be rejected even though it starts with SELECT.
    with pytest.raises(SQLValidationError):
        validate_sql("SELECT * FROM DOCUMENTS WHERE 1=1; DROP TABLE DOCUMENTS")
