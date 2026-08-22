"""
tests/test_ingestion.py — exercises the three real ingestion paths against
files generated on the fly: a native-text PDF, a scanned (image-only) PDF,
and a plain image. No live Exasol connection needed since these tests call
the pure text-extraction helpers directly, not ingest_document() (which
writes to DOCUMENTS/AUDIT_LOG).

Requires the system `tesseract` binary and poppler's `pdftoppm` to be
installed (see README setup step 4b) — these tests are skipped if either
is missing rather than failing the whole suite in an environment that
hasn't installed them yet.
"""

import shutil
from pathlib import Path

import pytest

pytesseract = pytest.importorskip("pytesseract")
pdf2image = pytest.importorskip("pdf2image")

from agents.ingestion import _extract_image_text, _extract_pdf_text, ingest_document  # noqa: E402

_TESSERACT_AVAILABLE = shutil.which("tesseract") is not None
_POPPLER_AVAILABLE = shutil.which("pdftoppm") is not None

pytestmark = pytest.mark.skipif(
    not (_TESSERACT_AVAILABLE and _POPPLER_AVAILABLE),
    reason="tesseract and/or poppler-utils not installed on this system",
)


@pytest.fixture
def sample_image(tmp_path) -> Path:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (600, 200), color="white")
    draw = ImageDraw.Draw(img)
    draw.text((20, 20), "INVOICE 4471", fill="black")
    draw.text((20, 60), "Vendor Acme Supplies", fill="black")
    path = tmp_path / "sample.png"
    img.save(path)
    return path


@pytest.fixture
def scanned_pdf(sample_image, tmp_path) -> Path:
    import img2pdf

    path = tmp_path / "scanned.pdf"
    path.write_bytes(img2pdf.convert(str(sample_image)))
    return path


@pytest.fixture
def native_pdf(tmp_path) -> Path:
    from reportlab.pdfgen import canvas

    path = tmp_path / "native.pdf"
    c = canvas.Canvas(str(path))
    c.drawString(50, 750, "Purchase Order PO-9982")
    c.drawString(50, 730, "Vendor Acme Supplies")
    c.save()
    return path


def test_image_ocr_extracts_text_and_confidence(sample_image):
    text, confidence = _extract_image_text(sample_image)
    # Assert on "Vendor" and "4471" rather than "Acme": real OCR can
    # misread a character or two ("Acme" -> "Aeme") even on clean synthetic
    # text, and that noise is exactly what the extraction agent's
    # per-field confidence scoring exists to flag downstream — this
    # ingestion test only needs to prove OCR ran and produced something
    # in the right ballpark, not that it was pixel-perfect.
    assert "Vendor" in text
    assert "4471" in text
    assert confidence is not None
    assert 0 <= confidence <= 100


def test_scanned_pdf_falls_back_to_ocr(scanned_pdf):
    text, page_count, confidence = _extract_pdf_text(scanned_pdf)
    assert page_count == 1
    assert "Vendor" in text
    assert "4471" in text
    assert confidence is not None  # OCR fallback should have fired


def test_native_pdf_skips_ocr(native_pdf):
    text, page_count, confidence = _extract_pdf_text(native_pdf)
    assert page_count == 1
    assert "Purchase Order" in text  # native text layer is exact, no OCR noise expected
    assert confidence is None  # native text layer present, OCR never runs


class _FakeDatabase:
    """Enough of Database to drive ingest_document() end to end: records
    every execute() call instead of touching a real Exasol connection.
    """

    def __init__(self):
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))


def test_txt_upload_skips_ocr_like_a_native_pdf(tmp_path):
    # Plain-text uploads (e.g. the .txt files in a realistic mixed-format
    # case corpus) should be read directly, with no OCR confidence at all
    # — same treatment as a PDF that already has a text layer.
    path = tmp_path / "identity_document.txt"
    path.write_text("Reference No: ID-0022\nName: Aryan Maharaj\n", encoding="utf-8")

    db = _FakeDatabase()
    result = ingest_document(db, str(path), filename="identity_document.txt")

    assert "Aryan Maharaj" in result.text
    assert result.page_count == 1
    assert result.ocr_confidence is None

    insert_calls = [p for sql, p in db.calls if "INSERT INTO DOCUMENTS" in sql]
    assert len(insert_calls) == 1
    assert insert_calls[0]["filename"] == "identity_document.txt"

    audit_actions = [p["action"] for _, p in db.calls if p and "action" in p]
    assert "ingested_document" in audit_actions
    assert "low_quality_scan_warning" not in audit_actions  # no OCR ran, nothing to warn about
