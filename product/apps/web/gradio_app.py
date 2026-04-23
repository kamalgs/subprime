"""Gradio web interface for Subprime financial advisor — conversational chat."""

from __future__ import annotations

import asyncio
import logging

import gradio as gr
from dotenv import load_dotenv

load_dotenv()

from subprime.advisor.planner import generate_plan, generate_strategy
from subprime.core.models import (
    ConversationLog,
    ConversationTurn,
    InvestmentPlan,
    InvestorProfile,
    StrategyOutline,
)
from subprime.evaluation.personas import load_personas

logger = logging.getLogger("subprime.web")

from subprime.core.config import CONVERSATIONS_DIR

# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

CSS = """
.subprime-chat { max-width: 800px; margin: 0 auto; }
.plan-table { width: 100%; border-collapse: collapse; margin: 0.5rem 0; font-size: 0.88rem; }
.plan-table th { background: #f4f4f8; text-align: left; padding: 6px 10px; border-bottom: 2px solid #ddd; font-weight: 600; }
.plan-table td { padding: 6px 10px; border-bottom: 1px solid #eee; vertical-align: top; }
.plan-table tr:hover td { background: #fafaff; }
.stat-row { display: flex; gap: 1rem; margin: 0.5rem 0; }
.stat-box { background: #f8f8fc; border: 1px solid #e0e0e8; border-radius: 6px; padding: 6px 14px; text-align: center; }
.stat-box .label { font-size: 0.7rem; color: #888; text-transform: uppercase; }
.stat-box .value { font-size: 1rem; font-weight: 600; }
.stat-box.bear .value { color: #c0392b; }
.stat-box.base .value { color: #d4a017; }
.stat-box.bull .value { color: #27ae60; }
.info-box { background: #f8f8fc; border-left: 3px solid #667eea; padding: 8px 12px; margin: 6px 0; font-size: 0.9rem; line-height: 1.5; }
.section-title { font-weight: 600; font-size: 0.95rem; color: #1a1a2e; margin: 10px 0 4px 0; border-bottom: 1px solid #eee; padding-bottom: 2px; }
"""


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_profile_html(p: InvestorProfile) -> str:
    goals = ", ".join(_esc(g) for g in p.financial_goals)
    return (
        f'<div class="section-title">Investor Profile</div>'
        f'<table class="plan-table">'
        f"<tr><th>Name</th><td>{_esc(p.name)}, {p.age}y</td>"
        f"<th>Risk</th><td>{p.risk_appetite.title()}</td></tr>"
        f"<tr><th>Horizon</th><td>{p.investment_horizon_years} years</td>"
        f"<th>SIP Budget</th><td>&#8377;{p.monthly_investible_surplus_inr:,.0f}/mo</td></tr>"
        f"<tr><th>Goals</th><td colspan='3'>{goals}</td></tr>"
        f"</table>"
    )


def render_strategy_html(s: StrategyOutline) -> str:
    alloc = (
        f"<strong>Equity {s.equity_pct:.0f}%</strong> / "
        f"Debt {s.debt_pct:.0f}% / Gold {s.gold_pct:.0f}%"
    )
    if s.other_pct > 0:
        alloc += f" / Other {s.other_pct:.0f}%"

    themes = ", ".join(_esc(t) for t in s.key_themes)

    questions = ""
    if s.open_questions:
        items = "".join(f"<li>{_esc(q)}</li>" for q in s.open_questions)
        questions = f'<div class="section-title">Open Questions</div><ul style="margin:4px 0;padding-left:1.2rem">{items}</ul>'

    return (
        f'<div class="section-title">Strategy Outline</div>'
        f"<p>{alloc}</p>"
        f'<div class="info-box"><strong>Approach:</strong> {_esc(s.equity_approach)}</div>'
        f"<p><strong>Themes:</strong> {themes}</p>"
        f"<p><strong>Expected:</strong> {_esc(s.risk_return_summary)}</p>"
        f"{questions}"
        f"<p><em>Type <strong>yes</strong> to proceed with fund selection, "
        f"or tell me what to adjust.</em></p>"
    )


def _format_inr_html(amount: float) -> str:
    """Format INR amount in lakhs/crores notation for HTML."""
    if amount >= 1_00_00_000:  # 1 crore
        return f"&#8377;{amount / 1_00_00_000:.2f} Cr"
    elif amount >= 1_00_000:  # 1 lakh
        return f"&#8377;{amount / 1_00_000:.2f} L"
    else:
        return f"&#8377;{amount:,.0f}"


def _compute_corpus_html(monthly_sip: float, years: int, cagr_pct: float) -> float:
    """Compute future value of monthly SIP at given CAGR."""
    if cagr_pct <= 0 or monthly_sip <= 0 or years <= 0:
        return 0.0
    r = cagr_pct / 100 / 12
    n = years * 12
    return monthly_sip * (((1 + r) ** n - 1) / r) * (1 + r)


def _inflation_adjusted_html(future_value: float, years: int, inflation_pct: float = 6.0) -> float:
    """Discount future value to today's terms."""
    if years <= 0:
        return future_value
    return future_value / ((1 + inflation_pct / 100) ** years)


def render_plan_html(
    plan: InvestmentPlan,
    monthly_sip: float | None = None,
    horizon_years: int | None = None,
) -> str:
    # Summary stats
    n_funds = len(plan.allocations)
    houses = {a.fund.fund_house for a in plan.allocations if a.fund.fund_house}
    total_sip = sum(a.monthly_sip_inr or 0 for a in plan.allocations)
    bear = plan.projected_returns.get("bear", 0)
    base = plan.projected_returns.get("base", 0)
    bull = plan.projected_returns.get("bull", 0)
    has_returns = any(v > 0 for v in (bear, base, bull))

    stat_boxes = (
        f'<div class="stat-box"><div class="label">Funds</div><div class="value">{n_funds}</div></div>'
        f'<div class="stat-box"><div class="label">Fund Houses</div><div class="value">{len(houses)}</div></div>'
        f'<div class="stat-box"><div class="label">Monthly SIP</div><div class="value">{_format_inr_html(total_sip)}</div></div>'
    )
    if has_returns:
        stat_boxes += (
            f'<div class="stat-box bear"><div class="label">Bear</div><div class="value">{bear:.1f}%</div></div>'
            f'<div class="stat-box base"><div class="label">Base</div><div class="value">{base:.1f}%</div></div>'
            f'<div class="stat-box bull"><div class="label">Bull</div><div class="value">{bull:.1f}%</div></div>'
        )

    stats = f'<div class="stat-row">{stat_boxes}</div>'

    # Allocations table
    rows = ""
    for a in plan.allocations:
        sip = _format_inr_html(a.monthly_sip_inr) if a.monthly_sip_inr else "-"
        er = f"{a.fund.expense_ratio:.2f}%" if a.fund.expense_ratio else "-"
        stars = ("&#9733;" * a.fund.morningstar_rating) if a.fund.morningstar_rating else "-"
        rows += (
            f"<tr><td><strong>{_esc(a.fund.name)}</strong>"
            f'<br><span style="color:#888;font-size:0.8rem">'
            f"{_esc(a.fund.fund_house or '')} | {_esc(a.fund.amfi_code)}</span></td>"
            f'<td style="text-align:right">{a.allocation_pct:.0f}%</td>'
            f"<td>{a.mode}</td>"
            f'<td style="text-align:right">{sip}</td>'
            f'<td style="text-align:right">{er}</td>'
            f'<td style="text-align:center">{stars}</td></tr>'
        )

    table = (
        f'<table class="plan-table">'
        f'<tr><th>Fund</th><th style="text-align:right">%</th><th>Mode</th>'
        f'<th style="text-align:right">SIP/mo</th><th style="text-align:right">ER</th>'
        f'<th style="text-align:center">Rating</th></tr>'
        f"{rows}</table>"
    )

    # Corpus projection table
    corpus_html = ""
    effective_sip = monthly_sip if monthly_sip else total_sip
    effective_horizon = horizon_years or 0
    if has_returns and effective_sip > 0 and effective_horizon > 0:
        corpus_rows = ""
        for label, cagr, color in [
            ("Bear", bear, "#c0392b"),
            ("Base", base, "#d4a017"),
            ("Bull", bull, "#27ae60"),
        ]:
            if cagr > 0:
                fv = _compute_corpus_html(effective_sip, effective_horizon, cagr)
                pv = _inflation_adjusted_html(fv, effective_horizon)
                corpus_rows += (
                    f'<tr><td style="color:{color};font-weight:600">{label}</td>'
                    f'<td style="text-align:right">{cagr:.1f}%</td>'
                    f'<td style="text-align:right">{_format_inr_html(fv)}</td>'
                    f'<td style="text-align:right">{_format_inr_html(pv)}</td></tr>'
                )
        if corpus_rows:
            corpus_html = (
                f'<div class="section-title">Projected Corpus '
                f"(SIP {_format_inr_html(effective_sip)}/mo over {effective_horizon} years)</div>"
                f'<table class="plan-table">'
                f'<tr><th>Scenario</th><th style="text-align:right">CAGR</th>'
                f'<th style="text-align:right">Future Value</th>'
                f'<th style="text-align:right">In Today\'s &#8377;</th></tr>'
                f"{corpus_rows}</table>"
            )

    # Rationale (always visible)
    rationale = f'<div class="info-box">{_esc(plan.rationale)}</div>' if plan.rationale else ""

    # Risks (collapsible)
    risks = ""
    if plan.risks:
        items = "".join(f"<li>{_esc(r)}</li>" for r in plan.risks)
        risks = (
            f"<details><summary><strong>Risks</strong></summary>"
            f'<ul style="margin:4px 0;padding-left:1.2rem">{items}</ul>'
            f"</details>"
        )

    # Getting Started (collapsible)
    setup = ""
    if plan.setup_phase:
        setup = (
            f"<details><summary><strong>Getting Started</strong></summary>"
            f'<div class="info-box">{_esc(plan.setup_phase)}</div>'
            f"</details>"
        )

    # Rebalancing Guidelines (collapsible)
    rebalancing = ""
    if plan.rebalancing_guidelines:
        rebalancing = (
            f"<details><summary><strong>Rebalancing Guidelines</strong></summary>"
            f'<div class="info-box">{_esc(plan.rebalancing_guidelines)}</div>'
            f"</details>"
        )

    disclaimer = (
        f'<p style="font-size:0.78rem;color:#999;margin-top:10px;font-style:italic">'
        f"{_esc(plan.disclaimer)}</p>"
    )

    return (
        f'<div class="section-title">Your Investment Plan</div>'
        f"{stats}{corpus_html}{table}"
        f'<div class="section-title">Why This Plan</div>{rationale}'
        f"{risks}{setup}{rebalancing}{disclaimer}"
    )


# ---------------------------------------------------------------------------
# Chat logic
# ---------------------------------------------------------------------------

# Conversation phases
PHASE_PROFILE = "profile"
PHASE_STRATEGY = "strategy"
PHASE_PLAN_READY = "plan_ready"
PHASE_DONE = "done"


def _make_state() -> dict:
    return {
        "phase": PHASE_PROFILE,
        "profile": None,
        "strategy": None,
        "plan": None,
        "conv": ConversationLog(model="chat"),
        "profile_turns": [],
        "awaiting_profile_input": True,
        "mode": "basic",
    }


def _opening_message() -> str:
    personas = load_personas()
    options = " / ".join(f"`{p.id}`" for p in personas)
    return (
        "Welcome! I'm FinAdvisor, your mutual fund advisor for the Indian market.\n\n"
        f"You can pick a persona ({options}) or just tell me about yourself — "
        "your age, how much you can invest monthly, goals, and time horizon."
    )


def _process_message(user_msg: str, history: list, state: dict) -> tuple[list, dict, str]:
    """Process a user message and return (updated_history, updated_state, status)."""
    phase = state["phase"]

    if phase == PHASE_PROFILE:
        return _handle_profile_phase(user_msg, history, state)
    elif phase == PHASE_STRATEGY:
        return _handle_strategy_phase(user_msg, history, state)
    elif phase == PHASE_PLAN_READY:
        return _handle_plan_phase(user_msg, history, state)
    else:
        history.append(
            {
                "role": "assistant",
                "content": "The session is complete. Start a new chat to begin again.",
            }
        )
        return history, state, ""


def _handle_profile_phase(user_msg: str, history: list, state: dict) -> tuple[list, dict, str]:
    # Check if user selected a persona
    try:
        personas = load_personas()
        persona_ids = {p.id.lower(): p for p in personas}
        if user_msg.strip().upper() in {p.id for p in personas}:
            profile = persona_ids[user_msg.strip().lower()]
            state["profile"] = profile
            state["conv"].profile = profile
            state["phase"] = PHASE_STRATEGY

            # Generate strategy
            html = render_profile_html(profile)
            history.append(
                {"role": "assistant", "content": f"Using profile **{profile.name}**.\n\n{html}"}
            )

            strategy = asyncio.run(generate_strategy(profile))
            state["strategy"] = strategy
            state["conv"].strategy = strategy

            html = render_strategy_html(strategy)
            history.append({"role": "assistant", "content": html})
            return history, state, ""
    except Exception:
        pass

    # Interactive profile: collect info, extract after 2 turns
    state["profile_turns"].append(user_msg)

    if len(state["profile_turns"]) < 2:
        # Ask one follow-up
        history.append(
            {
                "role": "assistant",
                "content": (
                    "Thanks! A couple more things — what's your risk comfort level "
                    "(conservative / moderate / aggressive), and do you have any "
                    "existing investments or liabilities?"
                ),
            }
        )
        return history, state, ""

    # Extract profile from conversation
    conversation_text = "\n".join(f"User: {t}" for t in state["profile_turns"])
    try:
        extractor_agent = __import__("pydantic_ai", fromlist=["Agent"]).Agent
        from subprime.core.config import DEFAULT_MODEL

        extractor = extractor_agent(
            DEFAULT_MODEL,
            system_prompt=(
                "Extract an InvestorProfile from this conversation. "
                "Use 'interactive' as the id. Infer reasonable defaults for missing fields."
            ),
            output_type=InvestorProfile,
            retries=2,
            defer_model_check=True,
        )
        result = asyncio.run(extractor.run(conversation_text))
        profile = result.output
    except Exception as exc:
        logger.exception("Profile extraction failed")
        history.append(
            {
                "role": "assistant",
                "content": f"Sorry, I had trouble understanding that. Could you try again? ({exc})",
            }
        )
        state["profile_turns"] = []
        return history, state, ""

    state["profile"] = profile
    state["conv"].profile = profile
    state["phase"] = PHASE_STRATEGY

    html = render_profile_html(profile)
    history.append(
        {
            "role": "assistant",
            "content": f"Here's what I gathered:\n\n{html}\n\nLet me work on a strategy...",
        }
    )

    # Generate strategy
    try:
        strategy = asyncio.run(generate_strategy(profile))
        state["strategy"] = strategy
        state["conv"].strategy = strategy

        html = render_strategy_html(strategy)
        history.append({"role": "assistant", "content": html})
    except Exception as exc:
        logger.exception("Strategy generation failed")
        history.append({"role": "assistant", "content": f"Error generating strategy: {exc}"})

    return history, state, ""


def _handle_strategy_phase(user_msg: str, history: list, state: dict) -> tuple[list, dict, str]:
    if user_msg.strip().lower() in ("yes", "y", "go ahead", "proceed", "ok", "sure"):
        state["phase"] = PHASE_PLAN_READY
        plan_mode = state.get("mode", "basic")
        if plan_mode == "premium":
            from subprime.advisor.perspectives import get_default_perspectives

            n_perspectives = state.get("n_perspectives", 3)
            perspective_list = get_default_perspectives(n_perspectives)
            names = [p.description for p in perspective_list]
            bullets = "\n".join(f"- {n}" for n in names)
            history.append(
                {
                    "role": "assistant",
                    "content": f"Generating {n_perspectives} perspectives and comparing:\n{bullets}",
                }
            )
        else:
            n_perspectives = 3
            history.append(
                {"role": "assistant", "content": "Finding specific funds for your strategy..."}
            )

        try:
            plan = asyncio.run(
                generate_plan(
                    state["profile"],
                    strategy=state["strategy"],
                    mode=plan_mode,
                    n_perspectives=n_perspectives,
                )
            )
            state["plan"] = plan
            state["conv"].plan = plan
            state["phase"] = PHASE_DONE

            # Save conversation
            try:
                CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)
                path = CONVERSATIONS_DIR / f"{state['conv'].id}.json"
                path.write_text(state["conv"].model_dump_json(indent=2))
            except Exception:
                pass

            profile = state.get("profile")
            html = render_plan_html(
                plan,
                monthly_sip=profile.monthly_investible_surplus_inr if profile else None,
                horizon_years=profile.investment_horizon_years if profile else None,
            )
            history.append({"role": "assistant", "content": html})
        except Exception as exc:
            logger.exception("Plan generation failed")
            state["phase"] = PHASE_STRATEGY
            history.append(
                {
                    "role": "assistant",
                    "content": f"Error generating plan: {exc}\n\nYou can try again — type **yes** to retry.",
                }
            )

        return history, state, ""

    # Revise strategy
    state["conv"].strategy_revisions.append(ConversationTurn(role="user", content=user_msg))

    try:
        strategy = asyncio.run(
            generate_strategy(
                state["profile"],
                feedback=user_msg,
                current_strategy=state["strategy"],
            )
        )
        state["strategy"] = strategy
        state["conv"].strategy = strategy

        html = render_strategy_html(strategy)
        history.append({"role": "assistant", "content": html})
    except Exception as exc:
        logger.exception("Strategy revision failed")
        history.append({"role": "assistant", "content": f"Error revising strategy: {exc}"})

    return history, state, ""


def _handle_plan_phase(user_msg: str, history: list, state: dict) -> tuple[list, dict, str]:
    history.append(
        {
            "role": "assistant",
            "content": "Your plan is ready above. Start a new chat to begin again.",
        }
    )
    state["phase"] = PHASE_DONE
    return history, state, ""


# ---------------------------------------------------------------------------
# Gradio app
# ---------------------------------------------------------------------------


def create_app() -> gr.Blocks:
    with gr.Blocks(title="FinAdvisor") as demo:
        state = gr.State(_make_state)

        gr.HTML(
            '<div style="text-align:center;padding:12px 0 4px 0">'
            '<h2 style="margin:0">FinAdvisor</h2>'
            '<p style="margin:2px 0 0 0;color:#666;font-size:0.9rem">'
            "AI-powered mutual fund advisory for Indian investors</p>"
            '<p style="margin:4px 0 0 0;color:#c0392b;font-size:0.78rem">'
            "&#9888; For educational and research purposes only. Not SEBI-registered investment advice. "
            "Please consult a certified financial advisor before making investment decisions.</p></div>"
        )

        chatbot = gr.Chatbot(
            value=[{"role": "assistant", "content": _opening_message()}],
            height=550,
        )

        with gr.Row():
            msg_input = gr.Textbox(
                placeholder="Type your message...",
                show_label=False,
                scale=5,
                container=False,
            )
            mode_radio = gr.Radio(
                choices=["basic", "premium"],
                value="basic",
                label="Plan Mode",
                scale=2,
            )
            send_btn = gr.Button("Send", variant="primary", scale=1)

        status = gr.Markdown("")

        def respond(user_msg: str, history: list, st: dict, plan_mode: str):
            if not user_msg.strip():
                return history, st, "", ""
            st["mode"] = plan_mode
            history.append({"role": "user", "content": user_msg})
            history, st, status_text = _process_message(user_msg, history, st)
            return history, st, "", status_text

        send_btn.click(
            fn=respond,
            inputs=[msg_input, chatbot, state, mode_radio],
            outputs=[chatbot, state, msg_input, status],
        )
        msg_input.submit(
            fn=respond,
            inputs=[msg_input, chatbot, state, mode_radio],
            outputs=[chatbot, state, msg_input, status],
        )

    return demo


if __name__ == "__main__":
    app = create_app()
    app.launch(server_port=7860, css=CSS)
