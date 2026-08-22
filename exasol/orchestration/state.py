"""
orchestration/state.py — the state machine described in the architecture doc:

    uploaded -> extracting -> (review if low confidence) -> reasoning
             -> (action + human_approval if discrepancy found) -> complete

This module only defines legal transitions and persists the current status
onto DOCUMENTS.status. It does not call any agent itself — workflow.py
drives the loop and calls agents in between transitions.
"""

from database.db import Database

_TRANSITIONS: dict[str, set[str]] = {
    "uploaded": {"extracting", "failed"},
    "extracting": {"review", "reasoning", "failed"},
    "review": {"reasoning", "failed"},
    "reasoning": {"complete", "failed"},
    "complete": set(),
    "failed": {"extracting"},  # allow a manual retry
}


class IllegalTransition(Exception):
    pass


def set_status(db: Database, doc_id: str, new_status: str, current_status: str) -> None:
    if new_status not in _TRANSITIONS.get(current_status, set()):
        raise IllegalTransition(
            f"Cannot move doc {doc_id} from '{current_status}' to '{new_status}'"
        )
    db.execute(
        "UPDATE DOCUMENTS SET status = {status}, updated_at = CURRENT_TIMESTAMP WHERE doc_id = {doc_id}",
        {"status": new_status, "doc_id": doc_id},
    )
