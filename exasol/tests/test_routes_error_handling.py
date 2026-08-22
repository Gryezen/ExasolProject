"""
tests/test_routes_error_handling.py — every route that calls out to an
agent, the LLM, or the database must turn a failure into a JSON error body,
never a bare Flask 500 HTML page. A frontend calling fetch(...).json() on
an HTML error page gets a confusing, unhelpful failure with no message —
that's the bug this test suite pins down (previously /api/chat,
/api/documents/<id>/process, /api/reviews, and /api/actions/<id>/decide
had no try/except at all).

Database/ReadOnlyDatabase connect lazily (see database/db.py), so importing
api.routes and exercising these routes with mocked-out agent calls never
touches a real Exasol instance.
"""

import os
from unittest.mock import patch

os.environ.setdefault("EXASOL_PASSWORD", "test")
os.environ.setdefault("EXASOL_RO_USER", "test")
os.environ.setdefault("EXASOL_RO_PASSWORD", "test")
os.environ.setdefault("GEMINI_API_KEY", "test")

import pytest

from api.routes import app as flask_app


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    return flask_app.test_client()


def _assert_json_error(resp):
    assert resp.status_code == 500
    assert resp.is_json, "route must return a JSON error body, not an HTML 500 page"
    body = resp.get_json()
    assert "error" in body and body["error"]


@patch("api.routes.workflow.compare_related_documents", side_effect=RuntimeError("boom"))
def test_process_document_failure_returns_json_error(mock_compare, client):
    resp = client.post("/api/documents/doc-1/process")
    _assert_json_error(resp)


@patch("api.routes.chat_agent.ask", side_effect=RuntimeError("boom"))
def test_chat_failure_returns_json_error(mock_ask, client):
    resp = client.post("/api/chat", json={"question": "which vendors have discrepancies?"})
    _assert_json_error(resp)


@patch("api.routes.human_review_agent.submit_review", side_effect=RuntimeError("boom"))
def test_submit_review_failure_returns_json_error(mock_submit, client):
    resp = client.post(
        "/api/reviews",
        json={
            "doc_id": "d1", "field_id": "f1", "field_name": "amount",
            "ai_value": "100", "human_value": "110",
            "status": "corrected", "reviewed_by": "tester",
        },
    )
    _assert_json_error(resp)


@patch("api.routes.action_agent.decide_action", side_effect=RuntimeError("boom"))
def test_decide_action_failure_returns_json_error(mock_decide, client):
    resp = client.post("/api/actions/a1/decide", json={"decision": "approved", "decided_by": "tester"})
    _assert_json_error(resp)
