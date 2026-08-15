"""Task 20: entry-phase tests for the shared exit simulator.

Only the ENTRY phase is in scope here (market fill / stop_entry fill /
stop_entry not_triggered via expiry or pre-fill invalidation). Since Task
21, a successful fill's default (scale_out=False) path proceeds into the
single-leg exit walk instead of raising -- so these tests pass
scale_out=True to isolate entry resolution and confirm the entry_index/
entry_price the scale-out walk (Task 24+) was established with, via the
returned ExitResult (the scale-out path no longer raises -- Task 21's
NotImplementedError placeholder was removed in Task 24).
"""
from swingbot.core.plan_engine import TradePlanV2, PlanStatus, simulate_exit
from tests.helpers import make_ohlcv


def _plan(**kw):
    base = dict(
        plan_id="p1", ticker="AAPL", created_at="2024-01-02", source="strategy",
        strategy="Fibonacci", horizon_key="2w", direction="bullish",
        entry_type="market", trigger_price=100.0, entry_price=None, expiry_bars=3,
        stop_loss=95.0, tp1=102.0, tp1_fraction=0.5, tp2=105.0,
        breakeven_trigger_fraction=0.5, trail_atr_mult=2.5,
        quality_score=0, quality_breakdown=[], tier="C",
        badge="WEAK", badge_stats={}, status=PlanStatus.PENDING, status_history=[],
    )
    base.update(kw)
    return TradePlanV2(**base)


# ---------------------------------------------------------------------------
# market entry
# ---------------------------------------------------------------------------

def test_market_entry_establishes_index_and_price_then_scale_out_walk_runs():
    df = make_ohlcv([100.0, 101.0, 102.5, 103.0, 104.0])
    plan = _plan(entry_type="market")

    result = simulate_exit(df, signal_index=2, plan=plan, scale_out=True)

    assert result.entry_index == 2
    assert result.entry_price == 102.5


# ---------------------------------------------------------------------------
# stop_entry fill
# ---------------------------------------------------------------------------

def test_stop_entry_fills_on_bar_whose_high_crosses_trigger_at_max_open_trigger():
    # signal bar (index 0) is irrelevant to the scan itself.
    df = make_ohlcv([
        100.0,                          # 0: signal bar
        (100.0, 104.0, 99.0, 103.0),    # 1: High 104 < trigger 105 -- no fill
        (106.0, 107.0, 105.5, 106.5),   # 2: gaps above trigger -- fills at Open
        (107.0, 108.0, 106.0, 107.5),   # 3: unreached (loop should have exited)
    ])
    plan = _plan(entry_type="stop_entry", direction="bullish",
                 trigger_price=105.0, stop_loss=95.0, expiry_bars=5)

    result = simulate_exit(df, signal_index=0, plan=plan, scale_out=True)

    assert result.entry_index == 2
    assert result.entry_price == 106.0  # max(open=106.0, trigger=105.0)


# ---------------------------------------------------------------------------
# stop_entry expiry
# ---------------------------------------------------------------------------

def test_stop_entry_expiry_produces_not_triggered_with_empty_legs():
    # expiry_bars=2: only bars 1-2 are scanned. Bar 3 would have triggered,
    # proving the scan actually stopped at the expiry boundary rather than
    # just running out of data.
    df = make_ohlcv([
        100.0,                         # 0: signal bar
        (100.0, 103.0, 99.0, 101.0),   # 1: High 103 < trigger 105
        (101.0, 104.0, 100.0, 102.0),  # 2: High 104 < trigger 105 (last scanned bar)
        (106.0, 107.0, 105.5, 106.5),  # 3: would trigger, but past expiry
    ])
    plan = _plan(entry_type="stop_entry", direction="bullish",
                 trigger_price=105.0, stop_loss=95.0, expiry_bars=2)

    result = simulate_exit(df, signal_index=0, plan=plan)

    assert result.outcome == "not_triggered"
    assert result.entry_index is None
    assert result.entry_price is None
    assert result.exit_index is None
    assert result.r_total == 0.0
    assert result.legs == []


# ---------------------------------------------------------------------------
# stop_entry pre-fill invalidation
# ---------------------------------------------------------------------------

def test_stop_entry_pre_fill_invalidation_produces_not_triggered_with_empty_legs():
    df = make_ohlcv([
        100.0,                         # 0: signal bar
        (99.0, 103.0, 98.0, 96.0),     # 1: close 96 above stop 95 -- still pending
        (95.0, 96.0, 90.0, 94.0),      # 2: close 94 <= stop 95 -- invalidated
        (106.0, 107.0, 105.5, 106.5),  # 3: would trigger, but never reached
    ])
    plan = _plan(entry_type="stop_entry", direction="bullish",
                 trigger_price=105.0, stop_loss=95.0, expiry_bars=5)

    result = simulate_exit(df, signal_index=0, plan=plan)

    assert result.outcome == "not_triggered"
    assert result.entry_index is None
    assert result.entry_price is None
    assert result.exit_index is None
    assert result.r_total == 0.0
    assert result.legs == []
