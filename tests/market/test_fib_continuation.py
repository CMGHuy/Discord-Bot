"""v103 C: Fibonacci Continuation -- a held retracement's break of the swing extreme."""
import numpy as np
import pandas as pd

from swingbot.core.market import entry_filters as ef
from swingbot.core.market.indicators import atr
from swingbot.core.market.strategy_types import HORIZONS
from swingbot.core.planning.params import STRUCTURE_BUFFER_ATR
from tests.helpers import make_ohlcv
from tests.market.test_fib_sr_confluence import _trending_frame

HZ = "2w"


def _breakout_bars(retrace_low=105.0, pullback_bars=3, breakout_close=110.5):
    """Flat pad; impulse A=100 -> H=110; retrace; then one breakout bar."""
    lookback = HORIZONS[HZ]["fib_lookback"]
    assert lookback >= 5 + pullback_bars + 1, "window must reach back to the swing low"
    pad = [(100.8, 101.0, 100.6, 100.8)] * (lookback + 30)
    impulse = [(100.2, 100.8, 100.0, 100.6)]
    for close in (103.0, 106.0, 108.5):
        impulse.append((close - 1.0, close + 0.5, close - 1.2, close))
    impulse.append((109.0, 110.0, 108.8, 109.6))
    pull = []
    for position in range(1, pullback_bars + 1):
        low = 110.0 - (110.0 - retrace_low) * position / pullback_bars
        pull.append((low + 0.8, low + 1.0, low, low + 0.5))
    breakout = [(109.8, breakout_close + 0.2, 109.5, breakout_close)]
    after = [(breakout_close, breakout_close + 0.3, breakout_close - 0.3, breakout_close)] * 3
    bars = pad + impulse + pull + breakout + after
    return bars, len(pad) + len(impulse) + len(pull)


def _frame(**kwargs):
    bars, index = _breakout_bars(**kwargs)
    return make_ohlcv(bars, start="2015-01-02"), index


def _mirror(bars):
    return [(210 - open_, 210 - low, 210 - high, 210 - close) for open_, high, low, close in bars]


def test_breakout_fires_exactly_once():
    df, index = _frame()
    signal = ef.fib_continuation_frame(df, HZ, "bullish")["signal"]
    assert bool(signal.iloc[index]) and int(signal.sum()) == 1


def test_structure_values_at_the_breakout():
    df, index = _frame()
    row = ef.fib_continuation_frame(df, HZ, "bullish").iloc[index]
    assert row["level"] == 110.0 and row["impulse"] == 10.0 and row["retrace"] == 105.0
    assert row["depth"] == 0.5
    assert row["stop"] == 110.0 - ef.FIB_CONTINUATION_STOP_ATR * float(atr(df, 14).iloc[index])


def test_too_deep_does_not_fire_unless_d_max_allows():
    df, index = _frame(retrace_low=103.0)
    assert not ef.fib_continuation_frame(df, HZ, "bullish")["signal"].any()
    wide = ef.fib_continuation_frame(df, HZ, "bullish", params={"d_max": 0.786})
    assert bool(wide["signal"].iloc[index])


def test_too_shallow_does_not_fire():
    df, _ = _frame(retrace_low=107.0)
    assert not ef.fib_continuation_frame(df, HZ, "bullish")["signal"].any()


def test_one_bar_pullback_does_not_fire():
    df, _ = _frame(pullback_bars=1)
    assert not ef.fib_continuation_frame(df, HZ, "bullish")["signal"].any()


def test_extended_breakout_bar_is_dropped_not_capped():
    df, _ = _frame(breakout_close=113.0)
    assert not ef.fib_continuation_frame(df, HZ, "bullish")["signal"].any()


def test_bearish_mirror_fires_once():
    bars, index = _breakout_bars()
    df = make_ohlcv(_mirror(bars), start="2015-01-02")
    frame = ef.fib_continuation_frame(df, HZ, "bearish")
    assert bool(frame["signal"].iloc[index]) and int(frame["signal"].sum()) == 1
    assert frame["level"].iloc[index] == 100.0 and frame["retrace"].iloc[index] == 105.0


def test_flat_frame_never_fires():
    df = make_ohlcv([100.0] * 120, start="2015-01-02", spread=0.0)
    for direction in ("bullish", "bearish"):
        frame = ef.fib_continuation_frame(df, HZ, direction)
        assert not frame["signal"].any() and frame["depth"].isna().all()


def test_nan_bars_do_not_fire():
    df, index = _frame()
    df = df.copy()
    df.iloc[index - 2, :4] = np.nan
    assert not ef.fib_continuation_frame(df, HZ, "bullish")["signal"].iloc[index]


def test_no_lookahead_truncation():
    df = _trending_frame(400, 0.06, seed=2)
    full = ef.fib_continuation_frame(df, "4w", "bullish")
    for index in range(60, len(df), 13):
        truncated = ef.fib_continuation_frame(df.iloc[:index + 1], "4w", "bullish").iloc[-1]
        pd.testing.assert_series_equal(truncated, full.iloc[index], check_names=False)


def test_at_bar_returns_structure_only_on_a_signal():
    df, index = _frame()
    got = ef.fib_continuation_at(df, index, HZ, "bullish")
    assert got["level"] == 110.0 and set(got) == {"level", "impulse", "retrace", "stop"}
    assert ef.fib_continuation_at(df, index + 1, HZ, "bullish") is None


def test_continuation_at_accepts_negative_index():
    df, index = _frame()
    df = df.iloc[:index + 1]
    assert ef.fib_continuation_at(df, -1, HZ, "bullish") == ef.fib_continuation_at(df, index, HZ, "bullish")


def test_entries_compose_the_shared_gates():
    df = _trending_frame(400, 0.06, seed=2)
    gates = ef.compute_shared_gates(df)
    bull, bear = ef.fib_continuation_entries(df, "4w")
    raw_bull = ef.fib_continuation_frame(df, "4w", "bullish")["signal"]
    expected = (raw_bull & gates["bull_regime"] & gates["trend50_bull"]
                & gates["atr_floor"] & gates["atr_calm"] & gates["vol_ok"])
    pd.testing.assert_series_equal(bull, expected.fillna(False).astype(bool), check_names=False)
    assert bear.dtype == bool


def test_ships_masked_in_entries_for():
    df, _ = _frame()
    regimes = pd.Series("unknown", index=df.index)
    bull, bear = ef.entries_for("Fibonacci Continuation", df, HZ, regimes=regimes)
    assert not bull.any() and not bear.any()


def test_registered_once_and_buffer_matches_planning():
    assert ef.ENTRY_FUNCS["Fibonacci Continuation"] is ef.fib_continuation_entries
    assert ef.FIB_CONTINUATION_STOP_ATR == STRUCTURE_BUFFER_ATR
