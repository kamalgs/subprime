"""Tests for the AIS parser.

Text-based unit tests against synthetic blocks that mirror the two
layouts pdfminer emits on real AIS PDFs. Real AIS PDFs contain full
PII and aren't committed.
"""

from __future__ import annotations

import pytest

from subprime.data.ais import AISParseError, _classify, parse_ais


def test_classify_routes_common_descriptions() -> None:
    assert _classify("Salary received (Section 192)") == "total_salary_inr"
    assert _classify("Dividend received (Section 194)") == "total_dividend_inr"
    assert _classify("Sale of unit of equity oriented mutual fund") == "total_sale_of_mf_inr"
    assert _classify("Sale of listed equity share (Depository)") == "total_sale_of_securities_inr"
    assert _classify("Interest from savings bank") == "total_interest_inr"
    assert _classify("Unknown thing") is None


def test_parse_ais_rejects_non_ais_bytes() -> None:
    with pytest.raises(AISParseError):
        parse_ais(b"not a pdf", "")


def test_parse_ais_rejects_pdf_without_ais_header(tmp_path) -> None:
    """A valid PDF that isn't an AIS should error cleanly."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    pdf = tmp_path / "other.pdf"
    c = canvas.Canvas(str(pdf), pagesize=A4)
    c.drawString(100, 800, "Not an AIS, just a receipt")
    c.save()
    with pytest.raises(AISParseError):
        parse_ais(pdf.read_bytes(), "")
