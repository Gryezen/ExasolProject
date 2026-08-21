# Agentic Document Intelligence Platform (PS23)

**Exasol AI Build Challenge 2026**

## One-sentence pitch

Most document-intelligence tools stop at "PDF → JSON." This platform goes further: it
extracts structured fields, gates on confidence, **reasons across related documents**
to catch discrepancies, drafts a next action, keeps a human in the loop, and lets
anyone query the accumulated knowledge base in plain English — all backed by Exasol.

## Why this problem still exists

OCR and field extraction are solved problems (Azure Document Intelligence, Google
Document AI, Amazon Textract, ABBYY Vantage). What none of them do out of the box is
**reason across documents that belong to the same case** — e.g. an invoice, its PO,
and its contract, or a citizen's income certificate against their welfare application
— and turn that reasoning into a concrete next step a human can approve. That's the
gap this project targets. See `docs/research-notes.md` for the fuller competitive
analysis and real-world evidence (Swedish Land Registry, Telangana High Court, Indian
voter-roll ETL, government health data entry, banking KYC, Maharashtra municipal
corporations).

## Architecture

```
User → Frontend → Orchestrator → Ingestion → Extraction → Confidence Gate
                                                  ├─ low  → Human Review → continue
                                                  └─ high → Reasoning
                                                                ├─ no discrepancy → Complete
                                                                └─ discrepancy    → Action → Human Approval

Chat Agent → SQL Validation → Read-only Exasol Query → Answer
```

Every agent action — extraction, gate decision, reasoning output, action draft,
human override, chat query — is written to `AUDIT_LOG`. Nothing in this system
should be trusted as "what happened" unless it's traceable back to an audit row.

## Components

| Component | Responsibility |
|---|---|
| `agents/ingestion.py` | Normalize PDF/image/scanned input into text + metadata |
| `agents/extraction.py` | Extract structured fields + confidence per field |
| `agents/confidence.py` | Deterministic routing: below threshold → human review |
| `agents/reasoning.py` | Compare related documents, produce structured discrepancies |
| `agents/action.py` | Draft an email/task proposal for a discrepancy (never auto-sent) |
| `agents/chat.py` | Natural language → validated read-only SQL → Exasol → explanation |
| `database/db.py` | Two connection identities: read-write (agents) and read-only (chat) |
| `database/audit.py` | Single place every agent logs an explainable event |
| `orchestration/state.py` | Legal state transitions for a document's lifecycle |
| `orchestration/workflow.py` | Drives the loop above, calling agents between transitions |

Agents that don't exist yet are intentionally not stubbed with fake logic — see
**Status** below.

## Database (Exasol, schema `DOC_INTEL`)

`schema.sql` defines: `DOCUMENTS`, `EXTRACTED_FIELDS`, `DOCUMENT_RELATIONSHIPS`,
`DISCREPANCIES`, `ACTIONS`, `HUMAN_REVIEWS`, `AUDIT_LOG`. `docs/mcp-grants.sql`
documents the read-only grant used by both the chat agent and the starter kit's
own MCP server, so a bad or injected query is rejected by Exasol's grants, not
just by application-level SQL validation.

## Setup

### 1. Install the Exasol Personal Local starter kit

```bash
curl -fsSL https://raw.githubusercontent.com/exasol-labs/exasol-personal-local-starterkit/main/install.sh | sh
exakit status      # wait for "running"
exakit info        # connection details
```

### 2. Load the schema

```bash
exapump sql -p starter-kit -f schema.sql
exapump sql -p starter-kit -f docs/mcp-grants.sql
```

### 3. Configure the app

```bash
cp .env.example .env
# fill in EXASOL_PASSWORD, EXASOL_RO_USER/PASSWORD (from `exakit info`), ANTHROPIC_API_KEY
```

### 4. Install dependencies

**4a. System packages (OCR engine + PDF rasterizer):**

```bash
sudo apt-get install -y tesseract-ocr poppler-utils
```

**4b. Python packages:**

```bash
pip install -r requirements.txt --break-system-packages   # or use a venv
```

### 5. Verify the wiring

```bash
python main.py
```

Expected output: read-write connection confirmed, read-only connection
confirmed, `DOCUMENTS` row count printed.

## Reliability rules this project follows

- Chat-generated SQL is read-only and runs under a dedicated Exasol identity
  with `SELECT`-only grants on `DOC_INTEL` — enforced at the database level,
  not just by prompting.
- No email is sent automatically; `agents/action.py` only ever produces a
  draft that a human approves via `ACTIONS.status`.
- Confidence routing (`agents/confidence.py`) is deterministic application
  code, not a second model call.
- `.env` is git-ignored; only `.env.example` (names, no values) is committed.

## Status

**Built and tested:**
- Schema, config, DB layer (read-write + read-only identities), audit logger, typed models, state machine
- `agents/ingestion.py` — native PDF text layer used directly when present; scanned PDFs (no text layer) and image uploads fall back to Tesseract OCR, with the average word-confidence recorded in `AUDIT_LOG` and a separate low-confidence warning logged below 60% so a poor scan is distinguishable from genuine field ambiguity later in the pipeline. Verified against real generated files (native-text PDF, image-only PDF, plain image), not mocked.
- `agents/extraction.py` — Claude tool-use call (forced `tool_choice`) that returns structured fields + confidence, persisted to `EXTRACTED_FIELDS`
- `agents/confidence.py` — deterministic gate (no model call), routes to `review` or `reasoning`
- `agents/human_review.py` — records corrections/approvals, advances the document once all low-confidence fields are resolved
- `agents/reasoning.py` — cross-document comparison producing structured `DISCREPANCIES`, not prose
- `agents/action.py` — drafts email + task proposals per discrepancy; never sends anything, only writes `status='proposed'` rows for human approval
- `agents/chat.py` — NL → SQL with a forced tool call, a hard-coded schema description (no guessed columns), and `validate_sql()` as a second line of defense in front of the read-only DB identity
- `agents/relationships.py` — links documents into the same case: a free deterministic rule pass (same vendor + a known compatible type pair, e.g. invoice↔purchase_order) runs first, with a bounded Claude fallback only for vendor-matched pairs whose document types aren't in the known list yet
- `orchestration/workflow.py` — drives `ingest → extract → link relationships → confidence gate` and, separately, `reasoning → action → complete` for a document once unblocked
- `api/routes.py` — Flask endpoints for upload, documents, fields, discrepancies, audit timeline, review submission, action approval, and chat. `/api/documents/upload` runs the full ingest→extract→link→gate pipeline synchronously so a demo shows real processing, not a spinner
- `tests/` — 28 passing unit tests covering the confidence gate, state-machine transitions, SQL validation, relationship rule-matching, and OCR ingestion (all run without a live Exasol connection or API key; the OCR tests generate real image/PDF fixtures on the fly and run actual Tesseract on them)

**Not yet built:** `frontend/`, sample data in `data/sample/`.

**Known limitation:** relationship linking only runs once, right after a document's own extraction. If document A finishes with no relationships (nothing to link to yet) and document B is uploaded later and links back to A, A itself is not re-queued into reasoning — only B proceeds to compare against A. For the demo (all three related documents uploaded in one sitting) this doesn't bite, but a production version needs a "wake up documents that just gained a relationship" step in `orchestration/workflow.py`.

Run `pytest` from the project root to run the test suite.

## Team

Four-way split (see `docs/architecture.md` for definitions of done):
Extraction · Data (Exasol schema/audit) · Orchestration (reasoning/action/chat) ·
Frontend/Demo.
