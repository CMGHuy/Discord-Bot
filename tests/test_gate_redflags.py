import datetime as dt

import numpy as np

import swingbot.config as config
import swingbot.core.gate.redflags as redflags
from swingbot.core.gate.redflags import (
    rf_dead_cat, rf_divergence_trap, rf_fake_breakout, rf_news_whipsaw, rf_stop_sweep,
    rf_thin_session,
)
from tests.conftest import make_ohlcv
from tests.fixtures.gate import breakout_and_fail, climax_overbought, range_daily, sweep_wick, uptrend_daily
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


def _dead_cat_v_bounce():
    """Downtrend followed by V-bounce with no structure shift.
    250-bar pure downtrend + 1-bar bounce. The 1-bar bounce keeps trend as "down"
    while still providing a bounce to test against."""
    down = 150.0 * (1 - 0.01) ** np.arange(250)
    low = down[-1]
    # Single bounce bar of +8%
    bounce = np.array([low * 1.08])
    return make_ohlcv(np.concatenate([down, bounce]), spread_pct=2.0)


def _reversal_with_structure():
    """Downtrend, then bounce -> higher low -> higher high: a real shift."""
    lead = np.full(200, 150.0)
    down = 150.0 * (1 - 0.01) ** np.arange(40)
    low = down[-1]
    leg1 = np.linspace(low, low * 1.06, 5)[1:]
    dip = np.linspace(low * 1.06, low * 1.03, 4)[1:]      # higher low
    leg2 = np.linspace(low * 1.03, low * 1.09, 6)[1:]     # higher high
    return make_ohlcv(np.concatenate([lead, down, leg1, dip, leg2]), spread_pct=2.0)


def test_dead_cat_fires_on_v_bounce():
    result = rf_dead_cat(_dead_cat_v_bounce(), make_plan(direction="bullish"), None)
    assert result.status == "fail"
    assert result.evidence["bounce_pct"] >= 5
    assert result.evidence["structure_shift"] is False


def test_structure_shift_passes():
    result = rf_dead_cat(_reversal_with_structure(),
                         make_plan(direction="bullish"), None)
    assert result.status == "pass"
    assert result.evidence["structure_shift"] is True


def test_bearish_plan_na():
    result = rf_dead_cat(_dead_cat_v_bounce(), make_plan(direction="bearish"), None)
    assert result.status == "pass" and "n/a" in result.detail


def _bullish_divergence(confirmed: bool):
    """Steep decline (RSI cold) -> bounce to 108 -> gentle grind to a LOWER
    low (RSI warmer = bullish divergence). Confirmation = close above 108."""
    closes = list(np.full(40, 130.0))
    closes += list(np.linspace(130, 100, 20))[1:]
    closes += list(np.linspace(100, 108, 6))[1:]
    closes += list(np.linspace(108, 98, 16))[1:]
    if confirmed:
        closes += list(np.linspace(98, 110, 8))[1:]     # closes above 108
    else:
        closes += list(np.linspace(98, 103, 5))[1:]     # bounce, still below 108
    return make_ohlcv(np.asarray(closes), spread_pct=0.5)


DIV_PLAN = make_plan(strategy="RSI Divergence", direction="bullish")


def test_unconfirmed_divergence_fires():
    result = rf_divergence_trap(_bullish_divergence(confirmed=False), DIV_PLAN, None)
    assert result.status == "fail" and "confirmation" in result.detail


def test_confirmed_divergence_passes():
    assert rf_divergence_trap(_bullish_divergence(confirmed=True),
                              DIV_PLAN, None).status == "pass"


def test_non_divergence_strategy_na():
    result = rf_divergence_trap(_bullish_divergence(False),
                                make_plan(strategy="VWAP"), None)
    assert result.status == "pass" and "n/a" in result.detail


def test_fading_strong_trend_fires():
    from swingbot.core.gate.redflags import rf_extreme_fade
    short_fade = make_plan(direction="bearish", strategy="RSI")
    result = rf_extreme_fade(climax_overbought(), short_fade, None)
    assert result.status == "fail"
    assert result.evidence["rsi"] > 75 and result.evidence["adx"] > 30


def test_range_fade_passes():
    from swingbot.core.gate.redflags import rf_extreme_fade
    short_fade = make_plan(direction="bearish", strategy="RSI")
    assert rf_extreme_fade(range_daily(90, 110, n=300), short_fade, None).status == "pass"


def test_with_trend_plan_passes():
    from swingbot.core.gate.redflags import rf_extreme_fade
    long_with = make_plan(direction="bullish")
    assert rf_extreme_fade(climax_overbought(), long_with, None).status == "pass"


NOW = dt.datetime(2026, 7, 14, 20, 0, tzinfo=dt.timezone.utc)


def _snap_with(events_24h):
    return {"events": {"next_high_impact": events_24h[0] if events_24h else None,
                       "within_24h": events_24h, "today": []}}


def test_cpi_tomorrow_fires_hard(monkeypatch):
    monkeypatch.setattr(redflags.earnings, "earnings_within",
                        lambda *a, **k: None)
    cpi = {"date": "2026-07-15", "time_et": "08:30", "kind": "cpi",
           "label": "CPI release", "importance": 3}
    result = rf_news_whipsaw(uptrend_daily(), make_plan(), _snap_with([cpi]), now=NOW)
    assert result.status == "fail"                    # ~16.5h ahead, inside 18h window
    from swingbot.core.gate.registry import CHECKS
    assert CHECKS["rf_news_whipsaw"].hard_block is True


def test_importance_2_warns(monkeypatch):
    monkeypatch.setattr(redflags.earnings, "earnings_within", lambda *a, **k: None)
    ppi = {"date": "2026-07-15", "time_et": "08:30", "kind": "ppi",
           "label": "PPI release", "importance": 2}
    assert rf_news_whipsaw(uptrend_daily(), make_plan(),
                           _snap_with([ppi]), now=NOW).status == "warn"


def test_quiet_week_passes(monkeypatch):
    monkeypatch.setattr(redflags.earnings, "earnings_within", lambda *a, **k: False)
    assert rf_news_whipsaw(uptrend_daily(), make_plan(),
                           _snap_with([]), now=NOW).status == "pass"


def test_earnings_inside_blackout_fires(monkeypatch):
    monkeypatch.setattr(redflags.earnings, "earnings_within", lambda *a, **k: True)
    result = rf_news_whipsaw(uptrend_daily(), make_plan(), _snap_with([]), now=NOW)
    assert result.status == "fail" and "earnings" in result.detail


def test_no_snapshot_unknown():
    assert rf_news_whipsaw(uptrend_daily(), make_plan(), None, now=NOW).status == "unknown"


def _liquid_df():
    return make_ohlcv(np.full(60, 50.0), volumes=np.full(60, 1_000_000.0))


def test_holiday_week_warns():
    holiday_week = dt.datetime(2026, 12, 29, 16, 0, tzinfo=dt.timezone.utc)  # 11:00 ET
    result = rf_thin_session(_liquid_df(), make_plan(), None, now=holiday_week)
    assert result.status == "warn" and "holiday week" in result.detail


def test_liquid_normal_day_passes():
    normal = dt.datetime(2026, 7, 14, 16, 0, tzinfo=dt.timezone.utc)         # 12:00 ET Tue
    assert rf_thin_session(_liquid_df(), make_plan(), None, now=normal).status == "pass"


def test_illiquid_ticker_warns():
    normal = dt.datetime(2026, 7, 14, 16, 0, tzinfo=dt.timezone.utc)
    thin = make_ohlcv(np.full(60, 2.0), volumes=np.full(60, 100_000.0))      # $200k/day
    result = rf_thin_session(thin, make_plan(), None, now=normal)
    assert result.status == "warn" and "dollar volume" in result.detail
