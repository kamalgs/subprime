"""subprime.data — Mutual fund data client, DuckDB store, and PydanticAI tools."""

from subprime.data.client import MFDataClient
from subprime.data.schemas import SchemeDetails, SchemeSearchResult
from subprime.data.tools import get_fund_details, search_funds_universe

__all__ = [
    "MFDataClient",
    "SchemeDetails",
    "SchemeSearchResult",
    "get_fund_details",
    "search_funds_universe",
]
