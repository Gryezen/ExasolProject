"""
models/document.py — typed structures passed between agents.

These are the shapes agents agree on in memory, before/after they get
written to or read from DOC_INTEL. Keeping them as pydantic models means a
malformed LLM extraction fails loudly here rather than silently corrupting
a row downstream.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


DocumentStatus = Literal[
    "uploaded", "extracting", "review", "reasoning", "complete", "failed"
]


class Document(BaseModel):
    doc_id: str
    filename: str
    document_type: str | None = None
    vendor: str | None = None
    status: DocumentStatus = "uploaded"
    source_path: str | None = None
    page_count: int | None = None
    uploaded_by: str | None = None
    uploaded_at: datetime | None = None


class ExtractedField(BaseModel):
    field_id: str
    doc_id: str
    field_name: str
    value: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    source_agent: str = "extraction"


class Discrepancy(BaseModel):
    discrepancy_id: str
    doc_id_1: str
    doc_id_2: str | None = None
    field_name: str
    value_1: str | None = None
    value_2: str | None = None
    severity: Literal["low", "medium", "high"]
    status: Literal["open", "acknowledged", "resolved", "dismissed"] = "open"
    explanation: str | None = None


class ActionProposal(BaseModel):
    action_id: str
    discrepancy_id: str | None = None
    doc_id: str | None = None
    action_type: Literal["email_draft", "task_proposal"]
    content: str
    status: Literal["proposed", "approved", "rejected", "sent"] = "proposed"
