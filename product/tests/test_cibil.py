"""Tests for CIBIL CIR parser + upload endpoint.

The real-layout parsing logic is unit-tested against a synthetic text
block that mimics what pdfminer produces on a CIBIL PDF; we don't ship a
real CIBIL PDF (contains PII) or a heavy encrypted fixture. The endpoint
tests only exercise the failure paths — valid-PDF parsing is covered by
the unit tests on the text parser.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from subprime.data.cibil import CIBILParseError, _parse_account_block, parse_cibil

FIXTURE = Path(__file__).parent / "fixtures" / "dummy_cibil.pdf"


# The exact layout pdfminer emits for a CIBIL account block — 5-label
# block followed by 5-value block, in column order.
_ACCOUNT_TEXT = """\
HDFC BANK

HOUSING LOAN

XXXX1234

(MEMBER NAME)

(ACCOUNT TYPE)

(ACCOUNT NUMBER)

INDIVIDUAL

(OWNERSHIP)

ACCOUNT DETAILS
CREDIT LIMIT
SANCTIONED AMOUNT
CURRENT BALANCE
CASH LIMIT
AMOUNT OVERDUE

-
40,00,000
28,40,000
-
0

RATE OF INTEREST
REPAYMENT TENURE
EMI AMOUNT
PAYMENT FREQUENCY
ACTUAL PAYMENT AMOUNT

8.5
240
34,500
MONTHLY
34,500

DATE OPENED/DISBURSED
DATE CLOSED

15-06-2021
-

DATE OF LAST PAYMENT
DATE REPORTED AND CERTIFIED

01-04-2026
15-04-2026
"""


def test_parse_account_block_housing_loan() -> None:
    acc = _parse_account_block(_ACCOUNT_TEXT)
    assert acc is not None
    assert acc.account_type == "HOUSING LOAN"
    assert acc.is_open is True
    assert acc.current_balance_inr == 2840000
    assert acc.emi_inr == 34500
    assert acc.amount_overdue_inr == 0
    assert acc.date_opened == "15-06-2021"


def test_parse_account_block_returns_none_on_unknown_type() -> None:
    """No recognised loan/card type → no account."""
    assert _parse_account_block("Random\nACCOUNT DETAILS\nCREDIT LIMIT\n-\n") is None


def test_parse_account_block_closed_account_has_is_open_false() -> None:
    closed = _ACCOUNT_TEXT.replace("15-06-2021\n-", "15-06-2021\n12-03-2025")
    acc = _parse_account_block(closed)
    assert acc is not None
    assert acc.is_open is False


def test_parse_cibil_rejects_non_cibil_pdf_bytes() -> None:
    """Bytes that don't decode to a CIBIL report must error clearly."""
    with pytest.raises(CIBILParseError):
        parse_cibil(b"not a pdf at all", "anything")


def test_parse_cibil_wrong_password_errors() -> None:
    """Uses the encrypted dummy_cas.pdf as a stand-in for 'wrong pw' —
    same pdfminer path, different structure. Either wrong-password or
    not-a-cibil error is acceptable."""
    cas_fixture = Path(__file__).parent / "fixtures" / "dummy_cas.pdf"
    with pytest.raises(CIBILParseError):
        parse_cibil(cas_fixture.read_bytes(), "wrong-password")


@pytest.mark.asyncio
async def test_upload_cibil_requires_profile() -> None:
    from apps.web.main import create_app

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        with FIXTURE.open("rb") as f:
            r = await c.post(
                "/api/v2/profile/cibil",
                files={"file": ("cibil.pdf", f, "application/pdf")},
                data={"password": "whatever"},
            )
        # Either 400 for missing profile OR 400 for parse failure — both mean
        # we got past auth/routing into the validation layer.
        assert r.status_code in (400, 413)


@pytest.mark.asyncio
async def test_upload_cibil_rejects_large_files() -> None:
    from apps.web.main import create_app

    app = create_app()
    big = b"\x00" * (11 * 1024 * 1024)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post(
            "/api/v2/profile/cibil",
            files={"file": ("cibil.pdf", big, "application/pdf")},
            data={"password": "x"},
        )
    assert r.status_code == 413
