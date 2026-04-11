"""subprime.data — Mutual fund data client, DuckDB store, and PydanticAI tools."""

from subprime.data.client import MFDataClient
from subprime.data.schemas import SchemeDetails, SchemeSearchResult
from subprime.data.tools import compare_funds, get_fund_performance, search_funds_universe

__all__ = [
    "MFDataClient",
    "SchemeDetails",
    "SchemeSearchResult",
    "compare_funds",
    "get_fund_performance",
    "search_funds_universe",
]
