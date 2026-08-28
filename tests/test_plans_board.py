import asyncio
import datetime as dt
import types
from unittest.mock import AsyncMock, MagicMock, patch

from swingbot.commands import plans as plans_module
from swingbot.commands.plans import render_board, _parse_board_args

TODAY = dt.date(2026, 7, 11)


def _plan(ticker, status, badge="VALIDATED", confidence_level=5, quality_score=80, plan_id=None,
          direction="bullish", tp2=None, entry_price=None, legs_realized=None, working_stop=None):
    return types.SimpleNamespace(
        plan_id=plan_id or f"{ticker}-{status}", ticker=ticker, status=status, badge=badge,
        confidence_level=confidence_level,
        quality_score=quality_score, direction=direction, entry_type="market",
        trigger_price=100.0, stop_loss=95.0, tp1=110.0, tp2=tp2,
        entry_price=entry_price, legs_realized=legs_realized or [], working_stop=working_stop,
        regime_aligned=True, created_at="2026-07-11",
    )


def test_render_board_groups_by_status_and_ranks_within_group():
    plans = [
        _plan("AAA", "PENDING", quality_score=20),
        _plan("BBB", "ACTIVE", quality_score=90),
        _plan("CCC", "PARTIAL", quality_score=50),
        _plan("DDD", "CLOSED"),   # excluded -- not in {PENDING, ACTIVE, PARTIAL}
    ]
    content, embed = render_board(plans, status="All", level="All", badge="All", page=0, today=TODAY)
    assert "DDD" not in content
    assert "PENDING" in content and "ACTIVE" in content and "PARTIAL" in content
    pending_pos = content.index("PENDING")
    active_pos = content.index("ACTIVE")
    assert content.index("AAA", pending_pos) > pending_pos
    assert content.index("BBB", active_pos) > active_pos


def _partial(ticker="NVDA", **kw):
    kw.setdefault("entry_price", 100.0)
    kw.setdefault("legs_realized", [{"fraction": 0.5, "exit_price": 110.0,
                                     "r": 2.0, "reason": "tp1"}])
    kw.setdefault("working_stop", 104.0)
    return _plan(ticker, "PARTIAL", **kw)


def _line_for(plan, **kw):
    """The one board row `plan` renders to, through the real !liveplans
    renderer (render_board -> _plan_line), not a formatter nothing calls."""
    content, _ = render_board([plan], status="All", level="All", badge="All",
                              page=0, today=TODAY, **kw)
    return next(ln for ln in content.splitlines() if plan.ticker in ln)


def test_partial_row_shows_the_banked_leg_not_the_stale_original_levels(monkeypatch):
    """Once TP1 fires, trigger_price/stop_loss/tp1 are stale -- the row must
    lead with what was banked (R, %, $) and then frame the runner as its own
    position."""
    from swingbot.core.planning import account
    from swingbot import config
    monkeypatch.setattr(account, "compute_position_size",
                        lambda entry, stop: {"shares": 100.0,
                                             "position_value": 10_000.0,
                                             "mode": "risk_pct"})
    monkeypatch.setattr(config, "CURRENCY_SYMBOL", "$")
    line = _line_for(_partial(tp2=120.0))
    assert "banked +2.00R/+10.0%/+$500.00 on 50%" in line
    assert "runner entry 110.00 SL 104.00 TP2 120.00" in line
    # The pre-TP1 tail is gone, not merely appended to.
    assert "entry 100.00" not in line and "SL 95.00" not in line


def test_partial_row_labels_the_tp1_fallback_when_there_is_no_tp2(monkeypatch):
    from swingbot.core.planning import account
    monkeypatch.setattr(account, "compute_position_size",
                        lambda entry, stop: None)
    line = _line_for(_partial(tp2=None))
    assert "runner entry 110.00 SL 104.00 TP1 (no TP2) 110.00" in line


def test_partial_row_omits_the_dollar_figure_when_unsized(monkeypatch):
    """Sizing unavailable -> no $ clause at all. Never a '$0.00', which
    would read as a flat trade rather than an unknown one."""
    from swingbot.core.planning import account
    from swingbot import config
    monkeypatch.setattr(account, "compute_position_size",
                        lambda entry, stop: None)
    monkeypatch.setattr(config, "CURRENCY_SYMBOL", "$")
    line = _line_for(_partial())
    assert "banked +2.00R/+10.0% on 50%" in line
    assert "$" not in line


def test_partial_row_survives_a_plan_with_no_recorded_leg(monkeypatch):
    """A PARTIAL plan predating legs_realized still renders -- banked clause
    dropped, runner entry falling back to the tp1 level."""
    from swingbot.core.planning import account
    monkeypatch.setattr(account, "compute_position_size",
                        lambda entry, stop: None)
    line = _line_for(_partial(legs_realized=[], working_stop=None))
    assert "banked" not in line
    assert "runner entry 110.00 TP1 (no TP2) 110.00" in line


def test_non_partial_rows_keep_the_original_tail():
    line = _line_for(_plan("BBB", "ACTIVE", tp2=120.0))
    assert "entry 100.00 SL 95.00 TP1 110.00 TP2 120.00" in line
    assert "banked" not in line and "runner" not in line


def test_render_board_filters_by_level():
    plans = [_plan("AAA", "ACTIVE", confidence_level=5), _plan("BBB", "ACTIVE", confidence_level=3)]
    content, _ = render_board(plans, status="All", level="5", badge="All", page=0, today=TODAY)
    assert "AAA" in content and "BBB" not in content


def test_render_board_filters_by_ticker():
    plans = [_plan("NVDA", "ACTIVE"), _plan("AAPL", "ACTIVE")]
    content, _ = render_board(plans, status="All", level="All", badge="All", page=0, ticker="NVDA", today=TODAY)
    assert "NVDA" in content and "AAPL" not in content


def test_liveplans_cmd_ticker_filter_survives_view_filter_change():
    """Task B16: `!liveplans NVDA` must keep filtering to NVDA even after
    the resulting PlanBoardView's status/level/badge selects are changed,
    because the ticker filter isn't one of render_fn's parameters -- it's
    captured by the lambda's closure over `parsed_ticker` at command-
    invocation time (swingbot/commands/plans.py:liveplans_cmd). This test
    picks level="3"/badge="WEAK" for the second render_fn call precisely
    because those match AAPL, not NVDA: if the ticker filter had been lost,
    AAPL would reappear in the output."""
    plans = [
        _plan("NVDA", "ACTIVE", confidence_level=5, badge="VALIDATED"),
        _plan("AAPL", "ACTIVE", confidence_level=3, badge="WEAK"),
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
    # Simulate the user then changing status/level/badge dropdowns to
    # values that match AAPL, not NVDA. If the ticker filter weren't fixed
    # by the closure, AAPL would now show up.
    changed_content, _ = view.render_fn("ACTIVE", "3", "WEAK")
    assert "AAPL" not in changed_content
    assert "No live plans match this filter" in changed_content


def test_parse_board_args_status_level_ticker():
    parsed = _parse_board_args(("active", "level:5", "NVDA"))
    assert parsed == {"status": "ACTIVE", "level": "5", "ticker": "NVDA"}


def test_parse_board_args_badge():
    parsed = _parse_board_args(("badge:validated",))
    assert parsed["badge"] == "VALIDATED"


def test_parse_board_args_empty():
    assert _parse_board_args(()) == {}
