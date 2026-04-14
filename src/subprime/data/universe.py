"""Fund universe curation and RAG context rendering.

Builds a curated, top-N-per-category fund universe from raw ``schemes`` and
``fund_returns`` data, and renders it as markdown for LLM consumption.

Central functions:

- :func:`normalize_category` — pure mapping of raw AMFI category strings to
  canonical categories used by the curated universe.
- :func:`build_universe` — repopulates the ``fund_universe`` table with the
  top-N funds per canonical category ranked by returns + AUM.
- :func:`render_universe_context` — renders the current ``fund_universe``
  table as a markdown brief for system-prompt injection.
- :func:`search_universe` — programmatic query API returning
  :class:`subprime.core.models.MutualFund` instances.
"""

from __future__ import annotations

from typing import Optional

import duckdb

from subprime.core.config import CURATED_TOP_N
from subprime.core.models import MutualFund


# --------------------------------------------------------------------------- #
# Expense ratio fallbacks
# --------------------------------------------------------------------------- #


# Fallback expense ratios when live API enrichment fails.
# Based on typical direct-plan ranges for each category in the Indian market.
_CATEGORY_TYPICAL_EXPENSE_RATIO: dict[str, float] = {
    "Index": 0.20,
    "Large Cap": 1.00,
    "Large & Mid Cap": 1.10,
    "Mid Cap": 1.15,
    "Small Cap": 1.20,
    "Flexi Cap": 1.00,
    "Multi Cap": 1.05,
    "ELSS": 1.05,
    "Hybrid": 0.95,
    "Debt": 0.55,
    "Gold": 0.40,
}


def typical_expense_ratio(category: str) -> float:
    """Return the category-typical expense ratio (fallback when live data is missing)."""
    return _CATEGORY_TYPICAL_EXPENSE_RATIO.get(category, 1.00)


# --------------------------------------------------------------------------- #
# Category taxonomy
# --------------------------------------------------------------------------- #


CURATED_CATEGORIES: list[str] = [
    "Large Cap",
    "Large & Mid Cap",
    "Mid Cap",
    "Small Cap",
    "Flexi Cap",
    "Multi Cap",
    "ELSS",
    "Index",
    "Hybrid",
    "Debt",
    "Gold",
]


# Order matters — first substring match wins.
_CATEGORY_PATTERNS: list[tuple[str, str]] = [
    ("Large & Mid Cap", "Large & Mid Cap"),
    ("Large Cap", "Large Cap"),
    ("Mid Cap", "Mid Cap"),
    ("Small Cap", "Small Cap"),
    ("Flexi Cap", "Flexi Cap"),
    ("Multi Cap", "Multi Cap"),
    ("ELSS", "ELSS"),
    ("Index Fund", "Index"),
    ("Aggressive Hybrid", "Hybrid"),
    ("Conservative Hybrid", "Hybrid"),
    ("Hybrid", "Hybrid"),
    ("Balanced", "Hybrid"),
    ("Debt Scheme", "Debt"),
    ("Gilt", "Debt"),
    ("Liquid Fund", "Debt"),
    ("Short Duration", "Debt"),
    ("Corporate Bond", "Debt"),
    ("Gold", "Gold"),
]


def normalize_category(raw: str | None) -> str | None:
    """Map a raw scheme category to a canonical curated category.

    Returns ``None`` if no pattern matches. Case-insensitive substring match,
    first hit wins.
    """
    if not raw:
        return None
    haystack = raw.lower()
    for needle, canonical in _CATEGORY_PATTERNS:
        if needle.lower() in haystack:
            return canonical
    return None


# --------------------------------------------------------------------------- #
# SQL helpers
# --------------------------------------------------------------------------- #


def _category_expense_ratio_case_sql(category_alias: str = "category") -> str:
    """Build a SQL CASE expression returning typical expense ratio for a canonical category.

    Used to populate expense_ratio in the fund_universe table when live API
    data is not yet available, and to cost-adjust the within-category ranking.
    """
    branches = [
        f"WHEN {category_alias} = '{cat}' THEN {er}"
        for cat, er in _CATEGORY_TYPICAL_EXPENSE_RATIO.items()
    ]
    return "CASE\n            " + "\n            ".join(branches) + "\n            ELSE 1.00\n        END"


def _category_case_sql(alias: str = "s.scheme_category") -> str:
    """Build a SQL ``CASE`` expression mapping raw category → canonical name.

    Uses ``ILIKE`` for case-insensitive matching. The branch order mirrors
    :data:`_CATEGORY_PATTERNS` so the first match wins, exactly like the
    Python helper :func:`normalize_category`.
    """
    branches: list[str] = []
    for needle, canonical in _CATEGORY_PATTERNS:
        # Escape single quotes in case of future pattern additions.
        safe_needle = needle.replace("'", "''")
        safe_canonical = canonical.replace("'", "''")
        branches.append(
            f"WHEN {alias} ILIKE '%{safe_needle}%' THEN '{safe_canonical}'"
        )
    return "CASE\n            " + "\n            ".join(branches) + "\n            ELSE NULL\n        END"


# --------------------------------------------------------------------------- #
# Build
# --------------------------------------------------------------------------- #


def build_universe(
    conn: duckdb.DuckDBPyConnection,
    top_n_per_category: int = CURATED_TOP_N,
) -> int:
    """Rebuild the curated ``fund_universe`` table.

    Deletes all existing rows and inserts the top-N funds per canonical
    category, ranked by ``returns_5y`` (then 3y, AUM, 1y). Excludes IDCW /
    dividend variants (we only want growth plans).

    Returns the count of rows in ``fund_universe`` after the rebuild.
    """
    conn.execute("DELETE FROM fund_universe")

    category_case = _category_case_sql()
    er_case = _category_expense_ratio_case_sql("category")

    sql = f"""
    INSERT INTO fund_universe (
        amfi_code, name, amc, category, sub_category,
        aum_cr, returns_1y, returns_3y, returns_5y, expense_ratio, rank_in_category
    )
    WITH categorized AS (
        SELECT
            s.amfi_code,
            COALESCE(s.nav_name, s.name) AS name,
            s.amc,
            {category_case} AS category,
            s.scheme_category AS sub_category,
            s.average_aum_cr AS aum_cr,
            r.returns_1y,
            r.returns_3y,
            r.returns_5y,
            COALESCE(s.plan_type, 'regular') AS plan_type
        FROM schemes s
        LEFT JOIN fund_returns r ON r.amfi_code = s.amfi_code
        WHERE (COALESCE(s.nav_name, s.name)) NOT ILIKE '%IDCW%'
          AND (COALESCE(s.nav_name, s.name)) NOT ILIKE '%dividend%'
          AND COALESCE(s.plan_type, 'regular') = 'direct'
    ),
    with_er AS (
        SELECT
            amfi_code, name, amc, category, sub_category,
            aum_cr, returns_1y, returns_3y, returns_5y,
            -- Populate expense_ratio from typical category values so the
            -- rendered universe table always shows cost estimates. Live API
            -- enrichment can overwrite these after build.
            {er_case} AS expense_ratio
        FROM categorized
        WHERE category IS NOT NULL
    ),
    ranked AS (
        SELECT
            amfi_code, name, amc, category, sub_category,
            aum_cr, returns_1y, returns_3y, returns_5y, expense_ratio,
            ROW_NUMBER() OVER (
                PARTITION BY category
                -- Cost-adjusted ranking: divide blended return by typical ER so
                -- index funds (low ER) aren't artificially depressed vs active
                -- funds with higher historical returns but higher fees.
                ORDER BY (returns_5y * 0.7 + COALESCE(returns_3y, returns_5y) * 0.3)
                             / expense_ratio DESC NULLS LAST,
                         aum_cr DESC NULLS LAST,
                         returns_1y DESC NULLS LAST
            ) AS rank_in_category
        FROM with_er
    )
    SELECT
        amfi_code, name, amc, category, sub_category,
        aum_cr, returns_1y, returns_3y, returns_5y, expense_ratio, rank_in_category
    FROM ranked
    WHERE rank_in_category <= ?
    """
    conn.execute(sql, [top_n_per_category])

    row = conn.execute("SELECT COUNT(*) FROM fund_universe").fetchone()
    return int(row[0]) if row else 0


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.1f}%"


def _fmt_er(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.2f}%"


def _fmt_aum(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:,.0f}"


def render_universe_context(conn: duckdb.DuckDBPyConnection) -> str:
    """Render the current fund universe as a markdown brief.

    Iterates :data:`CURATED_CATEGORIES` in order, rendering one table per
    category (sorted by ``rank_in_category``). Skips categories with no rows.
    Returns a placeholder string if the universe is empty.
    """
    total_row = conn.execute("SELECT COUNT(*) FROM fund_universe").fetchone()
    total = int(total_row[0]) if total_row else 0
    if total == 0:
        return "No curated fund universe available. Use live search tools if needed."

    lines: list[str] = [
        "## Curated Fund Universe (India)",
        "",
        "Use these funds as the primary source when building plans. "
        "All returns are CAGR % computed from historical NAV.",
        "",
    ]

    for category in CURATED_CATEGORIES:
        rows = conn.execute(
            """
            SELECT name, amc, amfi_code, returns_1y, returns_3y, returns_5y, expense_ratio, aum_cr
            FROM fund_universe
            WHERE category = ?
            ORDER BY rank_in_category
            """,
            [category],
        ).fetchall()
        if not rows:
            continue

        lines.append(f"### {category}")
        lines.append("| Fund | AMC | AMFI | 1y | 3y | 5y | ER | AUM (Cr) |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for name, amc, amfi_code, r1, r3, r5, er, aum in rows:
            lines.append(
                f"| {name} | {amc} | {amfi_code} | "
                f"{_fmt_pct(r1)} | {_fmt_pct(r3)} | {_fmt_pct(r5)} | "
                f"{_fmt_er(er)} | {_fmt_aum(aum)} |"
            )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


# --------------------------------------------------------------------------- #
# Search
# --------------------------------------------------------------------------- #


def search_universe(
    conn: duckdb.DuckDBPyConnection,
    category: str | None = None,
    limit: int = 20,
) -> list[MutualFund]:
    """Query the curated fund universe, returning ``MutualFund`` objects.

    Optional ``category`` filter matches the canonical category exactly.
    Results are ordered by ``rank_in_category``.
    """
    if category is not None:
        rows = conn.execute(
            """
            SELECT amfi_code, name, amc, category, sub_category,
                   aum_cr, returns_1y, returns_3y, returns_5y, expense_ratio
            FROM fund_universe
            WHERE category = ?
            ORDER BY rank_in_category
            LIMIT ?
            """,
            [category, limit],
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT amfi_code, name, amc, category, sub_category,
                   aum_cr, returns_1y, returns_3y, returns_5y, expense_ratio
            FROM fund_universe
            ORDER BY category, rank_in_category
            LIMIT ?
            """,
            [limit],
        ).fetchall()

    funds: list[MutualFund] = []
    for amfi_code, name, amc, cat, sub_cat, aum, r1, r3, r5, er in rows:
        funds.append(
            MutualFund(
                amfi_code=str(amfi_code),
                name=name or "",
                category=cat or "",
                sub_category=sub_cat or "",
                fund_house=amc or "",
                nav=0.0,
                expense_ratio=er or 0.0,
                aum_cr=aum,
                returns_1y=r1,
                returns_3y=r3,
                returns_5y=r5,
            )
        )
    return funds


def search_universe_by_code(
    conn: duckdb.DuckDBPyConnection,
    amfi_code: str,
) -> Optional[MutualFund]:
    """Look up a single fund by AMFI code from the curated universe."""
    row = conn.execute(
        """
        SELECT amfi_code, name, amc, category, sub_category,
               aum_cr, returns_1y, returns_3y, returns_5y, expense_ratio
        FROM fund_universe
        WHERE amfi_code = ?
        """,
        [amfi_code],
    ).fetchone()
    if not row:
        return None
    return MutualFund(
        amfi_code=str(row[0]),
        name=row[1] or "",
        category=row[3] or "",
        sub_category=row[4] or "",
        fund_house=row[2] or "",
        nav=0.0,
        expense_ratio=row[9] or 0.0,
        aum_cr=row[5],
        returns_1y=row[6],
        returns_3y=row[7],
        returns_5y=row[8],
    )
