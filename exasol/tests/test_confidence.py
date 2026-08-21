"""
tests/test_confidence.py — the confidence gate is deterministic application
logic (no model call), so it's fully testable with a fake database.
"""

from agents.confidence import run_confidence_gate


class FakeDatabase:
    def __init__(self, field_rows):
        self._field_rows = field_rows
        self.execute_calls = []

    def fetchall(self, sql, params=None):
        return self._field_rows

    def execute(self, sql, params=None):
        self.execute_calls.append((sql, params))


def test_all_fields_high_confidence_auto_approves():
    rows = [
        ("f1", "invoice_amount", "1000", 0.95),
        ("f2", "vendor_name", "Acme Co", 0.9),
    ]
    db = FakeDatabase(rows)
    result = run_confidence_gate(db, doc_id="doc-1", threshold=0.8)
    assert result.decision == "AUTO_APPROVE"
    assert result.low_confidence_fields == []


def test_one_low_confidence_field_triggers_review():
    rows = [
        ("f1", "invoice_amount", "1000", 0.95),
        ("f2", "vendor_name", "Acme Co", 0.4),
    ]
    db = FakeDatabase(rows)
    result = run_confidence_gate(db, doc_id="doc-1", threshold=0.8)
    assert result.decision == "HUMAN_REVIEW"
    assert len(result.low_confidence_fields) == 1
    assert result.low_confidence_fields[0]["field_name"] == "vendor_name"


def test_boundary_confidence_equal_to_threshold_passes():
    # A field exactly at the threshold should NOT be flagged (strictly less-than).
    rows = [("f1", "invoice_amount", "1000", 0.8)]
    db = FakeDatabase(rows)
    result = run_confidence_gate(db, doc_id="doc-1", threshold=0.8)
    assert result.decision == "AUTO_APPROVE"


def test_no_fields_extracted_auto_approves_by_default():
    # No fields means nothing is below threshold; this is a coverage gap
    # to flag separately, not something the confidence gate itself should block on.
    db = FakeDatabase([])
    result = run_confidence_gate(db, doc_id="doc-1", threshold=0.8)
    assert result.decision == "AUTO_APPROVE"
