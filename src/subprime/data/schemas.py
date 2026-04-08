"""Raw API response models for mfdata.in.

These are separate from the core MutualFund model — they mirror the API
response shapes exactly, and are converted to core models via the client.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class SchemeSearchResult(BaseModel):
    """A single result from the mfdata.in search endpoint."""

    amfi_code: str
    name: str
    category: str
    sub_category: str
    fund_house: str


class SchemeDetails(BaseModel):
    """Detailed fund information from mfdata.in."""

    amfi_code: str
    name: str
    category: str
    sub_category: str
    fund_house: str
    nav: float
    nav_date: Optional[str] = None
    expense_ratio: Optional[float] = None
    aum_cr: Optional[float] = None
    morningstar: Optional[int] = None
