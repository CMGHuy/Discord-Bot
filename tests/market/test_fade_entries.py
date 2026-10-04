"""v113 §3 Part A: Downtrend Overbought Fade entries (bars <= t only)."""
import numpy as np
import pandas as pd
import pytest

from swingbot.core.market import entry_filters as ef
from swingbot.core.market import short_entries as se
from swingbot.core.market.strategy_types import (FADE_STRATEGY, SHORT_STRATEGIES, STRATEGY_GATES,
                                                 V104_SHORTS)
from tests.helpers import make_ohlcv

HZ = "1w"
UNMASKED = {"directions": (), "cells": {("bearish", "1w")}}


def fade_df(tail=12, tail_step=0.995):
    """240 bars grinding 200 -> 100 (far under a falling SMA200), two +2% up days
    (RSI(2) ~82.7, then ~93.6 on bar t), then `tail` bars moving by `tail_step`."""
    closes = list(np.linspace(200.0, 100.0, 240))
    close = closes[-1]
    for step in (1.02, 1.02):
        close *= step
        closes.append(close)
    t = len(closes) - 1
    for _ in range(tail):
        close *= tail_step
        closes.append(close)
    df = make_ohlcv(closes, start="2015-01-02")
    df["evt_bars_to_next"] = np.nan
    return df, t


def test_fires_on_the_second_up_day_only():
    df, t = fade_df()
    frame = se.fade_frame(df, HZ)
    assert list(np.flatnonzero(frame["signal"].to_numpy())) == [t]


@pytest.mark.parametrize("m", [1.0, 1.25, 1.5])
def test_plan_columns_are_the_fixed_geometry(m):
    df, t = fade_df()
    row = se.fade_frame(df, HZ, params={"m": m}).iloc[t]
    close = float(df["Close"].iloc[t])
    assert row["level"] == pytest.approx(close)
    assert row["stop"] == pytest.approx(close * 1.02)
    assert row["target_a"] == pytest.approx(close - m * (close * 1.02 - close))
    assert np.isnan(row["target_b"])


@pytest.mark.parametrize("bars,fires", [(0, False), (3, False), (7, False), (8, True), (np.nan, True)])
def test_an_earnings_reaction_within_seven_bars_blocks(bars, fires):
    df, t = fade_df()
    df.loc[df.index[t], "evt_bars_to_next"] = bars
    assert bool(se.fade_frame(df, HZ)["signal"].iloc[t]) is fires


def test_no_earnings_column_means_no_signal():
    df, _ = fade_df()
    assert not se.fade_frame(df.drop(columns=["evt_bars_to_next"]), HZ)["signal"].any()


def test_needs_close_under_a_falling_sma200():
    closes = list(np.linspace(100.0, 200.0, 240))
    close = closes[-1]
    for step in (1.02, 1.02, 0.995):
        close *= step
        closes.append(close)
    df = make_ohlcv(closes, start="2015-01-02")
    df["evt_bars_to_next"] = np.nan
    assert not se.fade_frame(df, HZ)["signal"].any()


@pytest.mark.parametrize("offset", [-1, 0, 3])
def test_truncation_invariance(offset):
    df, t = fade_df()
    cut = t + offset
    assert cut < len(df) - 1
    full = se.fade_frame(df, HZ)
    part = se.fade_frame(df.iloc[:cut + 1], HZ)
    pd.testing.assert_series_equal(part.iloc[-1], full.iloc[cut], check_names=False)


def test_registered_short_only_and_masked_until_a_cell_admits_1w():
    df, t = fade_df()
    bull, bear = ef.ENTRY_FUNCS[se.FADE](df, HZ)
    assert not bull.any() and list(np.flatnonzero(bear.to_numpy())) == [t]
    assert STRATEGY_GATES[se.FADE] == {"directions": ()}
    masked_bull, masked_bear = ef.entries_for(se.FADE, df, HZ)
    assert not masked_bull.any() and not masked_bear.any()
    with ef.gate_override(se.FADE, UNMASKED):
        _, bear_1w = ef.entries_for(se.FADE, df, HZ)
        _, bear_2w = ef.entries_for(se.FADE, df, "2w")
    assert list(np.flatnonzero(bear_1w.to_numpy())) == [t] and not bear_2w.any()


def test_short_lists_and_defaults():
    assert se.FADE == FADE_STRATEGY == "Downtrend Overbought Fade"
    assert SHORT_STRATEGIES == V104_SHORTS + (FADE_STRATEGY, "First Bearish Compression Release")
    assert (se.BULL_TRAP, se.VOL_BREAKDOWN, se.GAP_DRIFT) == V104_SHORTS
    assert ef.DEFAULT_PARAMS[se.FADE] == {"m": 1.0}


def test_structure_at_matches_the_frame_row():
    df, t = fade_df()
    structure = se.structure_at(se.FADE, df, t, HZ)
    close = float(df["Close"].iloc[t])
    assert structure["stop"] == pytest.approx(close * 1.02)
    assert structure["target_a"] == pytest.approx(close * 0.98)
    assert se.structure_at(se.FADE, df, t - 1, HZ) is None
