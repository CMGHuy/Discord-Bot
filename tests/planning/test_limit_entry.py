"""v113 §3: limit entries in the shared exit simulator (spec fill model + amendment 3)."""
import pytest

from swingbot.core.planning import lifecycle
from swingbot.core.planning.plan_engine import PlanStatus, TradePlanV2, simulate_exit
from tests.helpers import make_ohlcv

SIGNAL = (100.5, 101.0, 99.5, 100.0)      # bar 0: signal bar; its close 100 is the limit
FLAT = (99.5, 100.2, 99.3, 99.6)          # trades through 100, never reaches 102 or 98


def _plan(**kw):
    base = dict(
        plan_id="p1", ticker="T", created_at="2024-01-02", source="strategy",
        strategy="Probe", horizon_key="1w", direction="bearish",
        entry_type="limit", trigger_price=100.0, entry_price=None, expiry_bars=1,
        stop_loss=102.0, tp1=98.0, tp1_fraction=1.0, tp2=None,
        breakeven_trigger_fraction=1.0, trail_atr_mult=2.5,
        quality_score=0, quality_breakdown=[],
        badge="WEAK", badge_stats={}, status=PlanStatus.PENDING, status_history=[],
    )
    base.update(kw)
    return TradePlanV2(**base)


def _df(*bars):
    return make_ohlcv([SIGNAL, *bars])


@pytest.mark.parametrize("scale_out", [False, True])
def test_sell_limit_fills_at_the_limit_and_wins_at_the_whole_position_target(scale_out):
    df = _df((99.5, 100.4, 99.2, 99.6), (99.4, 99.6, 98.6, 98.8), (98.7, 98.9, 97.9, 98.1), FLAT)
    res = simulate_exit(df, 0, _plan(), scale_out=scale_out)
    assert (res.outcome, res.entry_index, res.entry_price, res.exit_index) == ("win", 1, 100.0, 3)
    assert res.r_total == pytest.approx(1.0) and res.runner_outcome is None
    assert [leg["fraction"] for leg in res.legs] == [1.0]


def test_no_fill_when_bar_t_plus_1_never_reaches_the_limit_even_if_t_plus_2_does():
    df = _df((99.0, 99.8, 98.5, 99.0), (99.5, 100.5, 99.0, 100.0), FLAT)
    assert simulate_exit(df, 0, _plan(), scale_out=True).outcome == "not_triggered"


def test_a_gap_above_the_limit_fills_at_the_open():
    df = _df((100.8, 101.0, 100.1, 100.3), (100.0, 100.2, 98.5, 98.7), (98.5, 98.6, 97.8, 98.0))
    res = simulate_exit(df, 0, _plan(), scale_out=True)
    assert res.entry_price == 100.8 and res.outcome == "win"
    assert res.r_total == pytest.approx(2.8 / 1.2, abs=1e-3)


def test_a_stop_touch_on_the_fill_bar_is_a_full_loss_on_that_bar():
    df = _df((99.8, 102.5, 99.5, 101.8), FLAT)
    res = simulate_exit(df, 0, _plan(), scale_out=True)
    assert (res.outcome, res.entry_index, res.exit_index, res.r_total) == ("loss", 1, 1, -1.0)
    assert res.legs[0]["exit_price"] == 102.0


def test_a_gap_through_the_stop_exits_flat_on_the_fill_bar():
    df = _df((102.6, 103.0, 102.2, 102.8), FLAT)
    res = simulate_exit(df, 0, _plan(), scale_out=True)
    assert (res.outcome, res.entry_price, res.exit_index, res.r_total) == ("scratch", 102.6, 1, 0.0)


def test_the_time_stop_closes_at_the_seventh_bar_after_entry():
    df = _df(*([FLAT] * 10))
    res = simulate_exit(df, 0, _plan(), scale_out=True)
    assert (res.outcome, res.entry_index, res.exit_index) == ("timeout", 1, 8)
    assert res.r_total == pytest.approx(0.2)


def test_buy_limit_mirrors_the_sell_limit():
    plan = _plan(direction="bullish", stop_loss=98.0, tp1=102.0)
    df = _df((100.5, 100.8, 99.9, 100.4), (100.6, 102.2, 100.4, 102.0))
    res = simulate_exit(df, 0, plan, scale_out=True)
    assert (res.outcome, res.entry_price, res.exit_index) == ("win", 100.0, 2)


def test_lifecycle_helpers():
    sell, buy = _plan(), _plan(direction="bullish", stop_loss=98.0, tp1=102.0)
    assert lifecycle.limit_hit(sell, 100.0, 99.0) and not lifecycle.limit_hit(sell, 99.99, 99.0)
    assert lifecycle.limit_hit(buy, 101.0, 100.0) and not lifecycle.limit_hit(buy, 101.0, 100.01)
    assert lifecycle.limit_fill_price(sell, 99.0) == 100.0 and lifecycle.limit_fill_price(sell, 101.0) == 101.0
    assert lifecycle.limit_fill_price(buy, 101.0) == 100.0 and lifecycle.limit_fill_price(buy, 99.0) == 99.0
    assert lifecycle.stop_touched(sell, 102.0, 99.0) and not lifecycle.stop_touched(sell, 101.9, 99.0)
    assert lifecycle.at_or_beyond_stop(sell, 102.0) and not lifecycle.at_or_beyond_stop(buy, 98.1)


def test_truncating_after_the_fill_bar_does_not_change_a_fill_bar_stop_out():
    """No-lookahead: the fill and a fill-bar stop read bar t+1 only, never t+2."""
    full = _df((99.8, 102.5, 99.5, 101.8), (99.0, 99.2, 90.0, 90.5))
    a = simulate_exit(full, 0, _plan(), scale_out=True)
    b = simulate_exit(full.iloc[:2], 0, _plan(), scale_out=True)
    assert (a.outcome, a.entry_index, a.exit_index, a.r_total) == (
        b.outcome, b.entry_index, b.exit_index, b.r_total)
