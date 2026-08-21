"""
database/audit.py — the explainability backbone.

Every agent (ingestion, extraction, confidence_gate, reasoning, action,
chat, human) calls log_event() after each meaningful step. Nothing else in
this codebase should read AUDIT_LOG as anything but a record of what
already happened — it is append-only from the application's point of view.
"""

import uuid
from datetime import datetime, timezone

from database.db import Database

INSERT_SQL = """
    INSERT INTO AUDIT_LOG
        (log_id, doc_id, agent_name, action, input_summary, output_summary, confidence, timestamp)
    VALUES
        (:log_id, :doc_id, :agent_name, :action, :input_summary, :output_summary, :confidence, :timestamp)
"""


def log_event(
    db: Database,
    agent_name: str,
    action: str,
    doc_id: str | None = None,
    input_summary: str | None = None,
    output_summary: str | None = None,
    confidence: float | None = None,
) -> str:
    """Write one AUDIT_LOG row and return its id.

    Summaries are truncated defensively — this table is for a judge or
    officer to reconstruct *what happened and why*, not to store full
    payloads (those live in EXTRACTED_FIELDS / DISCREPANCIES / ACTIONS).
    """
    log_id = str(uuid.uuid4())
    db.execute(
        INSERT_SQL,
        {
            "log_id": log_id,
            "doc_id": doc_id,
            "agent_name": agent_name,
            "action": action,
            "input_summary": (input_summary or "")[:2000],
            "output_summary": (output_summary or "")[:2000],
            "confidence": confidence,
            "timestamp": datetime.now(timezone.utc),
        },
    )
    return log_id
