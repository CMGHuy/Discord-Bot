"""Tests for strategy_types constants and entry_filters."""
import pytest


def test_rr_override_single_source_and_floor():
    from swingbot.core.strategy_types import STRATEGY_RR_OVERRIDE, BREAKEVEN_TRIGGER_FRACTION
    from swingbot.core.backtest import STRATEGY_RR_OVERRIDE as BT_RR, ALL_STRATEGIES

    assert BT_RR is STRATEGY_RR_OVERRIDE          # same object, not a copy
    assert set(STRATEGY_RR_OVERRIDE) == set(ALL_STRATEGIES)
    assert all(rr >= 0.30 for rr in STRATEGY_RR_OVERRIDE.values()), \
        "R:R below 0.30 makes 80% win rate unprofitable (spec hard floor)"
    assert 0.0 < BREAKEVEN_TRIGGER_FRACTION < 1.0


def test_strategy_gates_shape():
    from swingbot.core.strategy_types import STRATEGY_GATES
    for strat, gates in STRATEGY_GATES.items():
        assert set(gates) <= {"directions", "horizons"}


import numpy as np
import pandas as pd

from tests.conftest import make_trend_df, make_ohlcv, assert_entry_invariants


def test_shared_gates_uptrend(uptrend_df):
    from swingbot.core.entry_filters import compute_shared_gates
    g = compute_shared_gates(uptrend_df)
    for key in ("bull_regime", "bear_regime", "trend50_bull", "trend50_bear",
                "atr_floor", "atr_calm", "vol_ok"):
        assert g[key].dtype == bool
        assert not g[key].isna().any()
    # 200-SMA + 20-bar slope shift need 220 bars: nothing NaN-passes early
    assert not g["bull_regime"].iloc[:219].any()
    # a steady uptrend is a bull regime at the end, never a bear regime
    assert g["bull_regime"].iloc[-1]
    assert not g["bear_regime"].any()


def test_shared_gates_downtrend(downtrend_df):
    from swingbot.core.entry_filters import compute_shared_gates
    g = compute_shared_gates(downtrend_df)
    assert not g["bull_regime"].iloc[-1]
    # bear regime needs 200-SMA falling for 120 bars -> needs 320 bars, so
    # it can be True only late in the series
    assert g["bear_regime"].iloc[-1]
    assert not g["bear_regime"].iloc[:319].any()


def test_rolling_extreme_position_helpers():
    from swingbot.core.entry_filters import _rolling_argmax_pos, _rolling_argmin_pos
    s = pd.Series([1.0, 5.0, 2.0, 3.0, 4.0])
    amax = _rolling_argmax_pos(s, 3)
    amin = _rolling_argmin_pos(s, 3)
    assert np.isnan(amax.iloc[0]) and np.isnan(amax.iloc[1])
    assert amax.iloc[2] == 1        # window [1,5,2] -> max at position 1
    assert amin.iloc[2] == 0        # min at position 0
    assert amax.iloc[4] == 2        # window [2,3,4] -> max at last position


def test_entries_for_applies_direction_and_horizon_gates(monkeypatch, uptrend_df):
    import swingbot.core.entry_filters as ef

    fired = pd.Series(True, index=uptrend_df.index)
    monkeypatch.setitem(ef.ENTRY_FUNCS, "Stub", lambda df, hk, params=None: (fired.copy(), fired.copy()))

    monkeypatch.setitem(ef.STRATEGY_GATES, "Stub", {"directions": ("bullish",)})
    bull, bear = ef.entries_for("Stub", uptrend_df, "4w")
    assert bull.all() and not bear.any()

    monkeypatch.setitem(ef.STRATEGY_GATES, "Stub", {"horizons": ("2m",)})
    bull, bear = ef.entries_for("Stub", uptrend_df, "4w")
    assert not bull.any() and not bear.any()


def _v_shape_down_then_flat():
    # Peak early (bar 350), decline to bar 470, small bounce at the end.
    # The swing HIGH precedes the swing LOW inside any recent window ->
    # down-impulse -> the old code would call a bounce here "bullish
    # retracement"; the fixed code must not.
    closes = np.concatenate([
        100 * 1.002 ** np.arange(350),                       # up to ~201
        100 * 1.002 ** 349 * 0.995 ** np.arange(1, 121),     # down ~45%
        np.full(29, 100 * 1.002 ** 349 * 0.995 ** 120 * 1.002),
    ])
    return make_ohlcv(closes, spread_pct=2.0)


def test_fibonacci_no_bullish_entries_on_down_impulse():
    from swingbot.core.entry_filters import fibonacci_entries
    df = _v_shape_down_then_flat()
    bull, bear = fibonacci_entries(df, "4w")
    assert_entry_invariants(bull, bear, df)
    # last 40 bars: price is bouncing off a decline -- swing direction is
    # DOWN, so no bullish fib-retracement entries are allowed there
    assert not bull.iloc[-40:].any()


def test_fibonacci_bullish_requires_bull_regime(downtrend_df):
    from swingbot.core.entry_filters import fibonacci_entries
    bull, bear = fibonacci_entries(downtrend_df, "4w")
    assert_entry_invariants(bull, bear, downtrend_df)
    assert not bull.any()


GATED_BY_MA50 = ["EMA Crossover", "VWAP", "Fibonacci"]  # extended by later tasks


def test_bullish_entries_respect_trend_gates(market_df):
    """Wiring invariant: every bullish entry bar must satisfy the shared
    trend gates the strategy declares (close above the 50- and 200-SMA)."""
    from swingbot.core.entry_filters import ENTRY_FUNCS, compute_shared_gates
    g = compute_shared_gates(market_df)
    for strat in GATED_BY_MA50:
        if strat not in ENTRY_FUNCS:
            continue
        bull, bear = ENTRY_FUNCS[strat](market_df, "4w")
        assert_entry_invariants(bull, bear, market_df)
        fired = bull[bull].index
        assert g["trend50_bull"].loc[fired].all(), f"{strat}: bull entry below 50-SMA"
        assert g["bull_regime"].loc[fired].all(), f"{strat}: bull entry outside bull regime"


def test_ema_cross_not_extended(market_df):
    """No bullish EMA entry may be more than ext_atr ATRs above the fast EMA."""
    from swingbot.core.entry_filters import ema_cross_entries, compute_shared_gates, DEFAULT_PARAMS
    from swingbot.core.indicators import ema
    from swingbot.core.strategy_types import HORIZONS
    g = compute_shared_gates(market_df)
    bull, _ = ema_cross_entries(market_df, "4w")
    fast = ema(market_df["Close"], HORIZONS["4w"]["ema_fast"])
    cap = DEFAULT_PARAMS["EMA Crossover"]["ext_atr"]
    ext = (market_df["Close"] - fast).abs() / g["atr14"]
    assert (ext[bull] <= cap + 1e-9).all()


def test_vwap_entries_flat_market_produces_nothing(flat_df):
    from swingbot.core.entry_filters import vwap_entries
    bull, bear = vwap_entries(flat_df, "4w")
    assert not bull.any() and not bear.any()   # atr_floor gate blocks dead tape


GATED_BY_MA50.extend(["MACD", "MA Ribbon"])


def test_macd_bullish_entries_have_rising_histogram(market_df):
    from swingbot.core.entry_filters import macd_entries
    from swingbot.core.indicators import macd as macd_fn
    from swingbot.core.strategy_types import MACD_PERIODS_BY_HORIZON
    bull, bear = macd_entries(market_df, "4w")
    assert_entry_invariants(bull, bear, market_df)
    f, s, sig = MACD_PERIODS_BY_HORIZON["4w"]
    hist = macd_fn(market_df["Close"], fast=f, slow=s, signal=sig)["histogram"]
    fired = bull[bull].index
    assert (hist.loc[fired] > hist.shift(1).loc[fired]).all()
    assert (hist.shift(1).loc[fired] > hist.shift(2).loc[fired]).all()


def test_ma_ribbon_slope_agreement(market_df):
    from swingbot.core.entry_filters import ma_ribbon_entries, RIBBON_PERIODS_BY_HORIZON
    bull, bear = ma_ribbon_entries(market_df, "4w")
    assert_entry_invariants(bull, bear, market_df)
    _, _, slow_p = RIBBON_PERIODS_BY_HORIZON["4w"]
    slow_sma = market_df["Close"].rolling(slow_p).mean()
    fired = bull[bull].index
    assert (slow_sma.loc[fired] > slow_sma.shift(10).loc[fired]).all()


GATED_BY_MA50.extend(["Support/Resistance", "Break & Retest"])


def test_sr_bullish_breakout_bar_quality(market_df):
    """Every S/R bullish entry must close in the top 40% of its bar and not
    gap more than 3% above the broken level."""
    from swingbot.core.entry_filters import support_resistance_entries, DEFAULT_PARAMS
    from swingbot.core.strategy_types import HORIZONS
    bull, bear = support_resistance_entries(market_df, "4w")
    assert_entry_invariants(bull, bear, market_df)
    lb = HORIZONS["4w"]["sr_lookback"]
    resistance = market_df["High"].rolling(lb).max().shift(1)
    frac = DEFAULT_PARAMS["Support/Resistance"]["close_frac"]
    for ts in bull[bull].index:
        row = market_df.loc[ts]
        rng = row["High"] - row["Low"]
        assert row["Close"] >= row["High"] - frac * rng
        assert row["Open"] <= resistance.loc[ts] * 1.03


def test_break_retest_entry_bar_bounces(market_df):
    """B&R bullish entries must close above the prior bar's high (the retest
    has already turned, we are not catching the falling knife into the level)."""
    from swingbot.core.entry_filters import break_retest_entries
    bull, bear = break_retest_entries(market_df, "4w")
    assert_entry_invariants(bull, bear, market_df)
    prev_high = market_df["High"].shift(1)
    fired = bull[bull].index
    assert (market_df["Close"].loc[fired] > prev_high.loc[fired]).all()
