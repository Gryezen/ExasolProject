"""
tests/test_relationships.py — the deterministic rule pass in
agents/relationships.py should match known compatible document-type pairs
regardless of argument order, and correctly refuse unknown pairs so they
fall through to the model fallback instead of being silently ignored.
"""

from agents.relationships import _rule_based_match


def test_matches_invoice_purchase_order():
    assert _rule_based_match("invoice", "purchase_order") == "invoice_to_po"


def test_matches_regardless_of_argument_order():
    assert _rule_based_match("purchase_order", "invoice") == "invoice_to_po"


def test_matches_income_certificate_welfare_application():
    assert _rule_based_match("income_certificate", "welfare_application") == "income_cert_to_application"


def test_matches_land_record_property_tax_receipt():
    assert _rule_based_match("land_record", "property_tax_receipt") == "land_record_to_tax_receipt"


def test_unknown_pair_returns_none():
    assert _rule_based_match("invoice", "birth_certificate") is None


def test_same_type_twice_returns_none():
    # Two invoices from the same vendor are not automatically "related" by
    # type alone — that would need vendor+content-level judgment, not a rule.
    assert _rule_based_match("invoice", "invoice") is None
