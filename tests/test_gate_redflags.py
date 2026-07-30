import datetime as dt

import numpy as np

from swingbot.core.gate.redflags import rf_fake_breakout, rf_stop_sweep
from tests.conftest import make_ohlcv
from tests.fixtures.gate import breakout_and_fail, sweep_wick, uptrend_daily
from tests.fixtures.gate.plans import make_plan

BREAKOUT_PLAN = make_plan(strategy="Break & Retest", direction="bullish",
                          trigger_price=100.0)


def test_breakout_and_fail_fires():
    result = rf_fake_breakout(breakout_and_fail(level=100.0), BREAKOUT_PLAN, None)
    assert result.status == "fail"


def test_clean_high_volume_breakout_passes():
    vols = np.full(60, 1_000_000.0)
    vols[-1] = 2_500_000.0
    closes = np.concatenate([np.linspace(92, 99, 59), [102.0]])
    df = make_ohlcv(closes, volumes=vols)
    assert rf_fake_breakout(df, BREAKOUT_PLAN, None).status == "pass"


def test_serial_poker_fires():
    # Two failed pokes in prior-10 window, OUTSIDE the recent-3 window,
    # to isolate and test the serial-poke branch specifically.
    # df_daily.iloc[-11:-1] covers indices -11 to -2; df_daily.iloc[-3:] covers indices -3,-2,-1
    # So pokes at -11 and -9 are ONLY in the prior window, not in recent.
    closes = np.full(60, 97.0)
    df = make_ohlcv(closes, spread_pct=1.0)
    # Add failed pokes at -11 and -9 (outside recent window)
    df.loc[df.index[-11], "High"] = 101.0
    df.loc[df.index[-9], "High"] = 101.0
    # All closes stay below level, so broke_out doesn't trigger
    result = rf_fake_breakout(df, BREAKOUT_PLAN, None)
    assert result.status == "fail"
    assert "serial-liar" in result.detail
    assert result.evidence.get("failed_pokes") == 2


def test_breakout_on_dead_volume_fails():
    # Bar breaks out above level and stays there, but on low volume.
    # This isolates the beyond_now + low-volume branch.
    closes = np.concatenate([np.full(59, 99.0), [102.0]])
    volumes = np.full(60, 1_000_000.0)
    volumes[-1] = 500_000.0  # 0.5x average, below 0.8 threshold
    df = make_ohlcv(closes, volumes=volumes)
    result = rf_fake_breakout(df, BREAKOUT_PLAN, None)
    assert result.status == "fail"
    assert "dead volume" in result.detail
    assert result.evidence["vol_ratio"] < 0.8


def test_non_breakout_strategy_na_pass():
    result = rf_fake_breakout(breakout_and_fail(), make_plan(strategy="RSI"), None)
    assert result.status == "pass" and "n/a" in result.detail


def test_sweep_wick_fires():
    plan = make_plan(trigger_price=101.0)
    result = rf_stop_sweep(sweep_wick(level=100.0), plan, None)
    assert result.status == "fail"
    assert result.evidence["wick_body"] >= 1.5


def test_normal_trend_passes():
    assert rf_stop_sweep(uptrend_daily(), make_plan(), None).status == "pass"
