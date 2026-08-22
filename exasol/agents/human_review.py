"""
agents/human_review.py — not an AI agent; the code path a human reviewer's
UI action goes through. Included alongside the other agents because the
architecture treats human review as a first-class step in the pipeline,
with the same audit obligations as any automated one.
"""

import uuid

from database.audit import log_event
from database.db import Database
from orchestration.state import set_status

INSERT_REVIEW_SQL = """
    INSERT INTO HUMAN_REVIEWS
        (review_id, doc_id, field_id, field_name, ai_value, human_value, status, reviewed_by, reviewed_at)
    VALUES
        (:review_id, :doc_id, :field_id, :field_name, :ai_value, :human_value, :status, :reviewed_by, CURRENT_TIMESTAMP)
"""

UPDATE_FIELD_VALUE_SQL = """
    UPDATE EXTRACTED_FIELDS
    SET field_value = :value, confidence = 1.0, source_agent = 'human_review'
    WHERE field_id = :field_id
"""

GET_OPEN_REVIEWS_SQL = """
    SELECT field_id FROM EXTRACTED_FIELDS
    WHERE doc_id = :doc_id AND confidence < :threshold
"""


def submit_review(
    db: Database,
    doc_id: str,
    field_id: str,
    field_name: str,
    ai_value: str | None,
    human_value: str | None,
    status: str,  # 'confirmed' | 'corrected' | 'rejected'
    reviewed_by: str,
) -> str:
    """Record one human decision on a low-confidence field. If this was
    the document's last open review, advance the document to 'reasoning'.
    """
    review_id = str(uuid.uuid4())
    db.execute(
        INSERT_REVIEW_SQL,
        {
            "review_id": review_id,
            "doc_id": doc_id,
            "field_id": field_id,
            "field_name": field_name,
            "ai_value": ai_value,
            "human_value": human_value,
            "status": status,
            "reviewed_by": reviewed_by,
        },
    )

    if status in ("confirmed", "corrected") and human_value is not None:
        db.execute(UPDATE_FIELD_VALUE_SQL, {"field_id": field_id, "value": human_value})

    log_event(
        db,
        agent_name="human",
        action=f"review_{status}",
        doc_id=doc_id,
        input_summary=f"field={field_name}, ai_value={ai_value}",
        output_summary=f"human_value={human_value}, reviewed_by={reviewed_by}",
        confidence=1.0,
    )

    return review_id


def advance_if_reviews_complete(db: Database, doc_id: str, threshold: float) -> bool:
    """Check whether any field is still below threshold and hasn't been
    corrected to confidence 1.0. If none remain, move the document to
    'reasoning'. Returns True if the document advanced.
    """
    remaining = db.fetchall(GET_OPEN_REVIEWS_SQL, {"doc_id": doc_id, "threshold": threshold})
    if remaining:
        return False
    set_status(db, doc_id, "reasoning", current_status="review")
    log_event(
        db,
        agent_name="human",
        action="all_reviews_complete",
        doc_id=doc_id,
        output_summary="Document advanced to reasoning.",
    )
    return True
