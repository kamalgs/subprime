"""Async HTTP client for mfdata.in — Indian mutual fund data API.

Wraps httpx for async requests and returns typed Pydantic models.
"""

from __future__ import annotations

from types import TracebackType
from typing import Optional

import httpx

from subprime.core.models import MutualFund
from subprime.data.schemas import SchemeDetails, SchemeSearchResult


class MFDataClient:
    """Async client for the mfdata.in API.

    Usage::

        async with MFDataClient() as client:
            results = await client.search_funds("nifty 50")
            details = await client.get_fund_details("119551")
    """

    def __init__(self, base_url: str = "https://mfdata.in/api/v1") -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=30.0)

    async def __aenter__(self) -> MFDataClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self._client.aclose()

    # ------------------------------------------------------------------
    # API methods
    # ------------------------------------------------------------------

    async def search_funds(
        self, query: str, category: Optional[str] = None
    ) -> list[SchemeSearchResult]:
        """Search for mutual fund schemes by name or keyword.

        Args:
            query: Search term (e.g. "nifty 50", "hdfc balanced").
            category: Optional category filter (e.g. "Equity", "Debt").

        Returns:
            List of matching schemes (may be empty).
        """
        params: dict[str, str] = {"q": query}
        if category is not None:
            params["category"] = category

        resp = await self._client.get("/schemes", params=params)
        resp.raise_for_status()
        body = resp.json()
        data = body.get("data", body) if isinstance(body, dict) else body
        if isinstance(data, list):
            return [SchemeSearchResult(**item) for item in data]
        return []

    async def get_fund_details(self, amfi_code: str) -> SchemeDetails:
        """Get detailed information for a single fund by AMFI code.

        Args:
            amfi_code: The AMFI registration number (e.g. "119551").

        Returns:
            Scheme details including NAV, expense ratio, AUM, etc.

        Raises:
            httpx.HTTPStatusError: If the fund is not found (404) or other HTTP error.
        """
        resp = await self._client.get(f"/schemes/{amfi_code}")
        resp.raise_for_status()
        body = resp.json()
        data = body.get("data", body) if isinstance(body, dict) else body
        return SchemeDetails(**data)

    async def get_nav_history(self, amfi_code: str) -> list[dict]:
        """Get NAV history for a fund.

        Args:
            amfi_code: The AMFI registration number.

        Returns:
            List of dicts with 'date' and 'nav' keys.

        Raises:
            httpx.HTTPStatusError: If the fund is not found (404) or other HTTP error.
        """
        resp = await self._client.get(f"/schemes/{amfi_code}/nav")
        resp.raise_for_status()
        body = resp.json()
        data = body.get("data", body) if isinstance(body, dict) else body
        return data if isinstance(data, list) else [data]

    # ------------------------------------------------------------------
    # Conversion
    # ------------------------------------------------------------------

    @staticmethod
    def details_to_mutual_fund(details: SchemeDetails) -> MutualFund:
        """Convert an API SchemeDetails response to the core MutualFund model.

        Missing optional fields are mapped to sensible defaults:
        - expense_ratio defaults to 0.0 when not provided by the API.
        - morningstar maps to morningstar_rating.
        """
        return MutualFund(
            amfi_code=details.amfi_code,
            name=details.name,
            category=details.category or "",
            sub_category=details.sub_category or "",
            fund_house=details.fund_house or "",
            nav=details.nav,
            expense_ratio=details.expense_ratio if details.expense_ratio is not None else 0.0,
            aum_cr=details.aum_cr,
            morningstar_rating=(
                details.morningstar if details.morningstar and details.morningstar >= 1 else None
            ),
        )

    @staticmethod
    def search_result_to_mutual_fund(result: SchemeSearchResult) -> MutualFund:
        """Convert a search result to core MutualFund (has most fields already)."""
        return MutualFund(
            amfi_code=result.amfi_code,
            name=result.name,
            category=result.category or "",
            sub_category=result.sub_category or "",
            fund_house=result.fund_house or "",
            nav=result.nav,
            expense_ratio=result.expense_ratio if result.expense_ratio is not None else 0.0,
            aum_cr=result.aum_cr,
            morningstar_rating=(
                result.morningstar if result.morningstar and result.morningstar >= 1 else None
            ),
        )
