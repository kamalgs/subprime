"""Generate downloadable plan reports — PDF + Excel.

The PDF is laid out with ReportLab's Platypus flowables: title block
with the Benji wordmark, a one-line investor summary, then one section
per plan field (allocations table, projected returns, setup steps,
checkpoints, rebalancing, rationale, risks), and finally the disclaimer
as a red-outlined box. Mirrors the on-screen plan so the PDF is a direct
print-quality equivalent.

The Excel file is a structured workbook: one sheet per major data block
(Summary, Allocations, Projected returns, Setup, Review checkpoints,
Risks). Plain text, typed numeric columns where relevant.
"""
from __future__ import annotations

from datetime import datetime
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from subprime.core.models import InvestmentPlan, InvestorProfile

# Benji brand tones (match tailwind primary-600 and red-600).
BRAND = colors.HexColor("#dc2626")           # red accent (matches wordmark)
PRIMARY = colors.HexColor("#2563eb")         # blue primary
MUTED = colors.HexColor("#64748b")           # slate
DARK = colors.HexColor("#0f172a")


def _styles() -> dict[str, ParagraphStyle]:
    ss = getSampleStyleSheet()
    # Tight, readable copy — A4 print-friendly
    return {
        "title": ParagraphStyle(
            "benji_title", parent=ss["Title"],
            fontName="Helvetica-Bold", fontSize=22, leading=26,
            textColor=DARK, spaceAfter=4,
        ),
        "subtitle": ParagraphStyle(
            "benji_sub", parent=ss["BodyText"],
            fontName="Helvetica", fontSize=10, leading=14,
            textColor=MUTED, spaceAfter=14,
        ),
        "section": ParagraphStyle(
            "benji_section", parent=ss["Heading2"],
            fontName="Helvetica-Bold", fontSize=13, leading=18,
            textColor=BRAND, spaceBefore=10, spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "benji_body", parent=ss["BodyText"],
            fontName="Helvetica", fontSize=10, leading=14,
            textColor=DARK, spaceAfter=4,
        ),
        "bullet": ParagraphStyle(
            "benji_bullet", parent=ss["BodyText"],
            fontName="Helvetica", fontSize=10, leading=14,
            leftIndent=14, bulletIndent=2, textColor=DARK, spaceAfter=2,
        ),
        "risk": ParagraphStyle(
            "benji_risk", parent=ss["BodyText"],
            fontName="Helvetica", fontSize=10, leading=14,
            leftIndent=14, bulletIndent=2, textColor=DARK, spaceAfter=2,
        ),
        "disclaimer": ParagraphStyle(
            "benji_disclaimer", parent=ss["BodyText"],
            fontName="Helvetica-Oblique", fontSize=8.5, leading=12,
            textColor=BRAND, alignment=1, spaceBefore=8,  # center aligned
        ),
        "footer": ParagraphStyle(
            "benji_footer", parent=ss["BodyText"],
            fontName="Helvetica", fontSize=8, leading=10,
            textColor=MUTED, alignment=1,
        ),
    }


def _header_band(canvas, doc) -> None:  # noqa: ARG001
    """Draw a thin red accent band on every page + footer pagination."""
    canvas.saveState()
    canvas.setFillColor(BRAND)
    canvas.rect(0, doc.pagesize[1] - 0.35 * cm, doc.pagesize[0], 0.35 * cm, stroke=0, fill=1)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 8)
    page_str = f"Page {canvas.getPageNumber()}"
    canvas.drawRightString(doc.pagesize[0] - 1.5 * cm, 1.1 * cm, page_str)
    canvas.drawString(1.5 * cm, 1.1 * cm, "Benji — AI financial advisor")
    canvas.restoreState()


def _fmt_money_inr(amount: float) -> str:
    """Indian number format with lakhs / crores suffixes."""
    if amount >= 1_00_00_000:
        return f"₹{amount / 1_00_00_000:.2f} Cr"
    if amount >= 1_00_000:
        return f"₹{amount / 1_00_000:.2f} L"
    return f"₹{amount:,.0f}"


def _allocations_table(plan: InvestmentPlan, styles: dict) -> Table:
    data = [["Fund", "AMC", "Category", "% Alloc", "Mode"]]
    for a in plan.allocations:
        fund = a.fund
        name = fund.display_name or fund.name or fund.amfi_code
        data.append([
            Paragraph(name, styles["body"]),
            fund.fund_house or "—",
            fund.category or "—",
            f"{a.allocation_pct:.1f}%",
            (a.mode or "—").upper(),
        ])
    tbl = Table(data, colWidths=[6.5 * cm, 3.0 * cm, 3.0 * cm, 2.0 * cm, 2.5 * cm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (3, 0), (3, -1), "RIGHT"),
        ("ALIGN", (4, 0), (4, -1), "CENTER"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.white),
    ]))
    return tbl


def _projections_table(plan: InvestmentPlan, styles: dict) -> Table | None:
    p = plan.projected_returns or {}
    if not p:
        return None
    data = [["Scenario", "CAGR"]]
    for key in ("bear", "base", "bull"):
        if key in p:
            data.append([key.title(), f"{p[key]:.1f}%"])
    tbl = Table(data, colWidths=[3.5 * cm, 2.5 * cm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
    ]))
    return tbl


def build_plan_pdf(plan: InvestmentPlan, profile: InvestorProfile) -> bytes:
    """Render the full plan as a branded A4 PDF, return bytes."""
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=1.5 * cm, rightMargin=1.5 * cm,
        topMargin=1.4 * cm, bottomMargin=2 * cm,
        title=f"Benji plan — {profile.name}", author="Benji",
    )
    styles = _styles()
    story: list = []

    # Title block
    story.append(Paragraph("Benji", ParagraphStyle(
        "wordmark", parent=styles["title"],
        fontName="Helvetica-Bold", fontSize=26, textColor=BRAND,
    )))
    story.append(Paragraph(
        f"Investment plan for <b>{profile.name}</b> · "
        f"{getattr(profile, 'life_stage', 'investor')} · "
        f"generated {datetime.utcnow().strftime('%d %b %Y')}",
        styles["subtitle"],
    ))

    # Profile summary
    monthly = getattr(profile, "monthly_investible_surplus_inr", None)
    horizon = getattr(profile, "investment_horizon_years", None)
    summary_bits = []
    if monthly:
        summary_bits.append(f"Investible surplus: <b>{_fmt_money_inr(float(monthly))}/mo</b>")
    if horizon:
        summary_bits.append(f"Horizon: <b>{horizon} years</b>")
    risk = getattr(profile, "risk_appetite", None)
    if risk:
        summary_bits.append(f"Risk: <b>{risk}</b>")
    if summary_bits:
        story.append(Paragraph(" · ".join(summary_bits), styles["body"]))
        story.append(Spacer(1, 6))

    # Allocations
    story.append(Paragraph("Allocations", styles["section"]))
    story.append(_allocations_table(plan, styles))
    story.append(Spacer(1, 4))

    # Projected returns
    proj = _projections_table(plan, styles)
    if proj is not None:
        story.append(Paragraph("Projected returns (CAGR)", styles["section"]))
        story.append(proj)

    # Setup phase
    if plan.setup_phase:
        story.append(Paragraph("Setup phase", styles["section"]))
        for line in _split_bullets(plan.setup_phase):
            story.append(Paragraph(line, styles["bullet"], bulletText="›"))

    # Review checkpoints
    if plan.review_checkpoints:
        story.append(Paragraph("Review checkpoints", styles["section"]))
        for cp in plan.review_checkpoints:
            story.append(Paragraph(cp, styles["bullet"], bulletText="›"))

    # Rebalancing guidelines
    if plan.rebalancing_guidelines:
        story.append(Paragraph("Rebalancing", styles["section"]))
        for line in _split_bullets(plan.rebalancing_guidelines):
            story.append(Paragraph(line, styles["bullet"], bulletText="›"))

    # Rationale
    if plan.rationale:
        story.append(Paragraph("Why this plan", styles["section"]))
        for line in _split_bullets(plan.rationale):
            story.append(Paragraph(line, styles["bullet"], bulletText="›"))

    # Risks
    if plan.risks:
        story.append(Paragraph("Risks to consider", styles["section"]))
        for r in plan.risks:
            story.append(Paragraph(r, styles["risk"], bulletText="⚠"))

    # Disclaimer
    story.append(Spacer(1, 12))
    story.append(Paragraph(plan.disclaimer, styles["disclaimer"]))

    doc.build(story, onFirstPage=_header_band, onLaterPages=_header_band)
    return buf.getvalue()


def _split_bullets(text: str) -> list[str]:
    """Normalize markdown-bullet text into plain sentences for PDF bullets."""
    if not text:
        return []
    out: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        # strip leading list markers
        for prefix in ("- ", "* ", "+ ", "• "):
            if s.startswith(prefix):
                s = s[len(prefix):]
                break
        # strip numbered markers
        import re
        s = re.sub(r"^\d+[.)]\s*", "", s)
        if s:
            out.append(s)
    return out or [text.strip()]


# ── Excel ─────────────────────────────────────────────────────────────────────

def build_plan_xlsx(plan: InvestmentPlan, profile: InvestorProfile) -> bytes:
    """Write the plan to an Excel workbook, return bytes."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    hdr_fill = PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid")
    hdr_font = Font(bold=True, color="FFFFFF")
    brand_font = Font(bold=True, color="DC2626", size=14)

    # ── Summary sheet ─────────────────────────────────────────────
    s = wb.active
    s.title = "Summary"
    s["A1"] = "Benji — Investment plan"
    s["A1"].font = brand_font
    s["A2"] = f"Investor: {profile.name}"
    s["A3"] = f"Generated: {datetime.utcnow().strftime('%d %b %Y')}"
    row = 5
    for label, val in [
        ("Life stage", getattr(profile, "life_stage", "")),
        ("Age", getattr(profile, "age", "")),
        ("Risk appetite", getattr(profile, "risk_appetite", "")),
        ("Monthly surplus (₹)", getattr(profile, "monthly_investible_surplus_inr", "")),
        ("Existing corpus (₹)", getattr(profile, "existing_corpus_inr", "")),
        ("Liabilities (₹)", getattr(profile, "liabilities_inr", "")),
        ("Horizon (years)", getattr(profile, "investment_horizon_years", "")),
        ("Tax bracket", getattr(profile, "tax_bracket", "")),
    ]:
        if val in (None, ""):
            continue
        s.cell(row=row, column=1, value=label).font = Font(bold=True)
        s.cell(row=row, column=2, value=val)
        row += 1
    s.column_dimensions["A"].width = 22
    s.column_dimensions["B"].width = 30

    # ── Allocations ───────────────────────────────────────────────
    alloc = wb.create_sheet("Allocations")
    alloc.append(["AMFI code", "Fund", "AMC", "Category",
                  "% Allocation", "Mode", "Monthly SIP (₹)", "Lumpsum (₹)"])
    for cell in alloc[1]:
        cell.fill = hdr_fill; cell.font = hdr_font
    for a in plan.allocations:
        f = a.fund
        alloc.append([
            f.amfi_code,
            f.display_name or f.name,
            f.fund_house or "",
            f.category or "",
            round(a.allocation_pct, 2),
            (a.mode or "").upper(),
            a.monthly_sip_inr or "",
            a.lumpsum_inr or "",
        ])
    for col, w in zip("ABCDEFGH", [12, 42, 20, 20, 14, 10, 16, 14]):
        alloc.column_dimensions[col].width = w

    # ── Projected returns ─────────────────────────────────────────
    if plan.projected_returns:
        pr = wb.create_sheet("Projections")
        pr.append(["Scenario", "CAGR %"])
        for cell in pr[1]:
            cell.fill = hdr_fill; cell.font = hdr_font
        for key in ("bear", "base", "bull"):
            if key in plan.projected_returns:
                pr.append([key.title(), round(plan.projected_returns[key], 2)])
        pr.column_dimensions["A"].width = 14
        pr.column_dimensions["B"].width = 12

    # ── Setup / Checkpoints / Risks / Rebalancing / Rationale ─────
    def _text_sheet(name: str, body: str | list[str], *, split_bullets: bool = False):
        if not body:
            return
        sh = wb.create_sheet(name)
        items = body if isinstance(body, list) else \
                (_split_bullets(body) if split_bullets else [body])
        sh.append([name])
        sh["A1"].fill = hdr_fill; sh["A1"].font = hdr_font
        sh.column_dimensions["A"].width = 100
        for i, item in enumerate(items, start=2):
            sh.cell(row=i, column=1, value=item).alignment = Alignment(wrap_text=True)

    _text_sheet("Setup", plan.setup_phase, split_bullets=True)
    _text_sheet("Review checkpoints", plan.review_checkpoints or [])
    _text_sheet("Rebalancing", plan.rebalancing_guidelines, split_bullets=True)
    _text_sheet("Rationale", plan.rationale, split_bullets=True)
    _text_sheet("Risks", plan.risks or [])

    # ── Disclaimer ────────────────────────────────────────────────
    dsc = wb.create_sheet("Disclaimer")
    dsc["A1"] = plan.disclaimer
    dsc["A1"].font = Font(italic=True, color="DC2626", size=10)
    dsc["A1"].alignment = Alignment(wrap_text=True)
    dsc.column_dimensions["A"].width = 100

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
