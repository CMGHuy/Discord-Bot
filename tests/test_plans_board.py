import datetime as dt
import types

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


def test_parse_board_args_status_tier_ticker():
    parsed = _parse_board_args(("active", "tier:a", "NVDA"))
    assert parsed == {"status": "ACTIVE", "tier": "A", "ticker": "NVDA"}


def test_parse_board_args_badge():
    parsed = _parse_board_args(("badge:validated",))
    assert parsed["badge"] == "VALIDATED"


def test_parse_board_args_empty():
    assert _parse_board_args(()) == {}
