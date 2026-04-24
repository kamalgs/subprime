"""CIBIL Credit Information Report (CIR) PDF parser.

CIBIL (TransUnion CIBIL) is India's largest credit bureau. Consumers can
download a free CIR annually from cibil.com; the PDF is password-protected
by a code the user sets during download.

Calibrated against a real CIBIL CIR layout. Scope is deliberately narrow:
we only extract the fields the advisor actually consumes — total
outstanding, total monthly EMI, active-loan count, overdue flag — plus a
per-account breakdown for display. The credit score itself is rendered as
a graphical gauge, not selectable text, so we don't try to OCR it.

The PDF never touches disk beyond a tempfile that pdfminer reads and
discards immediately.
"""

from __future__ import annotations

import logging
import re
import tempfile
from pathlib import Path

from subprime.core.models import CreditAccount, CreditSummary

logger = logging.getLogger(__name__)


class CIBILParseError(Exception):
    """Bad password, corrupt PDF, or unrecognised layout."""


_KNOWN_TYPES = (
    "HOUSING LOAN",
    "AUTO LOAN",
    "PERSONAL LOAN",
    "CREDIT CARD",
    "CONSUMER LOAN",
    "TWO-WHEELER LOAN",
    "LOAN AGAINST PROPERTY",
    "EDUCATION LOAN",
    "BUSINESS LOAN",
    "GOLD LOAN",
    "OVERDRAFT",
)

_ACCOUNT_END_RE = re.compile(r"DATE REPORTED AND CERTIFIED\s*\n+\S+\s*\n+\S+")
_FIVE_VALUES_AFTER = r"(?:\S+\s*\n+){{5}}"


def _parse_inr(s: str) -> int:
    """Parse Indian-style '1,23,456' → int. '-' or unparseable → 0."""
    if not s or s == "-":
        return 0
    try:
        return int(s.strip().replace(",", ""))
    except ValueError:
        return 0


def _parse_account_block(block: str) -> CreditAccount | None:
    """Extract a single account's fields from a text block.

    Returns None when the block doesn't look like an account (e.g. the
    header boilerplate between the personal-info section and the first
    account).
    """
    # Account type — look for a known loan/card type token near the top.
    type_match = re.search("|".join(re.escape(t) for t in _KNOWN_TYPES), block.upper())
    if not type_match:
        return None
    account_type = type_match.group()

    # Financial values: pdfminer emits the 5 labels
    # (CREDIT LIMIT / SANCTIONED AMOUNT / CURRENT BALANCE / CASH LIMIT /
    # AMOUNT OVERDUE) followed by the 5 values in the same order.
    fin_match = re.search(
        r"AMOUNT OVERDUE\s*\n+((?:\S+\s*\n+){5})",
        block,
    )
    current_balance = amount_overdue = 0
    if fin_match:
        vals = [v.strip() for v in fin_match.group(1).splitlines() if v.strip()][:5]
        if len(vals) >= 5:
            _, _, cb, _, od = vals
            current_balance = _parse_inr(cb)
            amount_overdue = _parse_inr(od)

    # EMI block — labels RATE OF INTEREST / REPAYMENT TENURE / EMI AMOUNT /
    # PAYMENT FREQUENCY / ACTUAL PAYMENT AMOUNT.
    emi_match = re.search(
        r"ACTUAL PAYMENT AMOUNT\s*\n+((?:\S+\s*\n+){5})",
        block,
    )
    emi = 0
    if emi_match:
        vals = [v.strip() for v in emi_match.group(1).splitlines() if v.strip()][:5]
        if len(vals) >= 3:
            emi = _parse_inr(vals[2])

    # Open/closed — DATE CLOSED == "-" means still open.
    date_match = re.search(
        r"DATE OPENED/DISBURSED\s*\nDATE CLOSED\s*\n+(\S+)\s*\n+(\S+)",
        block,
    )
    if date_match:
        date_opened = date_match.group(1)
        is_open = date_match.group(2) == "-"
    else:
        date_opened = ""
        is_open = True  # conservative: count as active if we can't tell

    return CreditAccount(
        account_type=account_type,
        is_open=is_open,
        current_balance_inr=current_balance,
        amount_overdue_inr=amount_overdue,
        emi_inr=emi,
        date_opened=date_opened,
    )


def _extract_text(pdf_bytes: bytes, password: str) -> str:
    from pdfminer.high_level import extract_text

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as tmp:
        tmp.write(pdf_bytes)
        tmp.flush()
        try:
            return extract_text(str(Path(tmp.name)), password=password)
        except Exception as e:
            raise CIBILParseError(f"PDF read failed: {e}") from e


def parse_cibil(pdf_bytes: bytes, password: str) -> CreditSummary:
    """Parse a CIBIL CIR PDF → CreditSummary.

    Raises ``CIBILParseError`` on bad password, corrupt PDF, or a layout
    we don't recognise. Unrecognised layout here means "no account blocks
    found" — callers can surface a "try a different PDF" message.
    """
    text = _extract_text(pdf_bytes, password)
    if not text or "CIBIL" not in text.upper():
        raise CIBILParseError(
            "This doesn't look like a CIBIL report — couldn't find 'CIBIL' header."
        )

    # Slice into account blocks. Each ends at "DATE REPORTED AND CERTIFIED"
    # + 2 date lines; the first starts at "ACCOUNT INFORMATION".
    end_positions = [m.end() for m in _ACCOUNT_END_RE.finditer(text)]
    if not end_positions:
        raise CIBILParseError(
            "Couldn't find any account blocks. The PDF may be a summary or a "
            "redesigned layout we haven't calibrated yet."
        )

    first_start = text.find("ACCOUNT INFORMATION")
    if first_start == -1:
        raise CIBILParseError("Missing 'ACCOUNT INFORMATION' section marker.")

    starts = [first_start] + end_positions[:-1]
    accounts: list[CreditAccount] = []
    for start, end in zip(starts, end_positions):
        acc = _parse_account_block(text[start:end])
        if acc is not None:
            accounts.append(acc)

    summary = CreditSummary(accounts=accounts)
    for a in accounts:
        if a.is_open:
            summary.active_account_count += 1
            summary.total_outstanding_inr += a.current_balance_inr
            summary.total_monthly_emi_inr += a.emi_inr
        else:
            summary.closed_account_count += 1
        summary.total_overdue_inr += a.amount_overdue_inr
    summary.has_overdue = summary.total_overdue_inr > 0
    return summary
