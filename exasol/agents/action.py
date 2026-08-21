"""
agents/action.py — drafts a next-step proposal for a discrepancy. Per the
architecture's reliability rules, this NEVER sends real email or performs
a real action; it only writes an ACTIONS row with status='proposed' for a
human to approve or reject.
"""

import uuid

import anthropic

from config import Settings
from database.audit import log_event
from database.db import Database

_ACTION_TOOL = {
    "name": "draft_action",
    "description": (
        "Draft a next-step proposal for a discrepancy: a short clarification "
        "email and/or a task description for a case handler. This is a draft "
        "only — it will be shown to a human for approval, never sent automatically."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "email_subject": {"type": "string"},
            "email_body": {"type": "string"},
            "task_description": {
                "type": "string",
                "description": "A short actionable task for the case handler, independent of the email.",
            },
        },
        "required": ["email_subject", "email_body", "task_description"],
    },
}

_SYSTEM_PROMPT = """You are an action-drafting agent. Given a discrepancy found \
between two related documents, draft:
1. A short, professional clarification email to the relevant party (vendor or \
citizen) asking them to resolve or explain the discrepancy.
2. A one-line task description for the internal case handler.

Be specific about the discrepancy (name the field and both values) and keep the \
tone neutral and non-accusatory — the goal is clarification, not blame. Do not \
claim any action has already been taken."""

INSERT_ACTION_SQL = """
    INSERT INTO ACTIONS
        (action_id, discrepancy_id, doc_id, action_type, content, status, created_at)
    VALUES
        (:action_id, :discrepancy_id, :doc_id, :action_type, :content, 'proposed', CURRENT_TIMESTAMP)
"""

GET_DISCREPANCY_SQL = """
    SELECT field_name, value_1, value_2, severity, explanation
    FROM DISCREPANCIES
    WHERE discrepancy_id = :discrepancy_id
"""


def draft_action_for_discrepancy(
    db: Database,
    settings: Settings,
    discrepancy_id: str,
    doc_id: str,
) -> tuple[str, str]:
    """Draft an email + task for one discrepancy. Returns (email_action_id, task_action_id)."""
    rows = db.fetchall(GET_DISCREPANCY_SQL, {"discrepancy_id": discrepancy_id})
    if not rows:
        raise ValueError(f"No discrepancy found with id {discrepancy_id}")
    field_name, value_1, value_2, severity, explanation = rows[0]

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model=settings.reasoning_model,
        max_tokens=1024,
        system=_SYSTEM_PROMPT,
        tools=[_ACTION_TOOL],
        tool_choice={"type": "tool", "name": "draft_action"},
        messages=[
            {
                "role": "user",
                "content": (
                    f"Discrepancy: field '{field_name}' disagrees "
                    f"(value 1: {value_1!r}, value 2: {value_2!r}). "
                    f"Severity: {severity}. Explanation: {explanation}"
                ),
            }
        ],
    )

    tool_use_block = next((b for b in response.content if b.type == "tool_use"), None)
    if tool_use_block is None:
        raise ValueError("Action model did not return a tool_use block")

    draft = tool_use_block.input
    email_content = f"Subject: {draft['email_subject']}\n\n{draft['email_body']}"

    email_action_id = str(uuid.uuid4())
    task_action_id = str(uuid.uuid4())

    db.execute(
        INSERT_ACTION_SQL,
        {
            "action_id": email_action_id,
            "discrepancy_id": discrepancy_id,
            "doc_id": doc_id,
            "action_type": "email_draft",
            "content": email_content,
        },
    )
    db.execute(
        INSERT_ACTION_SQL,
        {
            "action_id": task_action_id,
            "discrepancy_id": discrepancy_id,
            "doc_id": doc_id,
            "action_type": "task_proposal",
            "content": draft["task_description"],
        },
    )

    log_event(
        db,
        agent_name="action",
        action="drafted_action",
        doc_id=doc_id,
        input_summary=f"discrepancy_id={discrepancy_id}, field={field_name}",
        output_summary=f"email_action_id={email_action_id}, task_action_id={task_action_id}",
    )

    return email_action_id, task_action_id


def decide_action(db: Database, action_id: str, decision: str, decided_by: str) -> None:
    """Human approves or rejects a drafted action. decision: 'approved' | 'rejected'."""
    if decision not in ("approved", "rejected"):
        raise ValueError("decision must be 'approved' or 'rejected'")
    db.execute(
        """
        UPDATE ACTIONS
        SET status = :status, decided_at = CURRENT_TIMESTAMP, decided_by = :decided_by
        WHERE action_id = :action_id
        """,
        {"status": decision, "decided_by": decided_by, "action_id": action_id},
    )
    log_event(
        db,
        agent_name="human",
        action=f"action_{decision}",
        input_summary=f"action_id={action_id}",
        output_summary=f"decided_by={decided_by}",
    )
