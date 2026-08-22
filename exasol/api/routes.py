"""
api/routes.py — Flask surface over the orchestrator, agents, and queries.

Two kinds of routes live here:
  - Page routes (/, /upload, /documents/<id>/..., /chat) render Jinja
    templates from templates/ — one template per screen in the demo flow
    (dashboard -> upload -> extraction -> reasoning -> audit -> chat).
  - JSON routes (/api/...) are unchanged from the original single-page
    app; every page's JS calls these directly.

This is intentionally not the full app (no auth, no file-upload
streaming, no pagination) — it's enough for the frontend/demo owner to
build a real dashboard against real endpoints instead of mocks.

Run standalone with `python -m api.routes`, or `flask --app api.routes run`.
For production (e.g. Render), see Procfile / render.yaml — gunicorn
serves `api.routes:app` the same way.
"""

import os
import uuid
from pathlib import Path

from flask import Flask, abort, jsonify, redirect, render_template, request, url_for
from werkzeug.utils import secure_filename

from agents import chat as chat_agent
from agents import human_review as human_review_agent
from agents import action as action_agent
from config import load_settings
from database.db import Database, ReadOnlyDatabase
from database import queries
from orchestration import workflow

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".txt"}

app = Flask(
    __name__,
    template_folder=str(_PROJECT_ROOT / "templates"),
    static_folder=str(_PROJECT_ROOT / "static"),
    static_url_path="/static",
)
settings = load_settings()
db = Database(settings)
ro_db = ReadOnlyDatabase(settings)

# Pipeline stages shown in the document-page stepper. Order matters —
# it's the order stages render left to right.
_STAGE_LABELS = ["Upload", "Extract", "Confidence", "Reasoning", "Complete"]


def _stage_states(status: str) -> list[dict]:
    """Map a document's status onto the 5-stage stepper the demo flow is
    built around: Upload -> Extract -> Confidence -> Reasoning -> Complete.

    'failed' can happen during ingestion or extraction, so it's shown as
    an error on the Extract stage rather than guessing further — the
    audit trail has the real detail.
    """
    order = ["uploaded", "extracting", "review", "reasoning", "complete"]
    if status == "failed":
        index = 1  # Extract
        return [
            {"label": label, "state": ("done" if i < index else "error" if i == index else "")}
            for i, label in enumerate(_STAGE_LABELS)
        ]
    index = order.index(status) if status in order else 0
    return [
        {"label": label, "state": ("done" if i < index else "active" if i == index else "")}
        for i, label in enumerate(_STAGE_LABELS)
    ]


@app.context_processor
def inject_globals():
    return {"confidence_threshold": settings.confidence_threshold}


def _get_document_or_404(doc_id: str) -> dict:
    row = queries.get_document(db, doc_id)
    if row is None:
        abort(404)
    cols = ["doc_id", "filename", "document_type", "vendor", "status", "page_count", "uploaded_at"]
    return _row_to_dict(row, cols)


# ---------------------------------------------------------------- pages --

@app.route("/", methods=["GET"])
def dashboard():
    stats_row = queries.get_stats(db, settings.confidence_threshold)
    stats = _row_to_dict(stats_row, ["documents_total", "high_confidence_fields", "needs_review", "actions_triggered"])
    return render_template("dashboard.html", active_nav="dashboard", stats=stats)


@app.route("/upload", methods=["GET"])
def upload_page():
    return render_template(
        "upload.html", active_nav="upload", allowed_extensions=sorted(_ALLOWED_EXTENSIONS)
    )


@app.route("/documents/<doc_id>", methods=["GET"])
def document_root(doc_id: str):
    """Bare doc URLs land on Extraction Results — the first screen a case
    handler wants after upload."""
    return redirect(url_for("document_extraction", doc_id=doc_id))


@app.route("/documents/<doc_id>/extraction", methods=["GET"])
def document_extraction(doc_id: str):
    doc = _get_document_or_404(doc_id)
    return render_template(
        "document_extraction.html", active_nav="dashboard", doc=doc, stages=_stage_states(doc["status"])
    )


@app.route("/documents/<doc_id>/reasoning", methods=["GET"])
def document_reasoning(doc_id: str):
    doc = _get_document_or_404(doc_id)
    return render_template(
        "document_reasoning.html", active_nav="dashboard", doc=doc, stages=_stage_states(doc["status"])
    )


@app.route("/documents/<doc_id>/audit", methods=["GET"])
def document_audit(doc_id: str):
    doc = _get_document_or_404(doc_id)
    return render_template(
        "document_audit.html", active_nav="dashboard", doc=doc, stages=_stage_states(doc["status"])
    )


@app.route("/chat", methods=["GET"])
def chat_page():
    doc_id = request.args.get("doc")
    doc_name = None
    if doc_id:
        row = queries.get_document(db, doc_id)
        if row is not None:
            doc_name = row[1]  # filename
    return render_template(
        "chat.html", active_nav="chat", prefill_doc_id=doc_id, prefill_doc_name=doc_name
    )


# -------------------------------------------------------------- json api --

def _row_to_dict(row: tuple, columns: list[str]) -> dict:
    return dict(zip(columns, row))


@app.route("/api/config", methods=["GET"])
def get_config():
    """Expose the handful of settings the frontend needs to render
    correctly (e.g. which fields count as low-confidence) without
    hardcoding them client-side and risking drift from the real gate.
    """
    return jsonify(
        {
            "confidence_threshold": settings.confidence_threshold,
            "allowed_extensions": sorted(_ALLOWED_EXTENSIONS),
        }
    )


@app.route("/api/stats", methods=["GET"])
def get_stats():
    """Dashboard summary numbers: documents processed, high-confidence
    extractions, documents needing review, actions triggered."""
    row = queries.get_stats(db, settings.confidence_threshold)
    cols = ["documents_total", "high_confidence_fields", "needs_review", "actions_triggered"]
    return jsonify(_row_to_dict(row, cols))


@app.route("/api/documents", methods=["GET"])
def list_documents():
    rows = queries.list_documents(db)
    cols = ["doc_id", "filename", "document_type", "vendor", "status", "uploaded_at"]
    return jsonify([_row_to_dict(r, cols) for r in rows])


@app.route("/api/documents/<doc_id>", methods=["GET"])
def get_document(doc_id: str):
    row = queries.get_document(db, doc_id)
    if row is None:
        return jsonify({"error": "not found"}), 404
    cols = ["doc_id", "filename", "document_type", "vendor", "status", "page_count", "uploaded_at"]
    return jsonify(_row_to_dict(row, cols))


@app.route("/api/documents/<doc_id>/fields", methods=["GET"])
def get_fields(doc_id: str):
    rows = queries.get_fields(db, doc_id)
    cols = ["field_id", "field_name", "value", "confidence", "source_agent"]
    return jsonify([_row_to_dict(r, cols) for r in rows])


@app.route("/api/documents/<doc_id>/discrepancies", methods=["GET"])
def get_discrepancies(doc_id: str):
    rows = queries.get_discrepancies_for_document(db, doc_id)
    cols = ["discrepancy_id", "doc_id_1", "doc_id_2", "field_name", "value_1", "value_2", "severity", "status", "explanation"]
    return jsonify([_row_to_dict(r, cols) for r in rows])


@app.route("/api/documents/<doc_id>/audit", methods=["GET"])
def get_audit_timeline(doc_id: str):
    rows = queries.get_audit_timeline(db, doc_id)
    cols = ["log_id", "agent_name", "action", "input_summary", "output_summary", "confidence", "timestamp"]
    return jsonify([_row_to_dict(r, cols) for r in rows])


@app.route("/api/documents/<doc_id>/actions", methods=["GET"])
def get_actions(doc_id: str):
    rows = queries.get_actions_for_document(db, doc_id)
    cols = ["action_id", "discrepancy_id", "action_type", "content", "status", "created_at", "decided_at", "decided_by"]
    return jsonify([_row_to_dict(r, cols) for r in rows])


@app.route("/api/documents/<doc_id>/related", methods=["GET"])
def get_related_documents(doc_id: str):
    """The other documents in this citizen's / vendor's case — e.g. an
    income certificate linked to the welfare application it supports.
    Powers the case-file view so an officer isn't hunting through the
    whole registry to find documents that belong together.
    """
    rows = queries.get_related_documents(db, doc_id)
    cols = ["doc_id", "filename", "document_type", "vendor", "status", "relationship_type", "confidence"]
    return jsonify([_row_to_dict(r, cols) for r in rows])


@app.route("/api/discrepancies/open", methods=["GET"])
def get_open_discrepancies():
    rows = queries.get_open_discrepancies(db)
    cols = ["discrepancy_id", "doc_id_1", "doc_id_2", "field_name", "severity", "status"]
    return jsonify([_row_to_dict(r, cols) for r in rows])


@app.route("/api/documents/upload", methods=["POST"])
def upload_document():
    """Accept a file, run ingestion -> extraction -> relationship linking ->
    confidence gate synchronously, and return the result.

    Synchronous on purpose for the hackathon MVP: judges watching the demo
    should see the pipeline actually run, not poll a job queue. If document
    processing time becomes a problem during the demo, move this to a
    background task and add a /api/documents/<id>/status poll endpoint
    instead of faking progress client-side.
    """
    if "file" not in request.files:
        return jsonify({"error": "no file part named 'file' in request"}), 400
    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "empty filename"}), 400

    filename = secure_filename(file.filename)
    suffix = Path(filename).suffix.lower()
    if suffix not in _ALLOWED_EXTENSIONS:
        return jsonify({"error": f"unsupported file type: {suffix}"}), 400

    os.makedirs(settings.upload_dir, exist_ok=True)
    stored_name = f"{uuid.uuid4()}{suffix}"
    stored_path = os.path.join(settings.upload_dir, stored_name)
    file.save(stored_path)

    uploaded_by = request.form.get("uploaded_by")

    try:
        result = workflow.process_new_document(
            db, settings, file_path=stored_path, filename=filename, uploaded_by=uploaded_by
        )
    except Exception as e:
        return jsonify({"error": f"processing failed: {e}"}), 500

    return jsonify(result), 201


@app.route("/api/documents/<doc_id>/process", methods=["POST"])
def process_document(doc_id: str):
    """Trigger reasoning + action drafting for a document already past the
    confidence gate (status='reasoning'). Ingestion/extraction happen at
    upload time via orchestration.workflow.process_new_document, called
    from wherever file upload is handled (not in this minimal API).
    """
    result = workflow.compare_related_documents(db, settings, doc_id)
    return jsonify(result)


@app.route("/api/reviews", methods=["POST"])
def submit_review():
    body = request.get_json(force=True)
    required = ["doc_id", "field_id", "field_name", "ai_value", "human_value", "status", "reviewed_by"]
    missing = [k for k in required if k not in body]
    if missing:
        return jsonify({"error": f"missing fields: {missing}"}), 400

    review_id = human_review_agent.submit_review(
        db,
        doc_id=body["doc_id"],
        field_id=body["field_id"],
        field_name=body["field_name"],
        ai_value=body["ai_value"],
        human_value=body["human_value"],
        status=body["status"],
        reviewed_by=body["reviewed_by"],
    )
    human_review_agent.advance_if_reviews_complete(db, body["doc_id"], settings.confidence_threshold)
    return jsonify({"review_id": review_id})


@app.route("/api/actions/<action_id>/decide", methods=["POST"])
def decide_action(action_id: str):
    body = request.get_json(force=True)
    decision = body.get("decision")
    decided_by = body.get("decided_by", "unknown")
    if decision not in ("approved", "rejected"):
        return jsonify({"error": "decision must be 'approved' or 'rejected'"}), 400
    action_agent.decide_action(db, action_id, decision, decided_by)
    return jsonify({"action_id": action_id, "status": decision})


@app.route("/api/chat", methods=["POST"])
def chat():
    body = request.get_json(force=True)
    question = body.get("question")
    if not question:
        return jsonify({"error": "missing 'question'"}), 400
    result = chat_agent.ask(db, ro_db, settings, question)
    return jsonify(result)


if __name__ == "__main__":
    app.run(debug=True, port=5005)
