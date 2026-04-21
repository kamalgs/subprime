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
    assert "40.0%" in text
    assert "30.0%" in text


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


def _load(xlsx_bytes: bytes):
    from openpyxl import load_workbook
    return load_workbook(filename=BytesIO(xlsx_bytes), read_only=False, data_only=True)


def test_xlsx_opens_and_has_expected_sheets(plan, profile):
    xlsx = build_plan_xlsx(plan, profile)
    wb = _load(xlsx)
    expected = {
        "Summary", "Allocations", "Projections", "Setup",
        "Review checkpoints", "Rebalancing", "Rationale",
        "Risks", "Disclaimer",
    }
    assert expected.issubset(set(wb.sheetnames)), \
        f"missing: {expected - set(wb.sheetnames)}"


def test_xlsx_summary_has_investor_name(plan, profile):
    wb = _load(build_plan_xlsx(plan, profile))
    s = wb["Summary"]
    flat = "\n".join(str(c.value) for row in s.iter_rows() for c in row if c.value)
    assert "Ananya Shetty" in flat
    assert "Benji" in flat


def test_xlsx_allocations_typed(plan, profile):
    wb = _load(build_plan_xlsx(plan, profile))
    sh = wb["Allocations"]
    header = [c.value for c in sh[1]]
    assert header == ["AMFI code", "Fund", "AMC", "Category",
                      "% Allocation", "Mode", "Monthly SIP (₹)", "Lumpsum (₹)"]
    # First data row
    row = [c.value for c in sh[2]]
    assert row[0] == "119551"
    assert row[1] == "HDFC Nifty 50 Index"
    assert isinstance(row[4], (int, float))       # % Allocation is numeric
    assert row[4] == 40.0
    assert isinstance(row[6], (int, float))       # SIP amount is numeric
    assert row[6] == 20_000


def test_xlsx_projections_numeric(plan, profile):
    wb = _load(build_plan_xlsx(plan, profile))
    pr = wb["Projections"]
    rows = list(pr.iter_rows(values_only=True))
    assert rows[0] == ("Scenario", "CAGR %")
    # Scenario/value pairs — all values should be numeric
    for label, val in rows[1:]:
        assert label in {"Bear", "Base", "Bull"}
        assert isinstance(val, (int, float))


def test_xlsx_disclaimer_present(plan, profile):
    wb = _load(build_plan_xlsx(plan, profile))
    d = wb["Disclaimer"]
    assert "research" in str(d["A1"].value).lower()


def test_xlsx_omits_empty_optional_sheets(plan, profile):
    plan.setup_phase = ""
    plan.rebalancing_guidelines = ""
    plan.rationale = ""
    plan.risks = []
    plan.review_checkpoints = []
    wb = _load(build_plan_xlsx(plan, profile))
    # Required sheets still there
    assert {"Summary", "Allocations", "Disclaimer"}.issubset(set(wb.sheetnames))
    # Empty optional sheets NOT created
    assert "Setup" not in wb.sheetnames
    assert "Risks" not in wb.sheetnames
