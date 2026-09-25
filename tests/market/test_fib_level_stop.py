"""v103 A: Fibonacci level-stop -- stop just past the tested level; drop, never cap."""
import numpy as np
import pandas as pd

from swingbot import config
from swingbot.core.market import entry_filters as ef
from swingbot.core.market.indicators import atr
from swingbot.core.market.strategy_types import HORIZONS
from swingbot.core.risk_limits import capped_planned_loss_pct
from tests.market.test_fib_sr_confluence import (
    _bear_signal_frame, _bull_signal_frame, _reference_no_confluence,
)


def _set(monkeypatch, b, directions):
    monkeypatch.setattr(config, "FIB_LEVEL_STOP_ATR", b, raising=False)
    monkeypatch.setattr(config, "FIB_LEVEL_STOP_DIRECTIONS", directions, raising=False)


def _independent_stop(df, horizon, direction, b):
    """Row-by-row re-derivation sharing no code with the helper."""
    lb = HORIZONS[horizon]["fib_lookback"]
    ratios = ef.DEFAULT_PARAMS["Fibonacci"]["ratios"]
    a = atr(df, 14)
    cap = capped_planned_loss_pct(HORIZONS[horizon]["max_risk_pct"])
    out = []
    for i in range(len(df)):
        if i < lb - 1 or np.isnan(a.iloc[i]):
            out.append(np.nan)
            continue
        hi = df["High"].iloc[i - lb + 1:i + 1].max()
        lo = df["Low"].iloc[i - lb + 1:i + 1].min()
        close = df["Close"].iloc[i]
        tested = min((hi - r * (hi - lo) for r in ratios), key=lambda lv: abs(lv - close))
        stop = tested - b * a.iloc[i] if direction == "bullish" else tested + b * a.iloc[i]
        losing = stop < close if direction == "bullish" else stop > close
        fits = abs(close - stop) / close * 100 <= cap + 1e-9
        out.append(stop if (losing and fits) else np.nan)
    return pd.Series(out, index=df.index)


def test_flag_off_is_bit_identical_to_an_independent_reference(monkeypatch):
    df_bull, df_bear = _bull_signal_frame(), _bear_signal_frame()
    ref_bull, _ = _reference_no_confluence(df_bull, "4w")
    _, ref_bear = _reference_no_confluence(df_bear, "4w")
    assert ref_bull.any() and ref_bear.any(), "reference frames must fire"
    for b, directions in ((0.0, ""), (0.25, ""), (0.0, "bullish,bearish")):
        _set(monkeypatch, b, directions)
        bull, _ = ef.fibonacci_entries(df_bull, "4w")
        _, bear = ef.fibonacci_entries(df_bear, "4w")
        pd.testing.assert_series_equal(bull, ref_bull)
        pd.testing.assert_series_equal(bear, ref_bear)


def test_helper_matches_an_independent_rederivation():
    for df in (_bull_signal_frame(), _bear_signal_frame()):
        for direction in ("bullish", "bearish"):
            for b in (0.1, 0.5):
                got = ef.fib_level_stop_series(df, "4w", direction, b)
                pd.testing.assert_series_equal(
                    got, _independent_stop(df, "4w", direction, b), check_names=False,
                )
    assert ef.fib_level_stop_series(_bull_signal_frame(), "4w", "bullish", 0.1).notna().any()


def test_entries_drop_exactly_the_ineligible_bars(monkeypatch):
    df_bull, df_bear = _bull_signal_frame(), _bear_signal_frame()
    _set(monkeypatch, 0.0, "")
    bull0, _ = ef.fibonacci_entries(df_bull, "4w")
    _, bear0 = ef.fibonacci_entries(df_bear, "4w")
    _set(monkeypatch, 0.1, "bullish,bearish")
    bull1, _ = ef.fibonacci_entries(df_bull, "4w")
    _, bear1 = ef.fibonacci_entries(df_bear, "4w")
    keep_bull = ef.fib_level_stop_series(df_bull, "4w", "bullish", 0.1).notna()
    keep_bear = ef.fib_level_stop_series(df_bear, "4w", "bearish", 0.1).notna()
    pd.testing.assert_series_equal(bull1, bull0 & keep_bull, check_names=False)
    pd.testing.assert_series_equal(bear1, bear0 & keep_bear, check_names=False)


def test_direction_scope_leaves_the_other_direction_alone(monkeypatch):
    df_bull = _bull_signal_frame()
    ref_bull, _ = _reference_no_confluence(df_bull, "4w")
    _set(monkeypatch, 0.1, "bearish")
    bull, _ = ef.fibonacci_entries(df_bull, "4w")
    pd.testing.assert_series_equal(bull, ref_bull)


def test_drop_never_cap():
    stops = ef.fib_level_stop_series(_bull_signal_frame(), "4w", "bullish", 50.0)
    assert stops.isna().all(), "a stop past the 2% cap must be dropped, not dragged to the cap"


def test_no_lookahead_truncation():
    df = _bull_signal_frame()
    full = ef.fib_level_stop_series(df, "4w", "bullish", 0.25)
    for k in range(60, len(df), 17):
        trunc = ef.fib_level_stop_series(df.iloc[:k + 1], "4w", "bullish", 0.25).iloc[-1]
        assert (np.isnan(trunc) and np.isnan(full.iloc[k])) or trunc == full.iloc[k]


def test_at_bar_reads_the_same_series(monkeypatch):
    df = _bull_signal_frame()
    _set(monkeypatch, 0.0, "bullish")
    assert ef.fib_level_stop_at(df, 250, "4w", "bullish") is None
    _set(monkeypatch, 0.1, "bullish")
    assert ef.fib_level_stop_at(df, 250, "4w", "bearish") is None
    series = ef.fib_level_stop_series(df, "4w", "bullish", 0.1)
    for k in (120, 250, len(df) - 1):
        got = ef.fib_level_stop_at(df, k, "4w", "bullish")
        assert (np.isnan(got) and np.isnan(series.iloc[k])) or got == series.iloc[k]


def test_at_bar_accepts_negative_index(monkeypatch):
    df = _bull_signal_frame()
    _set(monkeypatch, 0.1, "bullish")
    last = ef.fib_level_stop_at(df, len(df) - 1, "4w", "bullish")
    neg = ef.fib_level_stop_at(df, -1, "4w", "bullish")
    assert (np.isnan(last) and np.isnan(neg)) or last == neg


def test_directions_parsing_is_forgiving(monkeypatch):
    _set(monkeypatch, 0.25, " Bullish , bearish ,sideways")
    assert ef._fib_level_stop_config() == (0.25, frozenset({"bullish", "bearish"}))


def test_nan_bars_give_nan_not_raise():
    df = _bull_signal_frame().copy()
    df.iloc[200:206, :4] = np.nan
    stops = ef.fib_level_stop_series(df, "4w", "bullish", 0.25)
    assert stops.iloc[200:206].isna().all()
