# Agentic Document Intelligence Platform (PS23)

*Exasol AI Build Challenge 2026*

## One-sentence pitch

Most document-intelligence tools stop at "PDF → JSON." This platform goes further: it
extracts structured fields, gates on confidence, *reasons across related documents*
to catch discrepancies, drafts a next action, keeps a human in the loop, and lets
anyone query the accumulated knowledge base in plain English — all backed by Exasol.

## Problem: why extraction alone isn't enough

OCR and field extraction are solved problems — Azure Document Intelligence, Google
Document AI, Amazon Textract, and ABBYY Vantage all do this well. What none of them do
out of the box is *reason across documents that belong to the same case*: an invoice
against its PO and contract, or a citizen's income certificate against their welfare
application. That comparison — and turning it into a concrete, human-approved next
step — is where the real cost sits today. Governments and enterprises run on
documents, but most are effectively unreadable by software because they're
unstructured, scanned, rotated, handwritten, or stamped, so organizations still pay
people to read them and re-type the result. The fuller competitive analysis and
real-world evidence this project drew on (Swedish Land Registry, Telangana High Court,
Indian voter-roll ETL, government health data entry, banking KYC, Maharashtra
municipal corporations) is summarized in the team's ideation notes; write it up as
docs/research-notes.md before submission if judges should see it directly (see
Status below).

## Solution

Extraction + confidence gate + human review + cross-document reasoning + action
proposal + conversational chat, with every step written to an audit log:


User → Frontend → Orchestrator → Ingestion → Extraction → Confidence Gate
                                                  ├─ low  → Human Review → continue
                                                  └─ high → Reasoning
                                                                ├─ no discrepancy → Complete
                                                                └─ discrepancy    → Action → Human Approval

Chat Agent → SQL Validation → Read-only Exasol Query → Answer


Every agent action — extraction, gate decision, reasoning output, action draft,
human override, chat query — is written to AUDIT_LOG. Nothing in this system
should be trusted as "what happened" unless it's traceable back to an audit row.

## Why Exasol

DOC_INTEL is the single system of record for every stage of the pipeline —
documents, extracted fields, relationships, discrepancies, action drafts, human
reviews, and the audit trail all live in one schema, queried by both the
orchestrator and the chat agent. Two separate connection identities (read-write for
agents, read-only for chat — see database/db.py and docs/mcp-grants.sql) let the
same database enforce, at the grant level, that a natural-language question can never
turn into a write, no matter what SQL a model generates. Exasol's speed on ad-hoc
analytical queries is what makes "ask a free-form question over the whole corpus"
(the chat agent) viable without a separate search/analytics stack.

## Demo scenario

One vendor, three related documents: invoice + purchase order + contract, with a
deliberate mismatch (e.g. invoice amount or payment terms).

| Step | What judges see |
|---|---|
| 1. Upload | Three related documents appear in the dashboard |
| 2. Extract | Fields and confidence scores appear |
| 3. Confidence | A low-confidence field pauses for human review |
| 4. Reason | Invoice/PO/contract values are compared and the mismatch is highlighted |
| 5. Act | Email draft + task proposal are generated (never auto-sent) |
| 6. Audit | Timeline shows extraction → decision → reasoning → action |
| 7. Chat | A natural-language question ("Which vendors have unresolved discrepancies this month?") returns an Exasol-backed answer |

## Tech stack

Python (Flask API), pyexasol, Claude (extraction / reasoning / chat, tool-use forced
calls), Tesseract + pdf2image/pypdf for ingestion/OCR, Exasol Personal Local as the
database, pytest for the test suite.

## Repository structure


exasol/
├── README.md
├── schema.sql                  # DOC_INTEL schema
├── main.py                     # wiring/connectivity entry point
├── config.py
├── agents/                     # one module per agent
│   ├── ingestion.py
│   ├── extraction.py
│   ├── confidence.py
│   ├── human_review.py
│   ├── relationships.py
│   ├── reasoning.py
│   ├── action.py
│   └── chat.py
├── orchestration/               # state machine + workflow driver
│   ├── state.py
│   └── workflow.py
├── database/                    # connections, audit logger
│   ├── db.py
│   ├── queries.py
│   └── audit.py
├── models/
│   └── document.py
├── api/
│   └── routes.py                # Flask endpoints
├── data/
│   ├── sample/                  # demo documents (invoices/, purchase_orders/, contracts/, forms/)
│   └── datasets/                # downloaded public datasets (git-ignored, see docs/datasets.md)
├── scripts/
│   ├── download_datasets.py     # fetch FUNSD / CORD / RVL-CDIP / DocVQA
│   ├── prepare_sample_data.py   # stage a subset into data/sample/
│   └── requirements-datasets.txt
├── docs/
│   ├── mcp-grants.sql
│   └── datasets.md
└── tests/


## Prerequisites

- Python 3.11+
- tesseract-ocr and poppler-utils (system packages, for OCR/PDF rasterization)
- An Exasol Personal Local instance (via the starter kit below)
- An Anthropic API key

## Installation & configuration

### 1. Install the Exasol Personal Local starter kit

bash
curl -fsSL https://raw.githubusercontent.com/exasol-labs/exasol-personal-local-starterkit/main/install.sh | sh
exakit status      # wait for "running"
exakit info        # connection details


### 2. Load the schema

bash
exapump sql -p starter-kit -f schema.sql
exapump sql -p starter-kit -f docs/mcp-grants.sql


### 3. Configure the app

bash
cp .env.example .env
# fill in EXASOL_PASSWORD, EXASOL_RO_USER/PASSWORD (from `exakit info`), ANTHROPIC_API_KEY


### 4. Install dependencies

*System packages (OCR engine + PDF rasterizer):*

bash
sudo apt-get install -y tesseract-ocr poppler-utils


*Python packages:*

bash
pip install -r requirements.txt --break-system-packages   # or use a venv


### 5. Verify the wiring

bash
python main.py


Expected output: read-write connection confirmed, read-only connection
confirmed, DOCUMENTS row count printed.

## How to run

bash
# API server
python -m api.routes            # or: flask --app api.routes run

# test suite
pytest


POST /api/documents/upload runs the full ingest → extract → link → confidence-gate
pipeline synchronously, so a demo shows real processing rather than a spinner. See
api/routes.py for the full endpoint list (documents, fields, discrepancies, audit
timeline, review submission, action approval, chat).

## How to run the demo

1. Drop the three sample documents (or your own invoice/PO/contract) into the upload
   endpoint/UI — see data/sample/ and docs/datasets.md for where to get realistic
   sample documents if you haven't authored your own yet.
2. Watch extraction populate fields with confidence scores; confirm/correct anything
   routed to human review.
3. Once all three documents are linked, the reasoning agent flags the mismatch as a
   DISCREPANCIES row.
4. Approve or reject the drafted email/task in ACTIONS.
5. Open the audit timeline for that document to see every step, in order.
6. Ask the chat agent a natural-language question over the whole corpus.

## Datasets for a bigger/more varied demo corpus

Beyond the three authored invoice/PO/contract files, scripts/download_datasets.py
can pull in public document-intelligence datasets (FUNSD, CORD, RVL-CDIP, DocVQA) that
were scouted during ideation, and scripts/prepare_sample_data.py stages a subset of
them into data/sample/. **Full details, licenses, and setup are in
[docs/datasets.md](docs/datasets.md)** — short version:

bash
pip install -r scripts/requirements-datasets.txt --break-system-packages
python scripts/download_datasets.py --dataset funsd
python scripts/download_datasets.py --dataset cord --cord-samples 30
python scripts/prepare_sample_data.py


This repo was assembled in a network-sandboxed environment, so the actual dataset
files (hosted on GitHub Pages, Hugging Face, and Kaggle — none of which were reachable
from that sandbox) are *not* checked in; run the two commands above on a normal
machine to populate data/datasets/ and data/sample/ yourself.

## Reliability and safety rules this project follows

- Chat-generated SQL is read-only and runs under a dedicated Exasol identity
  with SELECT-only grants on DOC_INTEL — enforced at the database level,
  not just by prompting (docs/mcp-grants.sql).
- agents/chat.py also validates that the model produced exactly one SELECT
  statement before it's ever executed, as a second line of defense.
- No email is sent automatically; agents/action.py only ever produces a
  draft that a human approves via ACTIONS.status.
- Confidence routing (agents/confidence.py) is deterministic application
  code, not a second model call.
- .env is git-ignored; only .env.example (names, no values) is committed.
- Structured model output (extraction, reasoning, chat SQL) is produced via forced
  tool-use calls and validated before any database write.
- Use synthetic/sample documents unless redistribution rights are clear (see
  docs/datasets.md for per-dataset license notes).

## Status

*Built and tested:*
- Schema, config, DB layer (read-write + read-only identities), audit logger, typed models, state machine
- agents/ingestion.py — native PDF text layer used directly when present; scanned PDFs (no text layer) and image uploads fall back to Tesseract OCR, with the average word-confidence recorded in AUDIT_LOG and a separate low-confidence warning logged below 60% so a poor scan is distinguishable from genuine field ambiguity later in the pipeline. Verified against real generated files (native-text PDF, image-only PDF, plain image), not mocked.
- agents/extraction.py — Claude tool-use call (forced tool_choice) that returns structured fields + confidence, persisted to EXTRACTED_FIELDS
- agents/confidence.py — deterministic gate (no model call), routes to review or reasoning
- agents/human_review.py — records corrections/approvals, advances the document once all low-confidence fields are resolved
- agents/reasoning.py — cross-document comparison producing structured DISCREPANCIES, not prose
- agents/action.py — drafts email + task proposals per discrepancy; never sends anything, only writes status='proposed' rows for human approval
- agents/chat.py — NL → SQL with a forced tool call, a hard-coded schema description (no guessed columns), and validate_sql() as a second line of defense in front of the read-only DB identity
- agents/relationships.py — links documents into the same case: a free deterministic rule pass (same vendor + a known compatible type pair, e.g. invoice↔️purchase_order) runs first, with a bounded Claude fallback only for vendor-matched pairs whose document types aren't in the known list yet
- orchestration/workflow.py — drives ingest → extract → link relationships → confidence gate and, separately, reasoning → action → complete for a document once unblocked
- api/routes.py — Flask endpoints for upload, documents, fields, discrepancies, audit timeline, review submission, action approval, and chat. /api/documents/upload runs the full ingest→extract→link→gate pipeline synchronously so a demo shows real processing, not a spinner
- tests/ — 28 passing unit tests covering the confidence gate, state-machine transitions, SQL validation, relationship rule-matching, and OCR ingestion (all run without a live Exasol connection or API key; the OCR tests generate real image/PDF fixtures on the fly and run actual Tesseract on them)
- scripts/download_datasets.py, scripts/prepare_sample_data.py, docs/datasets.md — dataset-integration tooling (see above); fetch logic is written and tested for graceful failure, but has not been run to completion end-to-end since the datasets' hosts aren't reachable from this build environment

*Not yet built:* frontend/; the three authored invoice/PO/contract sample documents for data/sample/; RVL-CDIP/DocVQA staging into data/sample/ (fetch-only for now — see docs/datasets.md); docs/architecture.md, docs/demo-script.md, and docs/research-notes.md (referenced above as the natural home for the architecture diagram, demo script, and competitive-analysis writeup, but not yet written).

*Known limitation:* relationship linking only runs once, right after a document's own extraction. If document A finishes with no relationships (nothing to link to yet) and document B is uploaded later and links back to A, A itself is not re-queued into reasoning — only B proceeds to compare against A. For the demo (all three related documents uploaded in one sitting) this doesn't bite, but a production version needs a "wake up documents that just gained a relationship" step in orchestration/workflow.py.

Run pytest from the project root to run the test suite.

## Future work

- Frontend dashboard (upload, review queue, discrepancy view, audit timeline, chat)
- Re-queue documents that gain a relationship after their own extraction already completed (see Known limitation above)
- Contract comparison as a third leg of reasoning (invoice/PO is the MVP pair)
- Semantic retrieval alongside SQL for less structured questions
- RVL-CDIP-based document-type pre-classification before extraction
- Stage RVL-CDIP/DocVQA into data/sample/ once a mapping onto EXTRACTED_FIELDS/DISCREPANCIES is defined

## Team

Four-way split (definitions of done belong in docs/architecture.md once written —
see Status above): Extraction · Data (Exasol schema/audit) · Orchestration
(reasoning/action/chat) · Frontend/Demo.
