"""v230 A1: the placebo universes reproduce from their seeds and carry no
serial structure (shuffled) or drift (gbm) by construction."""
import hashlib
import json
import zlib

import numpy as np
import pandas as pd
import pytest

from swingbot.core.backtesting.screen import indicators, placebo
from tests.backtesting.screen.helpers import random_walk

CAL = pd.bdate_range("2010-01-04", periods=600)


def _source(tmp_path, n=600, tickers=("AAA", "BBB", "CCC")):
    """A fake cache: three tickers, SPY, two context-only stems, a coverage file."""
    src = tmp_path / "src"
    src.mkdir()
    for seed, t in enumerate(tickers, start=1):
        random_walk(n, seed=seed).to_csv(src / f"{t}.csv", index_label="Date")
    random_walk(n, seed=99).to_csv(src / "SPY.csv", index_label="Date")
    for stem in ("^VIX", "BREADTH_ATR1"):
        random_walk(n, seed=98).to_csv(src / f"{stem}.csv", index_label="Date")
    (src / "_coverage_sp500_pit.json").write_text("{}", encoding="utf-8")
    return src


def test_ticker_seed_is_the_base_and_the_crc_of_the_name():
    assert placebo.ticker_seed("G001") == [42, zlib.crc32(b"G001")]
    assert placebo.ticker_seed("G001", base=7) == [7, zlib.crc32(b"G001")]


def test_trading_calendar_cuts_and_sorts(tmp_path):
    src = _source(tmp_path)
    cal = placebo.trading_calendar(src / "SPY.csv", "2010-02-01", "2010-03-31")
    assert cal[0] == pd.Timestamp("2010-02-01") and cal[-1] == pd.Timestamp("2010-03-31")
    assert cal.is_monotonic_increasing and cal.is_unique
    with pytest.raises(ValueError, match="no session"):
        placebo.trading_calendar(src / "SPY.csv", "2030-01-01", "2030-12-31")


def test_read_frame_keeps_ohlcv_sorted_and_unique(tmp_path):
    df = random_walk(5, seed=1)
    shuffled = pd.concat([df.iloc[[3, 1, 0, 2, 4]], df.iloc[[1]]])
    shuffled.assign(Extra=1).to_csv(tmp_path / "X.csv", index_label="Date")
    out = placebo.read_frame(tmp_path / "X.csv")
    assert list(out.columns) == list(placebo.OHLCV)
    assert out.index.is_monotonic_increasing and out.index.is_unique and len(out) == 5


def test_market_states_are_seeded_and_switch():
    cal = pd.bdate_range("2010-01-04", periods=2516)
    a, b = placebo.market_states(cal, 42), placebo.market_states(cal, 42)
    assert a.dtype == bool and np.array_equal(a, b)
    assert not np.array_equal(a, placebo.market_states(cal, 43))
    assert 0.05 < a.mean() < 0.35


def test_gbm_frame_is_seeded_per_ticker_and_consistent():
    stressed = np.zeros(len(CAL), dtype=bool)
    one = placebo.gbm_frame("G001", CAL, level=0.02, stressed=stressed)
    pd.testing.assert_frame_equal(one, placebo.gbm_frame("G001", CAL, level=0.02,
                                                         stressed=stressed))
    other = placebo.gbm_frame("G002", CAL, level=0.02, stressed=stressed)
    assert not one["Close"].equals(other["Close"])
    assert not one["Close"].equals(
        placebo.gbm_frame("G001", CAL, level=0.02, stressed=stressed, seed=7)["Close"])
    assert list(one.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert (one["High"] >= one[["Open", "Close"]].max(axis=1)).all()
    assert (one["Low"] <= one[["Open", "Close"]].min(axis=1)).all()
    assert one.index.equals(CAL)


def test_gbm_median_atr_pct_lands_on_its_level():
    cal = pd.bdate_range("2010-01-04", periods=2516)
    stressed = placebo.market_states(cal, 42)
    ratios = []
    for i in range(10):
        df = placebo.gbm_frame(f"G{i:03d}", cal, level=0.02, stressed=stressed)
        ratios.append(np.nanmedian(indicators.atr(df) / df["Close"]) / 0.02)
    assert 0.85 < np.mean(ratios) < 1.15


def test_gbm_is_driftless():
    cal = pd.bdate_range("2010-01-04", periods=2516)
    stressed = np.zeros(len(cal), dtype=bool)
    gross = [df["Close"].iloc[-1] / df["Close"].iloc[0]
             for df in (placebo.gbm_frame(f"G{i:03d}", cal, level=0.015, stressed=stressed)
                        for i in range(60))]
    assert abs(np.mean(gross) - 1.0) < 0.25


def test_atr_pct_quartiles_skip_index_and_context_files(tmp_path):
    src = _source(tmp_path)
    assert [p.stem for p in placebo._source_files(src)] == ["AAA", "BBB", "CCC"]
    q = placebo.atr_pct_quartiles(src, CAL)
    assert len(q) == 4 and list(q) == sorted(q) and all(v > 0 for v in q)
    only = placebo.atr_pct_quartiles(src, CAL, tickers=["AAA"])
    assert len(set(only)) == 1
    with pytest.raises(ValueError, match="no ATR%"):
        placebo.atr_pct_quartiles(src, CAL, tickers=["ZZZ"])
