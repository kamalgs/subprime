"""Gradio web interface for Subprime financial advisor."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import gradio as gr
from dotenv import load_dotenv

load_dotenv()

from subprime.advisor.planner import generate_plan, generate_strategy
from subprime.core.models import (
    Allocation,
    ConversationLog,
    ConversationTurn,
    InvestmentPlan,
    InvestorProfile,
    StrategyOutline,
)
from subprime.evaluation.personas import load_personas

logger = logging.getLogger("subprime.web")

CONVERSATIONS_DIR = Path("conversations")

# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

CSS = """
.subprime-header {
    text-align: center;
    padding: 1rem 0 0.5rem 0;
}
.subprime-header h1 {
    margin: 0;
    font-size: 1.8rem;
    font-weight: 700;
    color: #1a1a2e;
}
.subprime-header p {
    margin: 0.25rem 0 0 0;
    font-size: 0.95rem;
    color: #555;
}
.section-label {
    font-weight: 600;
    font-size: 1.05rem;
    color: #1a1a2e;
    margin-bottom: 0.25rem;
}
.plan-html table {
    width: 100%;
    border-collapse: collapse;
    margin: 0.75rem 0;
    font-size: 0.9rem;
}
.plan-html th {
    background: #f0f0f5;
    text-align: left;
    padding: 0.5rem 0.75rem;
    border-bottom: 2px solid #ddd;
    font-weight: 600;
    color: #1a1a2e;
}
.plan-html td {
    padding: 0.5rem 0.75rem;
    border-bottom: 1px solid #eee;
    vertical-align: top;
}
.plan-html tr:hover td {
    background: #fafafe;
}
.plan-html .section-title {
    font-weight: 600;
    font-size: 1rem;
    color: #1a1a2e;
    margin: 1rem 0 0.5rem 0;
    padding-bottom: 0.25rem;
    border-bottom: 2px solid #e0e0e0;
}
.plan-html .stat-row {
    display: flex;
    gap: 1.5rem;
    margin: 0.5rem 0;
}
.plan-html .stat-box {
    background: #f8f8fc;
    border: 1px solid #e0e0e8;
    border-radius: 6px;
    padding: 0.5rem 1rem;
    text-align: center;
    min-width: 100px;
}
.plan-html .stat-box .label {
    font-size: 0.75rem;
    color: #777;
    text-transform: uppercase;
}
.plan-html .stat-box .value {
    font-size: 1.1rem;
    font-weight: 600;
    color: #1a1a2e;
}
.plan-html .stat-box.bear .value { color: #c0392b; }
.plan-html .stat-box.base .value { color: #d4a017; }
.plan-html .stat-box.bull .value { color: #27ae60; }
.plan-html .rationale-box {
    background: #f8f8fc;
    border-left: 3px solid #667eea;
    padding: 0.75rem 1rem;
    margin: 0.5rem 0;
    font-size: 0.9rem;
    line-height: 1.5;
}
.plan-html .risk-item {
    padding: 0.2rem 0;
    color: #555;
}
.plan-html ul {
    margin: 0.25rem 0;
    padding-left: 1.25rem;
}
.plan-html li {
    margin: 0.2rem 0;
}
.conv-card {
    border: 1px solid #e0e0e8;
    border-radius: 8px;
    padding: 1rem;
    margin: 0.5rem 0;
    cursor: pointer;
    transition: border-color 0.15s;
}
.conv-card:hover {
    border-color: #667eea;
}
.conv-card .conv-id {
    font-weight: 600;
    color: #1a1a2e;
}
.conv-card .conv-meta {
    font-size: 0.85rem;
    color: #777;
    margin-top: 0.25rem;
}
"""


# ---------------------------------------------------------------------------
# HTML rendering helpers
# ---------------------------------------------------------------------------

def _esc(text: str) -> str:
    """Escape HTML entities."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def render_profile_html(profile: InvestorProfile) -> str:
    """Render an InvestorProfile as clean HTML."""
    goals_html = "".join(f"<li>{_esc(g)}</li>" for g in profile.financial_goals)
    prefs = _esc(profile.preferences) if profile.preferences else "None specified"

    return f"""<div class="plan-html">
<div class="section-title">Investor Profile: {_esc(profile.name)} ({_esc(profile.id)})</div>
<table>
    <tr><th style="width:200px">Age</th><td>{profile.age}</td></tr>
    <tr><th>Risk Appetite</th><td>{_esc(profile.risk_appetite).title()}</td></tr>
    <tr><th>Investment Horizon</th><td>{profile.investment_horizon_years} years</td></tr>
    <tr><th>Monthly SIP Budget</th><td>&#8377;{profile.monthly_investible_surplus_inr:,.0f}</td></tr>
    <tr><th>Existing Corpus</th><td>&#8377;{profile.existing_corpus_inr:,.0f}</td></tr>
    <tr><th>Liabilities</th><td>&#8377;{profile.liabilities_inr:,.0f}</td></tr>
    <tr><th>Life Stage</th><td>{_esc(profile.life_stage)}</td></tr>
    <tr><th>Tax Bracket</th><td>{_esc(profile.tax_bracket)}</td></tr>
    <tr><th>Preferences</th><td>{prefs}</td></tr>
    <tr><th>Financial Goals</th><td><ul>{goals_html}</ul></td></tr>
</table>
</div>"""


def render_strategy_html(strategy: StrategyOutline) -> str:
    """Render a StrategyOutline as clean HTML."""
    alloc_rows = f"""
    <tr><td>Equity</td><td>{strategy.equity_pct:.0f}%</td></tr>
    <tr><td>Debt</td><td>{strategy.debt_pct:.0f}%</td></tr>
    <tr><td>Gold</td><td>{strategy.gold_pct:.0f}%</td></tr>"""
    if strategy.other_pct > 0:
        alloc_rows += f"\n    <tr><td>Other</td><td>{strategy.other_pct:.0f}%</td></tr>"

    themes_html = ", ".join(_esc(t) for t in strategy.key_themes)

    questions_html = ""
    if strategy.open_questions:
        q_items = "".join(f"<li>{_esc(q)}</li>" for q in strategy.open_questions)
        questions_html = f"""
<div class="section-title">Open Questions</div>
<ul>{q_items}</ul>"""

    return f"""<div class="plan-html">
<div class="section-title">Strategy Outline</div>
<table>
    <tr><th style="width:120px">Asset Class</th><th>Allocation</th></tr>
    {alloc_rows}
</table>
<div class="section-title">Equity Approach</div>
<div class="rationale-box">{_esc(strategy.equity_approach)}</div>
<div class="section-title">Key Themes</div>
<p>{themes_html}</p>
<div class="section-title">Risk / Return Summary</div>
<div class="rationale-box">{_esc(strategy.risk_return_summary)}</div>
{questions_html}
</div>"""


def render_plan_html(plan: InvestmentPlan) -> str:
    """Render an InvestmentPlan as clean HTML."""
    # Allocations table
    alloc_rows = ""
    for a in plan.allocations:
        sip = f"&#8377;{a.monthly_sip_inr:,.0f}" if a.monthly_sip_inr else "-"
        er = f"{a.fund.expense_ratio:.2f}%" if a.fund.expense_ratio else "-"
        rating = "" if not a.fund.morningstar_rating else ("&#9733;" * a.fund.morningstar_rating)
        alloc_rows += f"""<tr>
    <td><strong>{_esc(a.fund.name)}</strong><br><span style="color:#888;font-size:0.8rem">{_esc(a.fund.amfi_code)}</span></td>
    <td>{_esc(a.fund.fund_house) if a.fund.fund_house else '-'}</td>
    <td style="text-align:right">{a.allocation_pct:.0f}%</td>
    <td style="text-align:center">{a.mode}</td>
    <td style="text-align:right">{sip}</td>
    <td style="text-align:right">{er}</td>
    <td style="text-align:center">{rating}</td>
    <td>{_esc(a.rationale)}</td>
</tr>"""

    # Projected returns
    bear = plan.projected_returns.get("bear", 0.0)
    base = plan.projected_returns.get("base", 0.0)
    bull = plan.projected_returns.get("bull", 0.0)

    # Risks
    risks_html = ""
    if plan.risks:
        risk_items = "".join(f"<li class='risk-item'>{_esc(r)}</li>" for r in plan.risks)
        risks_html = f"""
<div class="section-title">Key Risks</div>
<ul>{risk_items}</ul>"""

    # Review checkpoints
    checkpoints_html = ""
    if plan.review_checkpoints:
        cp_items = "".join(f"<li>{_esc(c)}</li>" for c in plan.review_checkpoints)
        checkpoints_html = f"""
<div class="section-title">Review Checkpoints</div>
<ul>{cp_items}</ul>"""

    return f"""<div class="plan-html">
<div class="section-title">Fund Allocations</div>
<table>
    <tr>
        <th>Fund</th><th>Fund House</th><th style="text-align:right">%</th>
        <th style="text-align:center">Mode</th><th style="text-align:right">SIP/mo</th>
        <th style="text-align:right">ER</th><th style="text-align:center">Rating</th>
        <th>Rationale</th>
    </tr>
    {alloc_rows}
</table>

<div class="section-title">Projected Returns (CAGR)</div>
<div class="stat-row">
    <div class="stat-box bear"><div class="label">Bear</div><div class="value">{bear:.1f}%</div></div>
    <div class="stat-box base"><div class="label">Base</div><div class="value">{base:.1f}%</div></div>
    <div class="stat-box bull"><div class="label">Bull</div><div class="value">{bull:.1f}%</div></div>
</div>

<div class="section-title">Rationale</div>
<div class="rationale-box">{_esc(plan.rationale)}</div>

{risks_html}

{checkpoints_html}

{f'<div class="section-title">Rebalancing Guidelines</div><div class="rationale-box">{_esc(plan.rebalancing_guidelines)}</div>' if plan.rebalancing_guidelines else ''}

{f'<div class="section-title">Setup Phase</div><div class="rationale-box">{_esc(plan.setup_phase)}</div>' if plan.setup_phase else ''}

<p style="font-size:0.8rem;color:#999;margin-top:1rem;font-style:italic">{_esc(plan.disclaimer)}</p>
</div>"""


def render_conversation_html(conv: ConversationLog) -> str:
    """Render a saved conversation as HTML."""
    parts = [f'<div class="plan-html">']
    parts.append(
        f'<div class="section-title">Conversation: {_esc(conv.id)}</div>'
        f'<p style="color:#777;font-size:0.85rem">'
        f'{conv.timestamp:%Y-%m-%d %H:%M} UTC &mdash; Model: {_esc(conv.model)}</p>'
    )

    if conv.profile:
        parts.append(render_profile_html(conv.profile))

    if conv.profile_turns:
        parts.append(f'<div class="section-title">Profile Conversation ({len(conv.profile_turns)} turns)</div>')
        for turn in conv.profile_turns:
            role_label = "Advisor" if turn.role == "advisor" else "You"
            color = "#667eea" if turn.role == "advisor" else "#27ae60"
            parts.append(
                f'<p><strong style="color:{color}">{role_label}:</strong> {_esc(turn.content)}</p>'
            )

    if conv.strategy:
        parts.append(render_strategy_html(conv.strategy))

    if conv.strategy_revisions:
        parts.append(f'<div class="section-title">Strategy Revisions ({len(conv.strategy_revisions)} rounds)</div>')
        for turn in conv.strategy_revisions:
            parts.append(f'<p><strong style="color:#27ae60">You:</strong> {_esc(turn.content)}</p>')

    if conv.plan:
        parts.append(render_plan_html(conv.plan))

    parts.append("</div>")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Persona loading
# ---------------------------------------------------------------------------

def _load_persona_choices() -> list[tuple[str, str]]:
    """Load personas and return (display_label, id) tuples."""
    try:
        personas = load_personas()
        return [(f"{p.id} - {p.name} ({p.age}, {p.risk_appetite})", p.id) for p in personas]
    except Exception:
        logger.warning("Failed to load persona bank", exc_info=True)
        return []


def _get_persona_by_id(pid: str) -> InvestorProfile | None:
    """Load a single persona by ID, returning None on failure."""
    try:
        personas = load_personas()
        for p in personas:
            if p.id == pid:
                return p
    except Exception:
        logger.warning("Failed to load persona %s", pid, exc_info=True)
    return None


# ---------------------------------------------------------------------------
# Conversation persistence
# ---------------------------------------------------------------------------

def _save_conversation(conv: ConversationLog) -> Path:
    """Save a conversation log to disk."""
    CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)
    path = CONVERSATIONS_DIR / f"{conv.id}.json"
    path.write_text(conv.model_dump_json(indent=2))
    return path


def _list_conversations() -> list[dict[str, Any]]:
    """List saved conversations as metadata dicts."""
    if not CONVERSATIONS_DIR.exists():
        return []
    convs = []
    for f in sorted(CONVERSATIONS_DIR.glob("*.json"), reverse=True):
        try:
            data = json.loads(f.read_text())
            name = data.get("profile", {}).get("name", "Unknown") if data.get("profile") else "Unknown"
            convs.append({
                "id": data.get("id", f.stem),
                "timestamp": data.get("timestamp", ""),
                "model": data.get("model", ""),
                "profile_name": name,
                "path": str(f),
            })
        except Exception:
            continue
    return convs


# ---------------------------------------------------------------------------
# Gradio app factory
# ---------------------------------------------------------------------------

def create_app() -> gr.Blocks:
    """Create and return the Gradio Blocks app."""

    persona_choices = _load_persona_choices()

    with gr.Blocks(title="Subprime Financial Advisor") as demo:

        # -- State --
        state_profile = gr.State(value=None)
        state_strategy = gr.State(value=None)
        state_plan = gr.State(value=None)
        state_conv = gr.State(value=None)

        # -- Embedded CSS + Header --
        gr.HTML(
            f"<style>{CSS}</style>"
            '<div class="subprime-header">'
            "<h1>Subprime Financial Advisor</h1>"
            "<p>AI-powered mutual fund advisory for Indian investors</p>"
            "</div>"
        )

        with gr.Tabs():

            # ==============================================================
            # TAB 1: ADVISOR
            # ==============================================================
            with gr.Tab("Advisor"):

                # -- Profile section --
                gr.Markdown("### Select or describe an investor profile")

                with gr.Row():
                    persona_dropdown = gr.Dropdown(
                        choices=persona_choices,
                        label="Choose a persona",
                        interactive=True,
                    )
                    use_profile_btn = gr.Button("Use Profile", variant="primary")

                profile_html = gr.HTML(label="Profile", visible=False)

                # -- Strategy section --
                strategy_section = gr.Group(visible=False)
                with strategy_section:
                    gr.Markdown("### Investment Strategy")
                    strategy_html = gr.HTML()
                    with gr.Row():
                        feedback_input = gr.Textbox(
                            label="Feedback (optional adjustments)",
                            placeholder="e.g. Increase equity allocation, add international exposure...",
                            scale=4,
                        )
                        revise_btn = gr.Button("Revise Strategy", scale=1)
                    generate_plan_btn = gr.Button(
                        "Generate Detailed Plan", variant="primary"
                    )

                # -- Plan section --
                plan_section = gr.Group(visible=False)
                with plan_section:
                    gr.Markdown("### Investment Plan")
                    plan_html = gr.HTML()

                # -- Status --
                status_msg = gr.Markdown("")

                # ---- Event handlers ----

                def on_use_profile(persona_id: str | None, conv_state):
                    """Load selected persona and generate initial strategy."""
                    if not persona_id:
                        return (
                            gr.update(),  # profile_html
                            gr.update(),  # strategy_section
                            gr.update(),  # strategy_html
                            gr.update(),  # plan_section
                            "**Please select a persona first.**",  # status
                            None,  # state_profile
                            None,  # state_strategy
                            None,  # state_plan
                            None,  # state_conv
                        )

                    profile = _get_persona_by_id(persona_id)
                    if profile is None:
                        return (
                            gr.update(),
                            gr.update(),
                            gr.update(),
                            gr.update(),
                            f"**Persona {persona_id} not found.**",
                            None,
                            None,
                            None,
                            None,
                        )

                    # Start conversation log
                    conv = ConversationLog(model="anthropic:claude-haiku-4-5")
                    conv.profile = profile

                    # Generate strategy
                    try:
                        strategy = asyncio.run(generate_strategy(profile))
                    except Exception as exc:
                        logger.exception("Strategy generation failed")
                        return (
                            gr.update(value=render_profile_html(profile), visible=True),
                            gr.update(visible=False),
                            gr.update(),
                            gr.update(visible=False),
                            f"**Error generating strategy:** {exc}",
                            profile,
                            None,
                            None,
                            conv,
                        )

                    conv.strategy = strategy

                    return (
                        gr.update(value=render_profile_html(profile), visible=True),
                        gr.update(visible=True),
                        gr.update(value=render_strategy_html(strategy)),
                        gr.update(visible=False),
                        "",
                        profile,
                        strategy,
                        None,
                        conv,
                    )

                use_profile_btn.click(
                    fn=on_use_profile,
                    inputs=[persona_dropdown, state_conv],
                    outputs=[
                        profile_html,
                        strategy_section,
                        strategy_html,
                        plan_section,
                        status_msg,
                        state_profile,
                        state_strategy,
                        state_plan,
                        state_conv,
                    ],
                )

                def on_revise_strategy(
                    feedback: str,
                    profile: InvestorProfile | None,
                    strategy: StrategyOutline | None,
                    conv: ConversationLog | None,
                ):
                    """Revise the strategy based on user feedback."""
                    if not profile or not strategy:
                        return (
                            gr.update(),
                            "**No active strategy to revise.**",
                            strategy,
                            conv,
                        )
                    if not feedback.strip():
                        return (
                            gr.update(),
                            "**Please enter feedback to revise the strategy.**",
                            strategy,
                            conv,
                        )

                    try:
                        new_strategy = asyncio.run(
                            generate_strategy(
                                profile,
                                feedback=feedback,
                                current_strategy=strategy,
                            )
                        )
                    except Exception as exc:
                        logger.exception("Strategy revision failed")
                        return (
                            gr.update(),
                            f"**Error revising strategy:** {exc}",
                            strategy,
                            conv,
                        )

                    if conv:
                        conv.strategy_revisions.append(
                            ConversationTurn(role="user", content=feedback)
                        )
                        conv.strategy = new_strategy

                    return (
                        gr.update(value=render_strategy_html(new_strategy)),
                        "",
                        new_strategy,
                        conv,
                    )

                revise_btn.click(
                    fn=on_revise_strategy,
                    inputs=[feedback_input, state_profile, state_strategy, state_conv],
                    outputs=[strategy_html, status_msg, state_strategy, state_conv],
                )

                def on_generate_plan(
                    profile: InvestorProfile | None,
                    strategy: StrategyOutline | None,
                    conv: ConversationLog | None,
                ):
                    """Generate detailed investment plan."""
                    if not profile or not strategy:
                        return (
                            gr.update(),
                            gr.update(),
                            "**No profile or strategy available.**",
                            None,
                            conv,
                        )

                    try:
                        plan = asyncio.run(
                            generate_plan(profile, strategy=strategy)
                        )
                    except Exception as exc:
                        logger.exception("Plan generation failed")
                        return (
                            gr.update(visible=False),
                            gr.update(),
                            f"**Error generating plan:** {exc}",
                            None,
                            conv,
                        )

                    if conv:
                        conv.plan = plan
                        try:
                            saved = _save_conversation(conv)
                            logger.info("Conversation saved to %s", saved)
                        except Exception:
                            logger.warning("Failed to save conversation", exc_info=True)

                    return (
                        gr.update(visible=True),
                        gr.update(value=render_plan_html(plan)),
                        "",
                        plan,
                        conv,
                    )

                generate_plan_btn.click(
                    fn=on_generate_plan,
                    inputs=[state_profile, state_strategy, state_conv],
                    outputs=[plan_section, plan_html, status_msg, state_plan, state_conv],
                )

            # ==============================================================
            # TAB 2: CONVERSATIONS
            # ==============================================================
            with gr.Tab("Conversations"):
                gr.Markdown("### Saved Conversations")
                refresh_btn = gr.Button("Refresh", size="sm")
                conv_dropdown = gr.Dropdown(
                    choices=[],
                    label="Select a conversation",
                    interactive=True,
                )
                conv_display = gr.HTML()

                def on_refresh_conversations():
                    """Reload conversation list."""
                    convs = _list_conversations()
                    if not convs:
                        return gr.update(choices=[], value=None), "<p style='color:#888'>No saved conversations found.</p>"
                    choices = [
                        (f"{c['id']} - {c['profile_name']} ({c['model']})", c["path"])
                        for c in convs
                    ]
                    return gr.update(choices=choices, value=None), ""

                refresh_btn.click(
                    fn=on_refresh_conversations,
                    inputs=[],
                    outputs=[conv_dropdown, conv_display],
                )

                def on_select_conversation(path: str | None):
                    """Display a selected conversation."""
                    if not path:
                        return ""
                    try:
                        conv = ConversationLog.model_validate_json(Path(path).read_text())
                        return render_conversation_html(conv)
                    except Exception as exc:
                        logger.warning("Failed to load conversation %s", path, exc_info=True)
                        return f"<p style='color:red'>Error loading conversation: {exc}</p>"

                conv_dropdown.change(
                    fn=on_select_conversation,
                    inputs=[conv_dropdown],
                    outputs=[conv_display],
                )

                # Auto-load on tab view
                demo.load(
                    fn=on_refresh_conversations,
                    inputs=[],
                    outputs=[conv_dropdown, conv_display],
                )

    return demo


if __name__ == "__main__":
    app = create_app()
    app.launch(server_port=7860)
