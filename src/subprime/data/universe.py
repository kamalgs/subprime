"""Fund universe curation and RAG context rendering.

Builds a curated, top-N-per-category fund universe from raw ``schemes`` and
``fund_returns`` data, and renders it as markdown for LLM consumption.

Central functions:

- :func:`normalize_category` — pure mapping of raw AMFI category strings to
  canonical categories used by the curated universe.
- :func:`build_universe` — repopulates the ``fund_universe`` table with the
  top-N funds per canonical category ranked by AUM (within a return tier).
  **Ranking is intentionally return- and AUM-only; expense ratio plays no
  role so that low-ER (index) and high-ER (active) funds compete on equal
  footing.  The LLM advisor sees cost data in the table and is free to weigh
  it — but the *selection* of which funds appear must not pre-bias toward
  either philosophy.**
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
    "Aggressive Hybrid": 1.00,
    "Conservative Hybrid": 0.85,
    "Debt": 0.55,
    "Gold": 0.40,
}


def typical_expense_ratio(category: str) -> float:
    """Return the category-typical expense ratio (fallback when live data is missing)."""
    return _CATEGORY_TYPICAL_EXPENSE_RATIO.get(category, 1.00)


# --------------------------------------------------------------------------- #
# Category taxonomy
# --------------------------------------------------------------------------- #


# Tax treatment per category, used by render_universe_context and advisor prompts.
# In India the 65 % equity threshold determines whether a fund is treated as
# "equity-oriented" (favourable LTCG/STCG) or taxed at the investor's slab rate.
# Post-Budget 2024: equity LTCG 12.5 % on gains above ₹1.25 L (held >1y),
# equity STCG 20 % (held <1y), debt fully at slab rate regardless of holding.
_CATEGORY_TAX_TREATMENT: dict[str, str] = {
    "Large Cap": "equity",
    "Large & Mid Cap": "equity",
    "Mid Cap": "equity",
    "Small Cap": "equity",
    "Flexi Cap": "equity",
    "Multi Cap": "equity",
    "ELSS": "equity-80c",
    "Index": "equity",
    "Aggressive Hybrid": "equity",
    "Conservative Hybrid": "slab",
    "Debt": "slab",
    "Gold": "slab",
}


_TAX_LABELS: dict[str, str] = {
    "equity": "equity-taxed — LTCG 12.5 % on gains >₹1.25L (held >1y), STCG 20 % (held <1y)",
    "equity-80c": (
        "equity-taxed + 80C deduction up to ₹1.5L on investment, "
        "3-year lock-in; LTCG 12.5 % on gains >₹1.25L (held >1y)"
    ),
    "slab": "slab-taxed — all gains at investor's income-tax slab, no LTCG/STCG concession",
}


def tax_regime(category: str) -> str:
    """Return the tax-regime key (``equity`` / ``equity-80c`` / ``slab``) for a category."""
    return _CATEGORY_TAX_TREATMENT.get(category, "slab")


CURATED_CATEGORIES: list[str] = [
    "Large Cap",
    "Large & Mid Cap",
    "Mid Cap",
    "Small Cap",
    "Flexi Cap",
    "Multi Cap",
    "ELSS",
    "Index",
    "Aggressive Hybrid",
    "Conservative Hybrid",
    "Debt",
    "Gold",
]


# Order matters — first substring match wins.
#
# The Aggressive / Conservative Hybrid split follows the 65 % equity threshold
# that determines tax treatment in India:
#   • ≥ 65 % equity → equity-taxed (LTCG 12.5 % / STCG 20 %)
#   • < 65 % equity → slab-taxed
# Balanced Advantage / Dynamic Asset Allocation / Equity Savings / Arbitrage
# funds maintain ≥ 65 % equity exposure (often via hedged positions) and
# qualify for equity taxation, so they live under "Aggressive Hybrid".
# Balanced Hybrid (40–60 % equity) falls below the 65 % threshold and is
# debt-taxed, so it lives under "Conservative Hybrid".
_CATEGORY_PATTERNS: list[tuple[str, str]] = [
    ("Large & Mid Cap", "Large & Mid Cap"),
    ("Large Cap", "Large Cap"),
    ("Mid Cap", "Mid Cap"),
    ("Small Cap", "Small Cap"),
    ("Flexi Cap", "Flexi Cap"),
    ("Multi Cap", "Multi Cap"),
    ("ELSS", "ELSS"),
    ("Index Fund", "Index"),
    ("Aggressive Hybrid", "Aggressive Hybrid"),
    ("Balanced Advantage", "Aggressive Hybrid"),
    ("Dynamic Asset Allocation", "Aggressive Hybrid"),
    ("Equity Savings", "Aggressive Hybrid"),
    ("Arbitrage", "Aggressive Hybrid"),
    ("Conservative Hybrid", "Conservative Hybrid"),
    ("Balanced Hybrid", "Conservative Hybrid"),
    ("Multi Asset", "Conservative Hybrid"),
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

    Deletes all existing rows and inserts up to ``top_n_per_category`` funds
    per canonical category using a **three-tier quota** so that funds at every
    stage of their track-record are represented:

    - **Tier 1 — established** (has 5y data): ~40 % of slots,
      ranked by ``returns_5y DESC, aum_cr DESC``.
    - **Tier 2 — growing** (3y data, no 5y): ~30 % of slots,
      ranked by ``returns_3y DESC, aum_cr DESC``.
    - **Tier 3 — newer** (1y data, no 3y/5y): remaining slots,
      ranked by ``returns_1y DESC, aum_cr DESC``.

    Each tier competes only within itself so a 1y return is never compared
    against a 5y CAGR.  Expense ratio plays no role in selection; the LLM
    sees cost data in the rendered table and weighs it freely.

    Excludes IDCW / dividend variants (growth plans only).

    Returns the count of rows inserted into ``fund_universe``.
    """
    import math

    tier1_n = math.ceil(top_n_per_category * 0.40)          # ~40 % established
    tier2_n = math.ceil(top_n_per_category * 0.30)          # ~30 % growing
    tier3_n = top_n_per_category - tier1_n - tier2_n        # remaining newer

    conn.execute("DELETE FROM fund_universe")

    category_case = _category_case_sql()
    er_case = _category_expense_ratio_case_sql("category")

    sql = f"""
    INSERT INTO fund_universe (
        amfi_code, name, amc, category, sub_category,
        aum_cr, launch_date, returns_1y, returns_3y, returns_5y,
        expense_ratio, rank_in_category,
        volatility_1y, beta, alpha, tracking_error, sharpe_ratio, information_ratio
    )
    WITH categorized AS (
        SELECT
            s.amfi_code,
            COALESCE(s.nav_name, s.name) AS name,
            s.amc,
            {category_case} AS category,
            s.scheme_category AS sub_category,
            s.average_aum_cr AS aum_cr,
            s.launch_date,
            r.returns_1y,
            r.returns_3y,
            r.returns_5y,
            r.volatility_1y,
            r.beta,
            r.alpha,
            r.tracking_error,
            r.sharpe_ratio,
            r.information_ratio,
            COALESCE(s.plan_type, 'regular') AS plan_type
        FROM schemes s
        LEFT JOIN fund_returns r ON r.amfi_code = s.amfi_code
        WHERE coalesce(s.nav_name, s.name) NOT ILIKE '%IDCW%'
          AND coalesce(s.nav_name, s.name) NOT ILIKE '%dividend%'
          AND COALESCE(s.plan_type, 'regular') = 'direct'
    ),
    with_er AS (
        SELECT
            amfi_code, name, amc, category, sub_category,
            aum_cr, launch_date, returns_1y, returns_3y, returns_5y,
            volatility_1y, beta, alpha, tracking_error, sharpe_ratio, information_ratio,
            {er_case} AS expense_ratio
        FROM categorized
        WHERE category IS NOT NULL
    ),
    -- Tier 1: established funds with a 5-year track record
    tier1 AS (
        SELECT *, 1 AS tier,
               ROW_NUMBER() OVER (
                   PARTITION BY category
                   ORDER BY returns_5y DESC NULLS LAST, aum_cr DESC NULLS LAST
               ) AS rn
        FROM with_er
        WHERE returns_5y IS NOT NULL
    ),
    -- Tier 2: growing funds with 3y but no 5y data
    tier2 AS (
        SELECT *, 2 AS tier,
               ROW_NUMBER() OVER (
                   PARTITION BY category
                   ORDER BY returns_3y DESC NULLS LAST, aum_cr DESC NULLS LAST
               ) AS rn
        FROM with_er
        WHERE returns_5y IS NULL AND returns_3y IS NOT NULL
    ),
    -- Tier 3: newer funds with only 1y data
    tier3 AS (
        SELECT *, 3 AS tier,
               ROW_NUMBER() OVER (
                   PARTITION BY category
                   ORDER BY returns_1y DESC NULLS LAST, aum_cr DESC NULLS LAST
               ) AS rn
        FROM with_er
        WHERE returns_5y IS NULL AND returns_3y IS NULL AND returns_1y IS NOT NULL
    ),
    combined AS (
        SELECT * FROM tier1 WHERE rn <= {tier1_n}
        UNION ALL
        SELECT * FROM tier2 WHERE rn <= {tier2_n}
        UNION ALL
        SELECT * FROM tier3 WHERE rn <= {tier3_n}
    )
    SELECT
        amfi_code, name, amc, category, sub_category,
        aum_cr, launch_date, returns_1y, returns_3y, returns_5y,
        expense_ratio,
        ROW_NUMBER() OVER (PARTITION BY category ORDER BY tier, rn) AS rank_in_category,
        volatility_1y, beta, alpha, tracking_error, sharpe_ratio, information_ratio
    FROM combined
    """
    conn.execute(sql)

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


def _fmt_metric(value: float | None, decimals: int = 2) -> str:
    if value is None:
        return "-"
    return f"{value:.{decimals}f}"


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
        "Column guide: β=beta vs Nifty 50 (1.0=market), α=Jensen's alpha annualised %, "
        "TE=tracking error % (low TE = index-like behaviour, high TE = genuinely active), "
        "Sharpe=risk-adjusted return. "
        "A fund with β≈1, α≈0, TE<2% is a closet indexer regardless of its category label.",
        "",
        "### Tax treatment (Indian MF, post-Budget 2024)",
        "",
        "The **65 % equity threshold** determines whether a fund is equity-taxed "
        "(LTCG 12.5 % on gains above ₹1.25 L held >1y, STCG 20 % held <1y) or "
        "slab-taxed (all gains at the investor's marginal slab, no concession). "
        "Each category table below is tagged with its regime — use this to build "
        "post-tax-optimal plans, especially for investors in the 20 % / 30 % slab.",
        "",
        "- **Equity-taxed**: Large/Mid/Small/Large & Mid/Flexi/Multi Cap, Index, "
        "ELSS, Aggressive Hybrid (incl. Balanced Advantage, DAAF, Equity Savings, "
        "Arbitrage — all maintain ≥65 % equity).",
        "- **Slab-taxed**: Conservative Hybrid, Balanced Hybrid, Multi Asset "
        "Allocation, Debt (all sub-types: Gilt, Liquid, Short Duration, Corporate "
        "Bond), Gold.",
        "- **ELSS special**: 80C deduction up to ₹1.5 L on investment, 3-year "
        "lock-in, then equity-taxed on gains. Most tax-efficient equity wrapper "
        "for investors with unused 80C headroom.",
        "",
    ]

    from datetime import date as _date

    today = _date.today()

    for category in CURATED_CATEGORIES:
        rows = conn.execute(
            """
            SELECT name, amc, amfi_code, launch_date,
                   returns_1y, returns_3y, returns_5y,
                   expense_ratio, aum_cr,
                   beta, alpha, tracking_error, sharpe_ratio
            FROM fund_universe
            WHERE category = ?
            ORDER BY rank_in_category
            """,
            [category],
        ).fetchall()
        if not rows:
            continue

        tax_label = _TAX_LABELS[tax_regime(category)]
        lines.append(f"### {category}  _({tax_label})_")
        lines.append("| Fund | AMC | AMFI | Age | AUM (Cr) | 1y | 3y | 5y | ER | β | α | TE | Sharpe |")
        lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for (name, amc, amfi_code, launch_date,
             r1, r3, r5, er, aum,
             beta, alpha, te, sharpe) in rows:
            age = f"{(today - launch_date).days // 365}y" if launch_date else "-"
            lines.append(
                f"| {name} | {amc} | {amfi_code} | {age} | {_fmt_aum(aum)} | "
                f"{_fmt_pct(r1)} | {_fmt_pct(r3)} | {_fmt_pct(r5)} | "
                f"{_fmt_er(er)} | "
                f"{_fmt_metric(beta)} | {_fmt_metric(alpha)}% | "
                f"{_fmt_metric(te)}% | {_fmt_metric(sharpe)} |"
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
    _SELECT = """
        SELECT amfi_code, name, amc, category, sub_category,
               launch_date, aum_cr,
               returns_1y, returns_3y, returns_5y, expense_ratio,
               volatility_1y, beta, alpha, tracking_error, sharpe_ratio, information_ratio
        FROM fund_universe
    """
    if category is not None:
        rows = conn.execute(
            _SELECT + "WHERE category = ? ORDER BY rank_in_category LIMIT ?",
            [category, limit],
        ).fetchall()
    else:
        rows = conn.execute(
            _SELECT + "ORDER BY category, rank_in_category LIMIT ?",
            [limit],
        ).fetchall()

    funds: list[MutualFund] = []
    for (amfi_code, name, amc, cat, sub_cat,
         launch_date, aum, r1, r3, r5, er,
         vol, beta, alpha, te, sharpe, ir) in rows:
        funds.append(
            MutualFund(
                amfi_code=str(amfi_code),
                name=name or "",
                category=cat or "",
                sub_category=sub_cat or "",
                fund_house=amc or "",
                nav=0.0,
                inception_date=launch_date,
                expense_ratio=er or 0.0,
                aum_cr=aum,
                returns_1y=r1,
                returns_3y=r3,
                returns_5y=r5,
                volatility_1y=vol,
                beta=beta,
                alpha=alpha,
                tracking_error=te,
                sharpe_ratio=sharpe,
                information_ratio=ir,
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
               launch_date, aum_cr,
               returns_1y, returns_3y, returns_5y, expense_ratio,
               volatility_1y, beta, alpha, tracking_error, sharpe_ratio, information_ratio
        FROM fund_universe
        WHERE amfi_code = ?
        """,
        [amfi_code],
    ).fetchone()
    if not row:
        return None
    (code, name, amc, cat, sub_cat,
     launch_date, aum, r1, r3, r5, er,
     vol, beta, alpha, te, sharpe, ir) = row
    return MutualFund(
        amfi_code=str(code),
        name=name or "",
        category=cat or "",
        sub_category=sub_cat or "",
        fund_house=amc or "",
        nav=0.0,
        inception_date=launch_date,
        expense_ratio=er or 0.0,
        aum_cr=aum,
        returns_1y=r1,
        returns_3y=r3,
        returns_5y=r5,
        volatility_1y=vol,
        beta=beta,
        alpha=alpha,
        tracking_error=te,
        sharpe_ratio=sharpe,
        information_ratio=ir,
    )
