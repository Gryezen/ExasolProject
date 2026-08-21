"""
agents/reasoning.py — the differentiator. Compares extracted fields across
documents linked in DOCUMENT_RELATIONSHIPS (invoice<->PO, income-cert<->
welfare-application, etc.) and produces structured DISCREPANCIES rows,
not prose. Reasoning output must be structured so it can be queried by
the chat agent and displayed consistently in the audit timeline.
"""

import uuid

import anthropic

from config import Settings
from database.audit import log_event
from database.db import Database

_REASONING_TOOL = {
    "name": "record_discrepancies",
    "description": (
        "Record structured discrepancies found by comparing the same "
        "business facts across two related documents. Only report a "
        "discrepancy when the two documents actually disagree on a fact "
        "that matters (amounts, dates, terms, names, quantities) — do not "
        "invent mismatches for fields that are simply absent on one side."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "discrepancies": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "field_name": {"type": "string"},
                        "value_1": {"type": "string"},
                        "value_2": {"type": "string"},
                        "severity": {"type": "string", "enum": ["low", "medium", "high"]},
                        "explanation": {
                            "type": "string",
                            "description": "One or two sentences: what disagrees and why it matters.",
                        },
                    },
                    "required": ["field_name", "value_1", "value_2", "severity", "explanation"],
                },
            }
        },
        "required": ["discrepancies"],
    },
}

_SYSTEM_PROMPT = """You are a cross-document reasoning agent. You are given the \
extracted fields from two related documents (e.g. an invoice and its purchase \
order, or a citizen's income certificate and their welfare application). Compare \
the fields that should logically agree between the two documents and flag any \
real disagreement.

Severity guide:
- high: financial amounts, legal terms, or identity fields disagree in a way \
that changes what should happen next.
- medium: dates, quantities, or terms disagree but the impact is ambiguous.
- low: minor formatting/wording differences unlikely to matter.

Do not flag a field as a discrepancy just because it appears on one document \
and not the other — that is a coverage gap, not a disagreement. Only compare \
fields present on both sides."""

INSERT_DISCREPANCY_SQL = """
    INSERT INTO DISCREPANCIES
        (discrepancy_id, doc_id_1, doc_id_2, field_name, value_1, value_2, severity, status, explanation, detected_at)
    VALUES
        (:discrepancy_id, :doc_id_1, :doc_id_2, :field_name, :value_1, :value_2, :severity, 'open', :explanation, CURRENT_TIMESTAMP)
"""

GET_FIELDS_SQL = """
    SELECT field_name, value, confidence
    FROM EXTRACTED_FIELDS
    WHERE doc_id = :doc_id
"""


class Discrepancy:
    def __init__(self, discrepancy_id, doc_id_1, doc_id_2, field_name, value_1, value_2, severity, explanation):
        self.discrepancy_id = discrepancy_id
        self.doc_id_1 = doc_id_1
        self.doc_id_2 = doc_id_2
        self.field_name = field_name
        self.value_1 = value_1
        self.value_2 = value_2
        self.severity = severity
        self.explanation = explanation


def _fields_to_text(rows: list[tuple]) -> str:
    return "\n".join(f"- {name}: {value} (confidence {conf})" for name, value, conf in rows)


def compare_documents(
    db: Database,
    settings: Settings,
    doc_id_1: str,
    doc_id_2: str,
) -> list[Discrepancy]:
    """Compare two related documents' extracted fields and persist any
    discrepancies found. Returns the list of discrepancies (empty if none).
    """
    fields_1 = db.fetchall(GET_FIELDS_SQL, {"doc_id": doc_id_1})
    fields_2 = db.fetchall(GET_FIELDS_SQL, {"doc_id": doc_id_2})

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model=settings.reasoning_model,
        max_tokens=4096,
        system=_SYSTEM_PROMPT,
        tools=[_REASONING_TOOL],
        tool_choice={"type": "tool", "name": "record_discrepancies"},
        messages=[
            {
                "role": "user",
                "content": (
                    f"Document A fields:\n{_fields_to_text(fields_1)}\n\n"
                    f"Document B fields:\n{_fields_to_text(fields_2)}\n\n"
                    "Compare and record any real discrepancies."
                ),
            }
        ],
    )

    tool_use_block = next((b for b in response.content if b.type == "tool_use"), None)
    if tool_use_block is None:
        raise ValueError("Reasoning model did not return a tool_use block")

    discrepancies_raw = tool_use_block.input.get("discrepancies", [])
    results: list[Discrepancy] = []
    for d in discrepancies_raw:
        discrepancy_id = str(uuid.uuid4())
        db.execute(
            INSERT_DISCREPANCY_SQL,
            {
                "discrepancy_id": discrepancy_id,
                "doc_id_1": doc_id_1,
                "doc_id_2": doc_id_2,
                "field_name": d["field_name"],
                "value_1": d["value_1"],
                "value_2": d["value_2"],
                "severity": d["severity"],
                "explanation": d["explanation"],
            },
        )
        results.append(
            Discrepancy(
                discrepancy_id, doc_id_1, doc_id_2,
                d["field_name"], d["value_1"], d["value_2"], d["severity"], d["explanation"],
            )
        )

    log_event(
        db,
        agent_name="reasoning",
        action="compared_documents",
        doc_id=doc_id_1,
        input_summary=f"doc_id_2={doc_id_2}, fields_compared={len(fields_1)}+{len(fields_2)}",
        output_summary=f"discrepancies_found={len(results)}",
    )

    return results
