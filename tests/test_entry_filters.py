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
