"""Raw API response models for mfdata.in.

These are separate from the core MutualFund model — they mirror the API
response shapes exactly, and are converted to core models via the client.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class SchemeSearchResult(BaseModel):
    """A single result from the mfdata.in /schemes?q= endpoint."""

    amfi_code: str
    name: str
    category: Optional[str] = ""
    plan_type: str = ""
    option_type: str = ""
    nav: float = 0.0
    nav_date: Optional[str] = None
    expense_ratio: Optional[float] = None
    aum: Optional[float] = None  # raw number, not crores
    morningstar: Optional[int] = None
    risk_label: Optional[str] = None
    family_name: Optional[str] = None
    amc_name: Optional[str] = None
    amc_slug: Optional[str] = None

    @property
    def fund_house(self) -> str:
        return self.amc_name or ""

    @property
    def sub_category(self) -> str:
        return self.category

    @property
    def aum_cr(self) -> Optional[float]:
        return self.aum / 1e7 if self.aum else None


class SchemeDetails(BaseModel):
    """Detailed fund information from mfdata.in /schemes/{code}."""

    amfi_code: str
    name: str
    category: Optional[str] = ""
    plan_type: str = ""
    option_type: str = ""
    nav: float = 0.0
    nav_date: Optional[str] = None
    expense_ratio: Optional[float] = None
    aum: Optional[float] = None  # raw number, not crores
    morningstar: Optional[int] = None
    risk_label: Optional[str] = None
    family_name: Optional[str] = None
    amc_name: Optional[str] = None
    amc_slug: Optional[str] = None

    @property
    def fund_house(self) -> str:
        return self.amc_name or ""

    @property
    def sub_category(self) -> str:
        return self.category

    @property
    def aum_cr(self) -> Optional[float]:
        return self.aum / 1e7 if self.aum else None
