import asyncio
import datetime as dt
import types
from unittest.mock import AsyncMock, MagicMock, patch

from swingbot.commands import plans as plans_module
from swingbot.commands.plans import render_board, _parse_board_args

TODAY = dt.date(2026, 7, 11)


def _plan(ticker, status, badge="VALIDATED", tier="A", quality_score=80, plan_id=None, direction="bullish"):
    return types.SimpleNamespace(
        plan_id=plan_id or f"{ticker}-{status}", ticker=ticker, status=status, badge=badge, tier=tier,
        quality_score=quality_score, direction=direction, entry_type="market",
        trigger_price=100.0, stop_loss=95.0, tp1=110.0, tp2=None,
        regime_aligned=True, created_at="2026-07-11",
    )


def test_render_board_groups_by_status_and_ranks_within_group():
    plans = [
        _plan("AAA", "PENDING", quality_score=20),
        _plan("BBB", "ACTIVE", quality_score=90),
        _plan("CCC", "PARTIAL", quality_score=50),
        _plan("DDD", "CLOSED"),   # excluded -- not in {PENDING, ACTIVE, PARTIAL}
    ]
    content, embed = render_board(plans, status="All", tier="All", badge="All", page=0, today=TODAY)
    assert "DDD" not in content
    assert "PENDING" in content and "ACTIVE" in content and "PARTIAL" in content
    pending_pos = content.index("PENDING")
    active_pos = content.index("ACTIVE")
    assert content.index("AAA", pending_pos) > pending_pos
    assert content.index("BBB", active_pos) > active_pos


def test_render_board_filters_by_tier():
    plans = [_plan("AAA", "ACTIVE", tier="A"), _plan("BBB", "ACTIVE", tier="B")]
    content, _ = render_board(plans, status="All", tier="A", badge="All", page=0, today=TODAY)
    assert "AAA" in content and "BBB" not in content


def test_render_board_filters_by_ticker():
    plans = [_plan("NVDA", "ACTIVE"), _plan("AAPL", "ACTIVE")]
    content, _ = render_board(plans, status="All", tier="All", badge="All", page=0, ticker="NVDA", today=TODAY)
    assert "NVDA" in content and "AAPL" not in content


def test_liveplans_cmd_ticker_filter_survives_view_filter_change():
    """Task B16: `!liveplans NVDA` must keep filtering to NVDA even after
    the resulting PlanBoardView's status/tier/badge selects are changed,
    because the ticker filter isn't one of render_fn's parameters -- it's
    captured by the lambda's closure over `parsed_ticker` at command-
    invocation time (swingbot/commands/plans.py:liveplans_cmd). This test
    picks tier="B"/badge="WEAK" for the second render_fn call precisely
    because those match AAPL, not NVDA: if the ticker filter had been lost,
    AAPL would reappear in the output."""
    plans = [
        _plan("NVDA", "ACTIVE", tier="A", badge="VALIDATED"),
        _plan("AAPL", "ACTIVE", tier="B", badge="WEAK"),
    ]
    fake_store = MagicMock()
    fake_store.open_plans.return_value = plans

    ctx = MagicMock()
    ctx.author.id = 42
    ctx.send = AsyncMock()

    with patch.object(plans_module, "PlanStore", return_value=fake_store):
        asyncio.run(plans_module.liveplans_cmd.callback(ctx, "NVDA"))

    ctx.send.assert_awaited_once()
    _, kwargs = ctx.send.call_args
    assert "NVDA" in kwargs["content"] and "AAPL" not in kwargs["content"]

    view = kwargs["view"]
    # Simulate the user then changing tier/badge dropdowns to values that
    # match AAPL, not NVDA. If the ticker filter weren't fixed by the
    # closure, AAPL would now show up.
    changed_content, _ = view.render_fn("ACTIVE", "B", "WEAK")
    assert "AAPL" not in changed_content
    assert "No live plans match this filter" in changed_content


def test_parse_board_args_status_tier_ticker():
    parsed = _parse_board_args(("active", "tier:a", "NVDA"))
    assert parsed == {"status": "ACTIVE", "tier": "A", "ticker": "NVDA"}


def test_parse_board_args_badge():
    parsed = _parse_board_args(("badge:validated",))
    assert parsed["badge"] == "VALIDATED"


def test_parse_board_args_empty():
    assert _parse_board_args(()) == {}
