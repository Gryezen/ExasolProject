# Simulated dashboard-upload dataset (v2 — messy/prose + noise)

50 synthetic "case folders" (`uploads/case_0001/` … `uploads/case_0050/`), each modeling
one citizen/vendor upload session to the dashboard, containing 2-5 related documents
drawn from: birth certificates, land records, tax forms (income certificate / property
tax / GST invoice), legal notices, contracts, identity documents, applications, and
scanned handwritten forms.

## What changed from v1

- **No more clean key-value tables.** Every document is written as dense, justified,
  multi-paragraph bureaucratic/legal prose — field values (names, dates, amounts, IDs)
  are buried mid-sentence, the way a real government extract, receipt, or notice reads,
  not spoon-fed to an extraction model.
- **Longer.** Each document runs 4-8 paragraphs (roughly 350-700 words), padded with
  realistic filler paragraphs, not just the bare facts.
- **~10% of each document's fields are wrong.** A typo, a transposed digit, an
  OCR-style character swap (O↔0, l↔1, S↔5, B↔8), a swapped day/month, or a currency
  slip (extra/missing digit) — applied per document, independent of every other
  document in the case. Because most documents only carry 4-8 fields, "10%" rounds up
  to a guaranteed minimum of one wrong field per document, so actual overall corruption
  lands around 15-20% of fields — every document has at least one error, some have two.
- Formats: PDF (~74%) and plain text (~26%), still entirely digital, no images/scans
  of the traditional kind.

## Ground truth

`manifest.json` records, for every field in every document: `correct_value` (what the
entity's true data is) vs. `displayed_value` (what's actually written in the file) vs.
`is_corrupted` (bool). This is what you diff your extraction agent's output against to
measure field-level accuracy — including whether it flags/gets fooled by the
intentionally-corrupted ~10-20%.

Separately, `has_intentional_cross_document_discrepancy` / `cross_document_discrepancy`
(4 of the 50 cases) marks a *larger*, deliberate mismatch between two documents in the
same case (e.g. declared income vs. income certificate, or invoice total vs. contract
value) — this is a different, bigger signal meant for the reasoning agent to catch, not
the small per-document typo noise above.

`manifest.csv` gives a flat per-case summary (scenario, file list, field/corruption
counts) for quick spreadsheet browsing.

## Regenerate or resize

```bash
pip install faker reportlab --break-system-packages
python generate_simulated_dataset.py --n-cases 50 --output-dir ./simulated_dataset --seed 42 --corrupt-rate 0.10
```

`--corrupt-rate` controls the per-document corruption target (default 0.10 = 10%).
Documents are longer than v1's table-based files, so file counts were dropped from 100
to 50 cases to keep total corpus size reasonable (~1.2 MB / 168 files at this size).

## Using it with the platform

Point the platform's ingestion at this corpus by copying `uploads/` into the app's
configured `UPLOAD_DIR` (see `.env` / `config.py` — `upload_dir`, default
`./data/uploads`), or feed each case's files through `POST /api/documents/upload` in a
loop. Because the values are now embedded in prose rather than tables, this corpus is a
much closer stress test of `agents/extraction.py`'s ability to actually read a document,
and the per-field ground truth in `manifest.json` lets you score it automatically.
