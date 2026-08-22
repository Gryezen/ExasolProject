# Sample document corpus

Everything under this directory is **synthetic** — generated locally by
[`scripts/generate_sample_documents.py`](../../scripts/generate_sample_documents.py),
not sourced from any real citizen, real government record, or external
dataset. It's safe to commit and safe to redistribute.

## Why not a real dataset (FUNSD / CORD / RVL-CDIP / data.gov.in)?

We looked. None of them work for this project:

- **FUNSD**'s actual image/annotation data is hosted at
  `guillaumejaume.github.io/FUNSD/dataset.zip`, and its license is
  non-commercial/research-only — a bad fit for a redistributable
  submission repo even where the host is reachable. Its GitHub repo
  ([crcresearch/FUNSD](https://github.com/crcresearch/FUNSD)) is
  documentation only; the real files live behind DVC / that external
  host.
- **CORD**'s GitHub repo ([clovaai/cord](https://github.com/clovaai/cord))
  is likewise documentation-only (checked via the GitHub API — the repo
  is 711 KB and contains a README, a license file, and one figure). The
  actual ~11,000 receipt images live on Hugging Face.
- **RVL-CDIP** is distributed only via Kaggle.
- **data.gov.in** (India's Open Government Data Platform) is its own
  host, separate from all of the above.
- Content mismatch, independent of hosting: FUNSD is 1980s-90s US
  tobacco-industry forms, CORD is Indonesian retail receipts. Neither
  contains anything resembling a birth certificate, income certificate,
  or land record, so even a successful download wouldn't exercise this
  project's actual extraction schema.

## What's here instead

Seven document types, matching the types this project's extraction
schema and rule-based relationship matcher already know about (see
`agents/extraction.py`, `agents/relationships.py`):

| Type | Count | Linked to |
|---|---|---|
| `birth_certificate/` | 6 | — |
| `income_certificate/` | 6 | `welfare_application` (income mismatch demo) |
| `welfare_application/` | 6 | `income_certificate` |
| `land_record/` | 6 | `property_tax_receipt` (same owner) |
| `property_tax_receipt/` | 6 | `land_record` |
| `complaint/` | 6 | — |
| `contractor_bid/` | 6 | — |

**`MANIFEST.txt`** lists the ground-truth field values used to render
every document — use it to check extraction accuracy during a demo
without re-reading each image by eye.

**Two of the six income-certificate/welfare-application pairs are
deliberately inconsistent** (the welfare application declares 3-4x the
income on the certificate) — these are tagged
`[DELIBERATE MISMATCH vs income_certificate]` in the manifest, and are
what the reasoning agent should catch and the action agent should draft
a clarification for. The rest are consistent, so not every pair should
trigger a discrepancy.

**Messiness is deliberate, not random noise.** Each category cycles
through: clean, clean, stamped (a "VERIFIED" or "PENDING" seal),
noisy (a stamp plus slight blur), and one genuinely degraded
phone-photo-style scan (rotated a few degrees, blurred, and
downsampled/upsampled to simulate re-compression). Verified with real
Tesseract OCR during generation: clean documents extract at roughly
89-92% word confidence; the degraded variant drops to ~76% and produces
real character-level OCR errors (e.g. "Nair" → "Mair"), which is exactly
what should trip the confidence gate into `HUMAN_REVIEW`.

## Regenerating / scaling up

```bash
pip install -r requirements.txt  # PIL is already a dependency
python3 scripts/generate_sample_documents.py --count-per-type 25 --seed 42
```

The ideation notes for this project suggested ~25 documents per category
(175 total) as a good target for a 48-hour hackathon corpus — the
default here is 6 per category to keep the committed repo small; bump
`--count-per-type` for a bigger demo corpus. Regenerating is
non-destructive to anything outside this directory and safe to re-run —
it only overwrites its own prior output.
