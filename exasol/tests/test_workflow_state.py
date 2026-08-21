"""
tests/test_workflow_state.py — the state machine in orchestration/state.py
should refuse illegal transitions before ever touching the database. Uses a
minimal fake in place of database.db.Database so no live Exasol connection
is required to run these.
"""

import pytest

from orchestration.state import IllegalTransition, set_status


class FakeDatabase:
    """Records executed statements instead of hitting a real database."""

    def __init__(self):
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))


def test_legal_transition_uploaded_to_extracting():
    db = FakeDatabase()
    set_status(db, "doc-1", "extracting", current_status="uploaded")
    assert len(db.calls) == 1
    assert db.calls[0][1]["status"] == "extracting"


def test_legal_transition_extracting_to_review():
    db = FakeDatabase()
    set_status(db, "doc-1", "review", current_status="extracting")
    assert db.calls[0][1]["status"] == "review"


def test_legal_transition_extracting_to_reasoning():
    db = FakeDatabase()
    set_status(db, "doc-1", "reasoning", current_status="extracting")
    assert db.calls[0][1]["status"] == "reasoning"


def test_illegal_transition_skips_extraction():
    db = FakeDatabase()
    with pytest.raises(IllegalTransition):
        set_status(db, "doc-1", "complete", current_status="uploaded")
    assert db.calls == []  # nothing written on a rejected transition


def test_illegal_transition_from_terminal_complete():
    db = FakeDatabase()
    with pytest.raises(IllegalTransition):
        set_status(db, "doc-1", "reasoning", current_status="complete")


def test_failed_can_retry_to_extracting():
    db = FakeDatabase()
    set_status(db, "doc-1", "extracting", current_status="failed")
    assert db.calls[0][1]["status"] == "extracting"
