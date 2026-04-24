"""AIS (Annual Information Statement) PDF parser.

The AIS is the Income Tax Department's consolidated view of every
financial transaction reported against a PAN — salary, dividends,
interest, capital gains, property / vehicle purchases, foreign
remittances, cash deposits, TDS/TCS. Users download it from
incometax.gov.in → Services → AIS (PDF or JSON). Password, when set,
is PAN in lowercase + DOB as DDMMYYYY.

pdfminer emits the AIS text with interleaved column layout — category
labels end up in one vertical column and values in another. Rather
than try to reconstruct the table layout, this parser extracts
``(INFORMATION DESCRIPTION, INFORMATION SOURCE, COUNT, AMOUNT)``
triples globally and classifies each by matching the description
against known section keywords.

Dividend entries are reported per-company without a pre-summed
``AMOUNT`` header, so dividend income extraction is best-effort from
the per-row values.
"""

from __future__ import annotations

import logging
import re

from subprime.core.models import AISSummary

logger = logging.getLogger(__name__)


class AISParseError(Exception):
    """Not an AIS PDF, bad password, or a layout we don't recognise."""


# Classification — map the "INFORMATION DESCRIPTION" text to one of our
# summary fields. First-substring match wins, so order matters: put the
# more specific matches before generic ones.
_DESCRIPTION_TO_FIELD: list[tuple[str, str]] = [
    ("salary received", "total_salary_inr"),
    # MF sales — match before generic "sale of" rules so "units of equity
    # oriented mutual fund" routes to MF, not securities.
    ("sale of unit of equity oriented mutual fund", "total_sale_of_mf_inr"),
    ("sale of units of mutual fund", "total_sale_of_mf_inr"),
    ("sale of other unit", "total_sale_of_mf_inr"),
    ("purchase of unit of equity oriented mutual fund", "total_purchase_of_mf_inr"),
    ("purchase of units of mutual fund", "total_purchase_of_mf_inr"),
    ("sale of listed equity", "total_sale_of_securities_inr"),
    ("sale of securities", "total_sale_of_securities_inr"),
    ("purchase of securities", "total_purchase_of_securities_inr"),
    ("dividend received", "total_dividend_inr"),
    ("income received in respect of units of mutual fund", "total_dividend_inr"),
    ("interest received on securities", "total_interest_inr"),
    ("interest from savings bank", "total_interest_inr"),
    ("interest from deposit", "total_interest_inr"),
    ("interest from others", "total_interest_inr"),
    ("interest income", "total_interest_inr"),
]


# Two layouts exist in the same document depending on section:
#   A. interleaved: DESC\n<desc>\nSOURCE\n<source>\nCOUNT\n<n>\nAMOUNT\n<amt>
#   B. grouped:    DESC\nSOURCE\n<desc>\n<source>\nCOUNT\n<n>\nAMOUNT\n<amt>
_TRIPLE_A_RE = re.compile(
    r"INFORMATION DESCRIPTION\s*\n+([^\n]+?)\s*\n+"
    r"INFORMATION SOURCE\s*\n+(.{1,200}?)\s*\n+"
    r"COUNT\s*\n+(\d+)\s*\n+AMOUNT\s*\n+([\d,]+(?:\.\d+)?)",
    re.DOTALL,
)
_TRIPLE_B_RE = re.compile(
    r"INFORMATION DESCRIPTION\s*\n+INFORMATION SOURCE\s*\n+"
    r"([^\n]+?)\s*\n+(.{1,200}?)\s*\n+"
    r"COUNT\s*\n+(\d+)\s*\n+AMOUNT\s*\n+([\d,]+(?:\.\d+)?)",
    re.DOTALL,
)


def _parse_inr(s: str) -> int:
    if not s or s == "-":
        return 0
    try:
        return int(float(s.replace(",", "")))
    except ValueError:
        return 0


def _extract_text(pdf_bytes: bytes, password: str) -> str:
    import tempfile
    from pathlib import Path

    from pdfminer.high_level import extract_text

    with tempfile.NamedTemporaryFile(prefix="subprime-", suffix=".pdf", delete=True) as tmp:
        tmp.write(pdf_bytes)
        tmp.flush()
        try:
            return extract_text(str(Path(tmp.name)), password=password)
        except Exception as e:
            raise AISParseError(f"PDF read failed: {e}") from e


def _classify(description: str) -> str | None:
    """Return the AISSummary field name for a description, or None."""
    dl = description.lower()
    for needle, field in _DESCRIPTION_TO_FIELD:
        if needle in dl:
            return field
    return None


def _sum_dividends_by_line(text: str) -> int:
    """Dividends have per-row entries without a COUNT/AMOUNT header.

    Each ``Dividend received (Section 194)`` block has a column of dates
    followed by a column of amounts. Rather than recover column order,
    sum all standalone numeric lines within a narrow window after each
    Dividend source. Inexact — will miss multi-line 0 entries — but
    close enough for an advisor-level figure.
    """
    total = 0
    for m in re.finditer(r"Dividend received \(Section 194\)\s*\n+[^\n]+\s*\n", text):
        block = text[m.end() : m.end() + 1500]
        # Drop the column of dates, collect the amount column.
        # Numbers follow all the date rows; pick the first run of ≤10
        # pure-number lines after the DATE OF PAYMENT/CREDIT header.
        amt_section = re.search(
            r"DATE OF PAYMENT/CREDIT\s*\n+.*?TDS DEPOSITED STATUS\s*\n+(.*?)(?=SR\.\s*NO|\Z)",
            block,
            re.DOTALL,
        )
        if not amt_section:
            continue
        candidates = [ln.strip() for ln in amt_section.group(1).splitlines() if ln.strip()]
        # Skip the date rows at the top; amount rows are the numeric lines
        # before the TDS rows. Heuristic: first half = amounts, second = TDS.
        numeric = [c for c in candidates if re.fullmatch(r"[\d,]+(\.\d+)?", c)]
        if not numeric:
            continue
        half = max(1, len(numeric) // 3)  # dates → amounts → tds deducted → deposited
        total += sum(_parse_inr(n) for n in numeric[:half])
    return total


def parse_ais(pdf_bytes: bytes, password: str = "") -> AISSummary:
    """Parse an AIS PDF → AISSummary of totals.

    Raises AISParseError on bad password, corrupt PDF, or missing the
    standard 'Annual Information Statement' header.
    """
    text = _extract_text(pdf_bytes, password)
    if not text or "Annual Information Statement" not in text:
        raise AISParseError(
            "This doesn't look like an AIS — 'Annual Information Statement' header missing."
        )

    summary = AISSummary()

    # FY / AY
    fy = re.search(r"Financial Year\s*\n+\s*(\d{4}-\d{2})", text)
    ay = re.search(r"Assessment Year\s*\n+\s*(\d{4}-\d{2})", text)
    if fy:
        summary.financial_year = fy.group(1)
    if ay:
        summary.assessment_year = ay.group(1)

    # Extract all (desc, source, count, amount) triples and accumulate by field.
    seen_spans: set[tuple[int, int]] = set()
    for pat in (_TRIPLE_A_RE, _TRIPLE_B_RE):
        for m in pat.finditer(text):
            if m.span() in seen_spans:
                continue
            seen_spans.add(m.span())
            desc, src, _count, amt_s = m.groups()
            amt = _parse_inr(amt_s)
            field = _classify(desc)
            if field:
                setattr(summary, field, getattr(summary, field) + amt)

    # Dividend fallback — per-company blocks don't carry COUNT/AMOUNT.
    if summary.total_dividend_inr == 0:
        summary.total_dividend_inr = _sum_dividends_by_line(text)

    # TDS total — sum every "Total Tax Deducted" / "TDS DEDUCTED" column amount
    # appearing at the header level.
    for m in re.finditer(r"Total Tax Deducted[^0-9]*([\d,]+(?:\.\d+)?)", text, flags=re.IGNORECASE):
        summary.total_tds_inr += _parse_inr(m.group(1))

    return summary
