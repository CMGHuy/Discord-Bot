"""v129: break_retest_entries exposes its broken-level series. The refactor
must leave the boolean signals byte-identical (spec § Testing), checked
against a frozen copy of the pre-v129 function on the parity fixtures."""
import numpy as np
import pytest

from swingbot.core.market import entry_filters as ef
from swingbot.core.market.strategy_types import HORIZONS
from tests.fixtures.ohlcv_parity import load_ohlcv

CASES = [(t, h) for t in ("DELL", "TSLA", "DOCU") for h in ("2m", "3m", "4m")]


def _legacy_break_retest_entries(df, horizon_key, params=None):
    """Frozen verbatim copy of entry_filters.break_retest_entries as of
    63d416c8 (pre-v129). Never edit."""
    p = ef._params("Break & Retest", params)
    h = HORIZONS[horizon_key]
    g = ef.compute_shared_gates(df)
    close, high, low = df["Close"], df["High"], df["Low"]
    lookback = h["sr_lookback"]

    resistance = high.rolling(lookback).max().shift(lookback)
    support = low.rolling(lookback).min().shift(lookback)
    vol_ratio = df["Volume"] / df["Volume"].rolling(20).mean()
    recent = ef.BRT_RECENT_BARS.get(horizon_key, 10)

    broke_up = (high.rolling(recent).max().shift(1) > resistance) & \
               (vol_ratio.rolling(recent).max().shift(1) >= ef.SR_VOLUME_MULTIPLE)
    broke_dn = (low.rolling(recent).min().shift(1) < support) & \
               (vol_ratio.rolling(recent).max().shift(1) >= ef.SR_VOLUME_MULTIPLE)

    dist_to_res = (close - resistance) / resistance.replace(0, np.nan) * 100
    dist_to_sup = (close - support) / support.replace(0, np.nan) * 100
    retest_pct = ef.BRT_RETEST_PCT.get(horizon_key, 1.0)

    held_level_bull = low >= resistance * (1 - p["hold_tol_pct"] / 100)
    held_level_bear = high <= support * (1 + p["hold_tol_pct"] / 100)
    turned_bull = close > high.shift(1)
    turned_bear = close < low.shift(1)
    rsi14 = g["rsi14"]

    bullish = (broke_up & dist_to_res.between(0, retest_pct) & held_level_bull & turned_bull
               & rsi14.between(42, 63)
               & g["bull_regime"] & g["trend50_bull"]
               & g["atr_floor"] & g["atr_calm"]).fillna(False)
    bearish = (broke_dn & dist_to_sup.between(-retest_pct, 0) & held_level_bear & turned_bear
               & rsi14.between(37, 58)
               & g["bear_regime"] & g["trend50_bear"]
               & g["atr_floor"] & g["atr_calm"]).fillna(False)
    return bullish, bearish


@pytest.mark.parametrize(("ticker", "horizon_key"), CASES)
def test_signals_byte_identical_to_pre_v129(ticker, horizon_key):
    df = load_ohlcv(ticker)
    new_bull, new_bear = ef.break_retest_entries(df, horizon_key)
    old_bull, old_bear = _legacy_break_retest_entries(df, horizon_key)
    assert new_bull.equals(old_bull)
    assert new_bear.equals(old_bear)


def test_level_at_reads_resistance_for_bulls_and_support_for_bears():
    df = load_ohlcv("DELL")
    resistance, support = ef._break_retest_levels(df, "2m")
    i = 849   # a real DELL 2m Break & Retest entry bar (see V129-4)
    assert ef.break_retest_level_at(df, i, "2m", "bullish") == float(resistance.iloc[i])
    assert ef.break_retest_level_at(df, i, "2m", "bearish") == float(support.iloc[i])


def test_level_at_is_none_during_warm_up():
    df = load_ohlcv("DELL")
    assert ef.break_retest_level_at(df, 5, "2m", "bullish") is None


def test_level_at_never_sees_future_bars():
    df = load_ohlcv("DELL")
    for t in (400, 849, 1246):
        for direction in ("bullish", "bearish"):
            assert (ef.break_retest_level_at(df, t, "3m", direction)
                    == ef.break_retest_level_at(df.iloc[:t + 1], t, "3m", direction))
