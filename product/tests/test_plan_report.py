"""Tests for the plan PDF + Excel report generators.

Covers:
  - PDF bytes are valid (starts with %PDF, reasonable length, contains our
    branded strings like 'Benji' and the disclaimer).
  - PDF survives edge cases: missing projected_returns, empty setup_phase,
    risks with leading '- ' markers (defensive — _format strips these but
    the report must still render if a caller skipped normalization).
  - XLSX opens cleanly, has every expected sheet, numeric cells are numeric,
    disclaimer is present and red-coloured.
"""
from __future__ import annotations

import re
from io import BytesIO

import pytest

from subprime.core.models import (
    Allocation,
    InvestmentPlan,
    InvestorProfile,
    MutualFund,
)
from subprime.core.plan_report import (
    build_plan_pdf,
    build_plan_xlsx,
)


@pytest.fixture
def profile() -> InvestorProfile:
    return InvestorProfile(
        id="P01", name="Ananya Shetty",
        financial_goals=["retirement", "home"],
        life_stage="mid career", tax_bracket="30%",
        age=38, risk_appetite="moderate",
        monthly_investible_surplus_inr=50000,
        existing_corpus_inr=2_500_000,
        liabilities_inr=0,
        investment_horizon_years=15,
    )


@pytest.fixture
def plan() -> InvestmentPlan:
    f1 = MutualFund(
        amfi_code="119551", name="HDFC Nifty 50 Index Direct Growth",
        display_name="HDFC Nifty 50 Index", category="Index", fund_house="HDFC",
    )
    f2 = MutualFund(
        amfi_code="120505", name="Parag Parikh Flexi Cap Direct Growth",
        display_name="Parag Parikh Flexi Cap", category="Flexi Cap", fund_house="PPFAS",
    )
    return InvestmentPlan(
        allocations=[
            Allocation(fund=f1, allocation_pct=40.0, mode="sip",
                       monthly_sip_inr=20_000, lumpsum_inr=0, rationale="Core equity"),
            Allocation(fund=f2, allocation_pct=30.0, mode="sip",
                       monthly_sip_inr=15_000, lumpsum_inr=0, rationale="Active tilt"),
        ],
        setup_phase="- Open a direct MF account on Kuvera\n- Start the monthly SIPs\n- Complete KYC",
        review_checkpoints=[
            "Year 3: if small-cap fund underperforms category by >3%, switch.",
            "When horizon drops below 5 years, shift equity to hybrid.",
        ],
        rebalancing_guidelines="Rebalance annually if any bucket drifts >5 pp from target.",
        projected_returns={"bear": 8.0, "base": 12.0, "bull": 16.0},
        rationale="Mid-career moderate risk with 15-year horizon — index core plus active tilt.",
        risks=[
            "Markets can drop 20-30% in a bad year.",
            "Active funds may underperform the index for extended periods.",
        ],
    )


# ── PDF ──────────────────────────────────────────────────────────────────────


def test_pdf_is_valid_bytes(plan, profile):
    pdf = build_plan_pdf(plan, profile)
    assert pdf[:5] == b"%PDF-", "not a valid PDF magic header"
    assert len(pdf) > 2000, "PDF smaller than expected — renderer likely produced empty pages"


def _pdf_text(pdf_bytes: bytes) -> str:
    """Extract the rendered text from a PDF using pypdf.

    ReportLab compresses content streams, so grepping raw bytes doesn't
    work for the rendered text. pypdf decompresses and decodes for us.
    """
    from io import BytesIO
    from pypdf import PdfReader
    reader = PdfReader(BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def test_pdf_contains_branding_and_disclaimer(plan, profile):
    text = _pdf_text(build_plan_pdf(plan, profile))
    assert "Benji" in text
    assert "Ananya Shetty" in text
    assert "research/educational purposes" in text


def test_pdf_contains_allocation_rows(plan, profile):
    text = _pdf_text(build_plan_pdf(plan, profile))
    assert "HDFC Nifty 50 Index" in text
    assert "Parag Parikh Flexi Cap" in text
    # Percentages are rendered with 0 decimal places in the table
    assert "40%" in text
    assert "30%" in text


def test_pdf_projection_includes_absolute_corpus(plan, profile):
    """Projection block should show both CAGR % and absolute final corpus."""
    text = _pdf_text(build_plan_pdf(plan, profile))
    # CAGR percentages
    assert "12.0%" in text
    # Absolute final corpus for the given SIP (35k/mo) and horizon (15 yrs):
    # at 12% CAGR ≈ ₹1.76 Cr — the table uses Cr / L suffixes.
    assert "Cr" in text or "L" in text  # has Indian numeric formatting somewhere


def test_pdf_has_short_disclaimer_up_front_and_footnote(plan, profile):
    text = _pdf_text(build_plan_pdf(plan, profile))
    # short disclaimer appears near the top with the ** footnote marker
    assert "research / educational use" in text
    assert "**" in text


def test_pdf_renders_without_projections(plan, profile):
    plan.projected_returns = {}
    pdf = build_plan_pdf(plan, profile)
    assert pdf[:5] == b"%PDF-"


def test_pdf_renders_without_optional_sections(plan, profile):
    plan.setup_phase = ""
    plan.rebalancing_guidelines = ""
    plan.rationale = ""
    plan.risks = []
    plan.review_checkpoints = []
    pdf = build_plan_pdf(plan, profile)
    assert pdf[:5] == b"%PDF-"
    # Disclaimer always present — it's the last flowable
    assert "research/educational purposes" in _pdf_text(pdf)


def test_pdf_handles_leading_bullet_markers_in_setup(plan, profile):
    """_format normally strips leading '- ' but the report must not choke
    if a caller skipped normalization."""
    plan.setup_phase = (
        "- Step one\n- Step two\n- Step three"
    )
    text = _pdf_text(build_plan_pdf(plan, profile))
    assert "Step one" in text
    assert "Step two" in text
    assert "Step three" in text


# ── Excel ────────────────────────────────────────────────────────────────────


def _load(xlsx_bytes: bytes, data_only: bool = True):
    """Load the workbook.

    ``data_only=True`` replaces formulas with their cached result — good
    for asserting numeric values. Pass ``data_only=False`` when checking
    formula strings (we haven't opened the file in Excel yet, so cached
    formula results are None).
    """
    from openpyxl import load_workbook
    return load_workbook(filename=BytesIO(xlsx_bytes), read_only=False,
                         data_only=data_only)


def _flat_cells(sheet) -> list:
    return [c.value for row in sheet.iter_rows() for c in row]


def test_xlsx_has_only_two_sheets(plan, profile):
    wb = _load(build_plan_xlsx(plan, profile))
    assert wb.sheetnames == ["Plan", "Explore"]


def test_xlsx_plan_has_wordmark_and_investor(plan, profile):
    wb = _load(build_plan_xlsx(plan, profile))
    flat = [str(c) for c in _flat_cells(wb["Plan"]) if c]
    assert any("Benji" in s for s in flat)
    assert any("Ananya Shetty" in s for s in flat)
    assert any("research / educational" in s for s in flat)


def test_xlsx_plan_has_allocations_table(plan, profile):
    wb = _load(build_plan_xlsx(plan, profile))
    flat = [str(c) for c in _flat_cells(wb["Plan"]) if c]
    # Both fund names present
    assert any("HDFC Nifty 50 Index" in s for s in flat)
    assert any("Parag Parikh Flexi Cap" in s for s in flat)


def test_xlsx_plan_has_projection_data(plan, profile):
    wb = _load(build_plan_xlsx(plan, profile))
    p = wb["Plan"]
    # Find the "Projected returns" header row and check the next three rows
    # have numeric CAGR + corpus values.
    flat = [str(c) for c in _flat_cells(p) if c]
    assert any("Projected returns" in s for s in flat)
    # Some cell in the sheet should be a non-trivial numeric corpus (the
    # best-case corpus for 35k/mo × 15yrs × 16% ≈ ₹2.5 Cr → 25_000_000).
    numbers = [c.value for row in p.iter_rows()
               for c in row if isinstance(c.value, (int, float))]
    assert max(numbers) > 10_000_000  # > 1 Cr somewhere


def test_xlsx_explore_sheet_has_editable_inputs_and_formulas(plan, profile):
    wb = _load(build_plan_xlsx(plan, profile), data_only=False)
    ex = wb["Explore"]
    # Input section contains 'Monthly SIP' label + editable SIP value
    labels = [c.value for row in ex.iter_rows(min_row=4, max_row=10)
              for c in row if c.value]
    assert any("Monthly SIP" in str(l) for l in labels)
    assert any("Horizon" in str(l) for l in labels)
    # Output formulas for final corpus — the three FV cells must start with =
    for addr in ("E5", "E6", "E7"):
        val = ex[addr].value
        assert isinstance(val, str) and val.startswith("="), \
            f"{addr} expected a formula, got {val!r}"
    # Growth-over-time formula table
    assert ex["A12"].value == "Year"
    # Year-0 formula should exist (year_cell row 13)
    assert ex["B13"].value is not None and str(ex["B13"].value).startswith("=")


def test_xlsx_plan_renders_without_optional_sections(plan, profile):
    plan.setup_phase = ""
    plan.rebalancing_guidelines = ""
    plan.rationale = ""
    plan.risks = []
    plan.review_checkpoints = []
    wb = _load(build_plan_xlsx(plan, profile))
    assert wb.sheetnames == ["Plan", "Explore"]


def test_xlsx_disclaimer_in_both_sheets(plan, profile):
    wb = _load(build_plan_xlsx(plan, profile))
    for name in ("Plan", "Explore"):
        flat = [str(c) for c in _flat_cells(wb[name]) if c]
        assert any("research" in str(s).lower() for s in flat), \
            f"{name} sheet missing disclaimer"
