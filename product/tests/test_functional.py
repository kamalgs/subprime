"""Functional smoke tests for CLI commands and web app.

These run WITHOUT mocks (except LLM calls) and catch regressions like
import errors, API compat issues, and launch failures. They run as part
of the normal test suite (not e2e) — no real API keys needed.

The Gradio 6.x breakage would have been caught by test_web_app_creates.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic_ai.usage import RunUsage
from typer.testing import CliRunner

from subprime.cli import app
from subprime.core.models import (
    Allocation,
    InvestmentPlan,
    InvestorProfile,
    MutualFund,
    StrategyOutline,
)

runner = CliRunner()


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _fake_strategy() -> StrategyOutline:
    return StrategyOutline(
        equity_pct=70.0, debt_pct=20.0, gold_pct=10.0, other_pct=0.0,
        equity_approach="Index-heavy",
        key_themes=["low cost", "broad diversification"],
        risk_return_summary="12-14% CAGR",
        open_questions=[],
    )


def _fake_plan() -> InvestmentPlan:
    return InvestmentPlan(
        allocations=[
            Allocation(
                fund=MutualFund(
                    amfi_code="120503", name="UTI Nifty 50 Index Fund",
                    category="Large Cap", sub_category="Index",
                    fund_house="UTI Mutual Fund", nav=150.0, expense_ratio=0.18,
                    morningstar_rating=4,
                ),
                allocation_pct=60.0, mode="sip",
                monthly_sip_inr=30000, rationale="Core index holding",
            ),
            Allocation(
                fund=MutualFund(
                    amfi_code="122639", name="Parag Parikh Flexi Cap Fund",
                    category="Flexi Cap", sub_category="Flexi Cap",
                    fund_house="PPFAS Mutual Fund", nav=88.0, expense_ratio=0.63,
                    morningstar_rating=5,
                ),
                allocation_pct=40.0, mode="sip",
                monthly_sip_inr=20000, rationale="Active diversified exposure",
            ),
        ],
        setup_phase="Start SIPs in month 1",
        review_checkpoints=["6-month review"],
        rebalancing_guidelines="Annual rebalancing if drift > 5%",
        projected_returns={"base": 12.0, "bull": 16.0, "bear": 6.0},
        rationale="Balanced index-core with active satellite",
        risks=["Market risk", "Currency risk"],
        disclaimer="For research purposes only.",
    )


# ===========================================================================
# CLI: subprime advise
# ===========================================================================


class TestCLIAdvise:
    """Functional tests for the advise command — verifies the full flow works."""

    def test_advise_help(self):
        result = runner.invoke(app, ["advise", "--help"])
        assert result.exit_code == 0
        assert "--profile" in result.output
        assert "--model" in result.output

    def test_advise_bulk_flow_renders_profile_strategy_plan(self):
        """Full bulk flow: profile → strategy → plan, verify output contains key sections."""
        with (
            patch("subprime.cli.generate_strategy", new_callable=AsyncMock, return_value=(_fake_strategy(), RunUsage())),
            patch("subprime.cli.generate_plan", new_callable=AsyncMock, return_value=(_fake_plan(), RunUsage())),
        ):
            result = runner.invoke(app, ["advise", "--profile", "P01"], input="yes\n")

        assert result.exit_code == 0
        # Profile phase
        assert "Tony Stark" in result.output
        # Strategy phase
        assert "70" in result.output  # equity %
        # Plan phase — fund names rendered
        assert "UTI Nifty 50" in result.output or "Nifty 50" in result.output

    def test_advise_strategy_revision_then_approve(self):
        """User revises strategy once, then approves."""
        revised_strategy = StrategyOutline(
            equity_pct=80.0, debt_pct=15.0, gold_pct=5.0, other_pct=0.0,
            equity_approach="More aggressive equity tilt",
            key_themes=["growth", "mid cap"],
            risk_return_summary="14-16% CAGR",
            open_questions=[],
        )

        call_count = 0

        async def mock_generate_strategy(profile, feedback=None, current_strategy=None, **kw):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _fake_strategy(), RunUsage()
            return revised_strategy, RunUsage()

        with (
            patch("subprime.cli.generate_strategy", side_effect=mock_generate_strategy),
            patch("subprime.cli.generate_plan", new_callable=AsyncMock, return_value=(_fake_plan(), RunUsage())),
        ):
            result = runner.invoke(
                app, ["advise", "--profile", "P01"],
                input="more equity\nyes\n",
            )

        assert result.exit_code == 0
        assert call_count == 2  # initial + revision

    def test_advise_saves_conversation(self, tmp_path, monkeypatch):
        """Conversation should be saved after successful advise."""
        monkeypatch.setattr("subprime.core.config.CONVERSATIONS_DIR", tmp_path)

        with (
            patch("subprime.cli.generate_strategy", new_callable=AsyncMock, return_value=(_fake_strategy(), RunUsage())),
            patch("subprime.cli.generate_plan", new_callable=AsyncMock, return_value=(_fake_plan(), RunUsage())),
        ):
            result = runner.invoke(app, ["advise", "--profile", "P01"], input="yes\n")

        assert result.exit_code == 0
        saved = list(tmp_path.glob("*.json"))
        assert len(saved) >= 1

    def test_advise_invalid_profile_id(self):
        """Invalid profile ID should produce an error, not crash."""
        result = runner.invoke(app, ["advise", "--profile", "INVALID_XYZ"])
        assert result.exit_code != 0 or "error" in result.output.lower()

    def test_advise_no_api_key_shows_error(self, monkeypatch):
        """Missing API key should show a clear error, not a traceback."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        result = runner.invoke(app, ["advise", "--profile", "P01"])
        assert result.exit_code != 0
        assert "ANTHROPIC_API_KEY" in result.output


# ===========================================================================
# CLI: subprime replay
# ===========================================================================


class TestCLIReplay:
    def test_replay_help(self):
        result = runner.invoke(app, ["replay", "--help"])
        assert result.exit_code == 0

    def test_replay_missing_file(self):
        result = runner.invoke(app, ["replay", "/nonexistent/path.json"])
        assert result.exit_code != 0

    def test_replay_valid_conversation(self, tmp_path):
        """Replay should render a saved conversation without errors."""
        from subprime.core.models import ConversationLog
        from subprime.evaluation.personas import get_persona

        conv = ConversationLog(
            model="test-model",
            profile=get_persona("P01"),
            strategy=_fake_strategy(),
            plan=_fake_plan(),
        )
        conv_path = tmp_path / f"{conv.id}.json"
        conv_path.write_text(conv.model_dump_json(indent=2))

        result = runner.invoke(app, ["replay", str(conv_path)])
        assert result.exit_code == 0
        assert "Tony Stark" in result.output


# ===========================================================================
# CLI: subprime web
# ===========================================================================


class TestCLIWeb:
    def test_web_help(self):
        result = runner.invoke(app, ["web", "--help"])
        assert result.exit_code == 0
        assert "--port" in result.output
        assert "--host" in result.output


# ===========================================================================
# Gradio web app
# ===========================================================================


class TestGradioApp:
    """Smoke tests for the Gradio web app — catches import/compat regressions."""

    def test_app_module_imports(self):
        """The web app module should import without errors."""
        from apps.web.gradio_app import create_app, CSS
        assert create_app is not None
        assert isinstance(CSS, str)

    def test_app_creates_without_error(self):
        """create_app() should return a Gradio Blocks instance.
        This is the test that would have caught the Gradio 6.x breakage."""
        from apps.web.gradio_app import create_app
        demo = create_app()
        assert demo is not None

    def test_html_renderers_produce_output(self):
        """All HTML rendering functions should return non-empty strings."""
        from apps.web.gradio_app import render_profile_html, render_strategy_html, render_plan_html
        from subprime.evaluation.personas import get_persona

        profile = get_persona("P01")
        strategy = _fake_strategy()
        plan = _fake_plan()

        profile_html = render_profile_html(profile)
        assert len(profile_html) > 50
        assert "Tony" in profile_html

        strategy_html = render_strategy_html(strategy)
        assert len(strategy_html) > 50
        assert "70" in strategy_html

        plan_html = render_plan_html(plan)
        assert len(plan_html) > 100
        assert "UTI Nifty 50" in plan_html
        assert "Parag Parikh" in plan_html

    def test_html_renderers_handle_minimal_data(self):
        """Renderers should not crash on minimal/default model data."""
        from apps.web.gradio_app import render_profile_html, render_strategy_html, render_plan_html

        profile = InvestorProfile(
            id="test", name="Test", age=30, risk_appetite="moderate",
            investment_horizon_years=10, monthly_investible_surplus_inr=10000,
            existing_corpus_inr=0, liabilities_inr=0,
            financial_goals=["Save"], life_stage="Mid career", tax_bracket="new_regime",
        )
        strategy = StrategyOutline(
            equity_pct=50.0, debt_pct=50.0, gold_pct=0.0, other_pct=0.0,
            equity_approach="Balanced", key_themes=[],
            risk_return_summary="8% CAGR", open_questions=[],
        )
        plan = InvestmentPlan(
            allocations=[
                Allocation(
                    fund=MutualFund(amfi_code="100", name="Test Fund"),
                    allocation_pct=100.0, mode="sip", rationale="Only fund",
                )
            ],
        )

        assert len(render_profile_html(profile)) > 0
        assert len(render_strategy_html(strategy)) > 0
        assert len(render_plan_html(plan)) > 0

    def test_chat_state_initializes(self):
        """Chat state factory should return a valid state dict."""
        from apps.web.gradio_app import _make_state, PHASE_PROFILE
        state = _make_state()
        assert state["phase"] == PHASE_PROFILE
        assert state["profile"] is None
        assert state["strategy"] is None

    def test_opening_message_lists_personas(self):
        """Opening message should mention available personas."""
        from apps.web.gradio_app import _opening_message
        msg = _opening_message()
        assert "P01" in msg
        assert "P05" in msg

    def test_process_message_persona_selection(self):
        """Selecting a persona ID should load profile and generate strategy."""
        from apps.web.gradio_app import _process_message, _make_state

        state = _make_state()
        history = []

        with patch("apps.web.gradio_app.generate_strategy", new_callable=AsyncMock, return_value=_fake_strategy()):
            history, state, status = _process_message("P01", history, state)

        assert state["profile"] is not None
        assert state["profile"].name == "Tony Stark"
        assert state["strategy"] is not None
        assert len(history) >= 1

    def test_process_message_strategy_approval(self):
        """Typing 'yes' in strategy phase should trigger plan generation."""
        from apps.web.gradio_app import _process_message, _make_state, PHASE_STRATEGY
        from subprime.evaluation.personas import get_persona

        state = _make_state()
        state["phase"] = PHASE_STRATEGY
        state["profile"] = get_persona("P01")
        state["strategy"] = _fake_strategy()
        history = []

        with patch("apps.web.gradio_app.generate_plan", new_callable=AsyncMock, return_value=_fake_plan()):
            history, state, status = _process_message("yes", history, state)

        assert state["plan"] is not None
        assert len(history) >= 1

    def test_process_message_strategy_revision(self):
        """Feedback in strategy phase should revise the strategy."""
        from apps.web.gradio_app import _process_message, _make_state, PHASE_STRATEGY
        from subprime.evaluation.personas import get_persona

        revised = StrategyOutline(
            equity_pct=80.0, debt_pct=10.0, gold_pct=10.0, other_pct=0.0,
            equity_approach="More aggressive", key_themes=["growth"],
            risk_return_summary="14% CAGR", open_questions=[],
        )

        state = _make_state()
        state["phase"] = PHASE_STRATEGY
        state["profile"] = get_persona("P01")
        state["strategy"] = _fake_strategy()
        history = []

        with patch("apps.web.gradio_app.generate_strategy", new_callable=AsyncMock, return_value=revised):
            history, state, status = _process_message("more equity please", history, state)

        assert state["strategy"].equity_pct == 80.0


# ===========================================================================
# CLI: subprime data
# ===========================================================================


class TestCLIData:
    def test_data_help(self):
        result = runner.invoke(app, ["data", "--help"])
        assert result.exit_code == 0
        assert "refresh" in result.output
        assert "stats" in result.output

    def test_data_stats_empty_db(self, tmp_path, monkeypatch):
        """No DB file → stats command should report no data, exit 0."""
        monkeypatch.setattr("subprime.cli.DB_PATH", tmp_path / "missing.duckdb")
        result = runner.invoke(app, ["data", "stats"])
        assert result.exit_code == 0
        assert "no" in result.output.lower() or "No" in result.output

    def test_data_stats_populated(self, tmp_path, monkeypatch):
        """Populated DB → stats command should show counts."""
        import duckdb

        from subprime.data.store import ensure_schema, log_refresh

        db_path = tmp_path / "test.duckdb"
        conn = duckdb.connect(str(db_path))
        ensure_schema(conn)
        log_refresh(conn, scheme_count=42, nav_count=1234)
        conn.close()

        monkeypatch.setattr("subprime.cli.DB_PATH", db_path)
        result = runner.invoke(app, ["data", "stats"])
        assert result.exit_code == 0
        assert "42" in result.output
        assert "1234" in result.output or "1,234" in result.output

    def test_data_refresh_help(self):
        result = runner.invoke(app, ["data", "refresh", "--help"])
        assert result.exit_code == 0


# ===========================================================================
# Advisor with populated universe
# ===========================================================================


class TestAdvisorWithUniverse:
    @pytest.mark.asyncio
    async def test_plan_generation_loads_universe_from_db(self, tmp_path, monkeypatch):
        """When a DuckDB exists, generate_plan should inject the universe into system prompt."""
        import duckdb

        from subprime.data.store import ensure_schema
        from subprime.data.universe import build_universe

        db_path = tmp_path / "subprime.duckdb"
        conn = duckdb.connect(str(db_path))
        ensure_schema(conn)
        conn.execute(
            "INSERT INTO schemes (amfi_code, name, nav_name, amc, scheme_category, plan_type, average_aum_cr) "
            "VALUES ('119551', 'UTI Nifty 50 Index Fund', 'UTI Nifty 50 Index Fund - Direct Plan - Growth', "
            "'UTI Mutual Fund', 'Equity Scheme - Index Fund', 'direct', 12000.0)"
        )
        conn.execute(
            "INSERT INTO fund_returns (amfi_code, returns_1y, returns_3y, returns_5y, last_computed_at) "
            "VALUES ('119551', 11.5, 13.2, 14.1, CURRENT_TIMESTAMP)"
        )
        build_universe(conn)
        conn.close()

        # Point the planner at our test DB
        monkeypatch.setattr("subprime.advisor.planner.DB_PATH", db_path)

        # Capture the universe_context arg by spying on create_advisor
        captured = {}

        def fake_create_advisor(*, prompt_hooks=None, universe_context=None, model=None):
            captured["universe_context"] = universe_context
            mock_agent = AsyncMock()
            mock_agent.run = AsyncMock(return_value=MagicMock(output=_fake_plan()))
            return mock_agent

        monkeypatch.setattr("subprime.advisor.planner.create_advisor", fake_create_advisor)

        from subprime.advisor.planner import generate_plan

        profile = InvestorProfile(
            id="test", name="Test", age=30, risk_appetite="moderate",
            investment_horizon_years=10, monthly_investible_surplus_inr=10000,
            existing_corpus_inr=0, liabilities_inr=0,
            financial_goals=["Save"], life_stage="Mid career", tax_bracket="new_regime",
        )

        await generate_plan(profile)

        ctx = captured["universe_context"]
        assert ctx is not None
        assert "UTI Nifty 50" in ctx
        assert "Index" in ctx

    @pytest.mark.asyncio
    async def test_plan_generation_no_db_falls_back(self, tmp_path, monkeypatch):
        """When no DB exists, generate_plan should pass universe_context=None."""
        monkeypatch.setattr(
            "subprime.advisor.planner.DB_PATH", tmp_path / "nonexistent.duckdb"
        )

        captured = {}

        def fake_create_advisor(*, prompt_hooks=None, universe_context=None, model=None):
            captured["universe_context"] = universe_context
            mock_agent = AsyncMock()
            mock_agent.run = AsyncMock(return_value=MagicMock(output=_fake_plan()))
            return mock_agent

        monkeypatch.setattr("subprime.advisor.planner.create_advisor", fake_create_advisor)

        from subprime.advisor.planner import generate_plan

        profile = InvestorProfile(
            id="test", name="Test", age=30, risk_appetite="moderate",
            investment_horizon_years=10, monthly_investible_surplus_inr=10000,
            existing_corpus_inr=0, liabilities_inr=0,
            financial_goals=["Save"], life_stage="Mid career", tax_bracket="new_regime",
        )

        await generate_plan(profile)

        assert captured["universe_context"] is None
