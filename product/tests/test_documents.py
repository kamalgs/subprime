"""Unit tests for subprime.data.documents — staging, password flow, classifier."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from subprime.data import documents


@pytest.fixture(autouse=True)
def _reset_store():
    documents._store.clear()
    yield
    documents._store.clear()


def _make_pdf(text: str, password: str | None = None) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setFont("Helvetica", 12)
    for i, line in enumerate(text.splitlines()):
        c.drawString(100, 800 - i * 18, line)
    c.save()
    buf.seek(0)

    if not password:
        return buf.getvalue()

    reader = PdfReader(buf)
    writer = PdfWriter()
    for p in reader.pages:
        writer.add_page(p)
    writer.encrypt(user_password=password, owner_password=password, algorithm="AES-128")
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def test_stage_unprotected_pdf_is_verified_immediately() -> None:
    pdf = _make_pdf("Consolidated Account Statement\nCAMS Mutual Fund Services")
    doc = documents.stage("sess1", "summary.pdf", pdf)
    assert doc.verified is True
    assert doc.requires_password is False
    assert doc.detected_type == "cas"


def test_stage_encrypted_pdf_sets_requires_password() -> None:
    pdf = _make_pdf("CIBIL TRANSUNION SCORE\nYour Score", password="secret")
    doc = documents.stage("sess2", "cibil.pdf", pdf)
    assert doc.requires_password is True
    assert doc.verified is False
    assert doc.detected_type == "unknown"  # can't classify until unlocked


def test_apply_password_unlocks_and_classifies() -> None:
    pdf = _make_pdf("CIBIL TRANSUNION SCORE\nYour Score", password="secret")
    doc = documents.stage("sess3", "cibil.pdf", pdf)
    updated = documents.apply_password("sess3", doc.doc_id, "secret")
    assert updated.verified is True
    assert updated.detected_type == "cibil"


def test_apply_password_rejects_wrong_password() -> None:
    pdf = _make_pdf("CIBIL TRANSUNION SCORE", password="right")
    doc = documents.stage("sess4", "x.pdf", pdf)
    with pytest.raises(ValueError, match="Incorrect password"):
        documents.apply_password("sess4", doc.doc_id, "wrong")


def test_apply_password_raises_on_unknown_doc() -> None:
    with pytest.raises(KeyError):
        documents.apply_password("nope", "missing", "")


def test_classify_unknown_for_generic_pdf() -> None:
    pdf = _make_pdf("Some unrelated invoice")
    doc = documents.stage("sess5", "invoice.pdf", pdf)
    assert doc.detected_type == "unknown"


def test_stage_enforces_per_session_cap() -> None:
    pdf = _make_pdf("test")
    for i in range(documents._MAX_DOCS_PER_SESSION):
        documents.stage("sess6", f"{i}.pdf", pdf)
    with pytest.raises(ValueError, match="Max"):
        documents.stage("sess6", "overflow.pdf", pdf)


def test_stage_enforces_size_cap() -> None:
    big = b"\x00" * (documents._MAX_BYTES + 1)
    with pytest.raises(ValueError, match="larger than"):
        documents.stage("sess7", "big.pdf", big)


def test_extract_all_runs_real_parsers() -> None:
    """End-to-end: stage a dummy CAS fixture, unlock it, extract."""
    fixture = Path(__file__).parent / "fixtures" / "dummy_cas.pdf"
    doc = documents.stage("sess8", "cas.pdf", fixture.read_bytes())
    assert doc.requires_password is True
    # dummy_cas fixture uses password TESTPASS12
    documents.apply_password("sess8", doc.doc_id, "TESTPASS12")
    result = documents.extract_all("sess8")
    # The dummy CAS isn't a real CAMS layout so parsing will either
    # produce no holdings or land in skipped — the important thing is
    # that extract_all runs without raising and returns the expected
    # top-level shape.
    assert "holdings" in result
    assert "credit_summary" in result
    assert "skipped" in result
