"""Rich display helpers for Subprime plans and scores.

format_* functions render to strings (via StringIO) for testability.
print_* functions write directly to the terminal.
"""

from __future__ import annotations

from io import StringIO

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from subprime.core.models import APSScore, InvestmentPlan, PlanQualityScore, StrategyOutline


def format_plan_summary(plan: InvestmentPlan) -> str:
    """Render an InvestmentPlan to a Rich-formatted string.

    Includes:
    - Allocations table (fund name, AMFI code, %, mode, monthly SIP, rationale)
    - Projected returns table (Bear/Base/Bull, color-coded)
    - Rationale panel
    """
    buf = StringIO()
    console = Console(file=buf, force_terminal=True, width=120)

    # --- Allocations table ---
    alloc_table = Table(title="Allocations", show_lines=True, expand=True)
    alloc_table.add_column("Fund Name", style="bold cyan", no_wrap=False)
    alloc_table.add_column("AMFI Code", justify="center")
    alloc_table.add_column("%", justify="right")
    alloc_table.add_column("Mode", justify="center")
    alloc_table.add_column("Monthly SIP", justify="right")
    alloc_table.add_column("Rationale", no_wrap=False)

    for alloc in plan.allocations:
        sip_str = f"{alloc.monthly_sip_inr:,.0f}" if alloc.monthly_sip_inr else "-"
        alloc_table.add_row(
            alloc.fund.name,
            alloc.fund.amfi_code,
            f"{alloc.allocation_pct:.1f}",
            alloc.mode,
            sip_str,
            alloc.rationale,
        )

    console.print(alloc_table)

    # --- Projected returns table ---
    returns_table = Table(title="Projected Returns (CAGR %)", show_lines=True)
    returns_table.add_column("Bear", style="red", justify="right")
    returns_table.add_column("Base", style="yellow", justify="right")
    returns_table.add_column("Bull", style="green", justify="right")

    bear = plan.projected_returns.get("bear", 0.0)
    base = plan.projected_returns.get("base", 0.0)
    bull = plan.projected_returns.get("bull", 0.0)
    returns_table.add_row(f"{bear:.1f}%", f"{base:.1f}%", f"{bull:.1f}%")

    console.print(returns_table)

    # --- Rationale panel ---
    console.print(Panel(plan.rationale, title="Rationale", border_style="blue"))

    return buf.getvalue()


def format_scores(aps: APSScore, pqs: PlanQualityScore) -> str:
    """Render APS and PQS scores to a Rich-formatted string.

    Shows composite scores and all individual dimensions.
    """
    buf = StringIO()
    console = Console(file=buf, force_terminal=True, width=100)

    # --- APS table ---
    aps_table = Table(title="Active-Passive Score (APS)", show_lines=True)
    aps_table.add_column("Dimension", style="bold")
    aps_table.add_column("Score", justify="right")

    aps_table.add_row("Passive Instrument Fraction", f"{aps.passive_instrument_fraction:.2f}")
    aps_table.add_row("Turnover Score", f"{aps.turnover_score:.2f}")
    aps_table.add_row("Cost Emphasis", f"{aps.cost_emphasis_score:.2f}")
    aps_table.add_row("Research vs Cost", f"{aps.research_vs_cost_score:.2f}")
    aps_table.add_row("Time Horizon Alignment", f"{aps.time_horizon_alignment_score:.2f}")
    aps_table.add_row("[bold]Composite APS[/bold]", f"[bold]{aps.composite_aps:.3f}[/bold]")

    console.print(aps_table)

    # --- PQS table ---
    pqs_table = Table(title="Plan Quality Score (PQS)", show_lines=True)
    pqs_table.add_column("Dimension", style="bold")
    pqs_table.add_column("Score", justify="right")

    pqs_table.add_row("Goal Alignment", f"{pqs.goal_alignment:.2f}")
    pqs_table.add_row("Diversification", f"{pqs.diversification:.2f}")
    pqs_table.add_row("Risk-Return Appropriateness", f"{pqs.risk_return_appropriateness:.2f}")
    pqs_table.add_row("Internal Consistency", f"{pqs.internal_consistency:.2f}")
    pqs_table.add_row("[bold]Composite PQS[/bold]", f"[bold]{pqs.composite_pqs:.3f}[/bold]")

    console.print(pqs_table)

    return buf.getvalue()


def format_strategy_outline(outline: StrategyOutline) -> str:
    """Render a StrategyOutline to a Rich-formatted string.

    Includes:
    - Asset allocation table (Equity, Debt, Gold; Other only if > 0)
    - Equity approach
    - Key themes (comma-separated)
    - Risk/return summary
    - Open questions (if any)
    """
    buf = StringIO()
    console = Console(file=buf, force_terminal=True, width=100)

    # --- Asset allocation table ---
    alloc_table = Table(title="Asset Allocation", show_lines=True)
    alloc_table.add_column("Asset Class", style="bold")
    alloc_table.add_column("%", justify="right")

    alloc_table.add_row("Equity", f"{outline.equity_pct:.0f}%")
    alloc_table.add_row("Debt", f"{outline.debt_pct:.0f}%")
    alloc_table.add_row("Gold", f"{outline.gold_pct:.0f}%")
    if outline.other_pct > 0:
        alloc_table.add_row("Other", f"{outline.other_pct:.0f}%")

    console.print(alloc_table)

    # --- Equity approach ---
    console.print(f"[bold]Equity Approach:[/bold] {escape(outline.equity_approach)}", highlight=False)

    # --- Key themes ---
    themes_str = ", ".join(outline.key_themes)
    console.print(f"[bold]Themes:[/bold] {escape(themes_str)}", highlight=False)

    # --- Risk/return summary ---
    console.print(f"[bold]Risk/Return:[/bold] {escape(outline.risk_return_summary)}", highlight=False)

    # --- Open questions ---
    if outline.open_questions:
        console.print("[bold]Open Questions:[/bold]")
        for q in outline.open_questions:
            console.print(f"  • {escape(q)}", highlight=False)

    return buf.getvalue()


def print_plan(plan: InvestmentPlan) -> None:
    """Print a formatted plan summary to the terminal."""
    console = Console()
    console.print(format_plan_summary(plan))


def print_scores(aps: APSScore, pqs: PlanQualityScore) -> None:
    """Print formatted scores to the terminal."""
    console = Console()
    console.print(format_scores(aps, pqs))
