"""subprime.data — Mutual fund data client and PydanticAI tool functions."""

from subprime.data.client import MFDataClient
from subprime.data.schemas import SchemeDetails, SchemeSearchResult
from subprime.data.tools import compare_funds, get_fund_performance, search_funds

__all__ = [
    "MFDataClient",
    "SchemeDetails",
    "SchemeSearchResult",
    "compare_funds",
    "get_fund_performance",
    "search_funds",
]
