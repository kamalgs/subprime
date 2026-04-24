"""CAS (Consolidated Account Statement) PDF parser.

Wraps the `casparser` library — handles CAMS and KFintech statements which
Indian investors can download free from camsonline.com / kfintech.com.

The parsed bytes never touch disk: we write the upload to a tempfile only
long enough for casparser to read it, then it's deleted.
"""

from __future__ import annotations

import logging

from subprime.core.models import Holding

logger = logging.getLogger(__name__)


class CASParseError(Exception):
    """Parser failure — bad password, corrupt PDF, or unrecognised format."""


def _category_of(scheme: str) -> str:
    """Heuristic: derive an asset category from the scheme name.

    casparser doesn't return category directly — it returns AMFI scheme
    code + name. Rather than round-trip to our fund universe just for this,
    match common name tokens.
    """
    s = scheme.lower()
    if any(k in s for k in ("liquid", "overnight", "money market", "arbitrage")):
        return "debt"
    if any(k in s for k in ("debt", "bond", "gilt", "income", "credit risk", "corporate")):
        return "debt"
    if "gold" in s:
        return "gold"
    if any(k in s for k in ("balanced", "hybrid", "multi asset", "equity savings")):
        return "hybrid"
    if any(k in s for k in ("index", "nifty", "sensex", "etf")):
        return "equity"
    if any(k in s for k in ("equity", "large cap", "mid cap", "small cap", "flexi", "elss")):
        return "equity"
    return "equity"


def parse_cas(pdf_bytes: bytes, password: str) -> list[Holding]:
    """Parse a CAS PDF → list of current (non-zero) holdings.

    Raises CASParseError on any failure.
    """
    import casparser

    # Parse in-memory — BytesIO never touches disk, so the bytes only
    # live in the Python process heap and get GC'd with this frame.
    import io

    try:
        data = casparser.read_cas_pdf(io.BytesIO(pdf_bytes), password)
    except Exception as e:
        raise CASParseError(str(e)) from e

    # casparser ≥0.8 returns a Pydantic CASData; older versions returned a dict.
    data = data.model_dump() if hasattr(data, "model_dump") else data
    if data.get("cas_type") == "SUMMARY":
        raise CASParseError(
            "This is a Summary CAS — it doesn't include fund-level holdings. "
            "Please request a Detailed CAS from CAMS with 'With holdings' enabled."
        )

    holdings: list[Holding] = []
    for folio in data.get("folios", []) or []:
        for scheme in folio.get("schemes", []) or []:
            name = (scheme.get("scheme") or "").strip()
            val = (scheme.get("valuation") or {}).get("value") or 0
            units = scheme.get("close") or 0
            if val <= 0 and units <= 0:
                continue  # closed / redeemed
            holdings.append(
                Holding(
                    scheme=name,
                    category=_category_of(name),
                    value_inr=float(val),
                    units=float(units),
                )
            )
    if not holdings:
        raise CASParseError(
            "No active holdings found in this CAS. "
            "It may be a new folio with no units, or the PDF layout isn't "
            "a standard CAMS/KFintech consolidated statement."
        )
    return holdings
