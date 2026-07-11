"""Shared synthetic-OHLCV builders for backtest/entry-filter tests.

All series are deterministic (fixed seed where randomness is used) so
test failures are reproducible.
"""
import numpy as np
import pandas as pd
import pytest


def make_ohlcv(closes, spread_pct=1.0, volumes=None, start="2019-01-01"):
    """Build an OHLCV frame from a close series. High/Low straddle the close
    by spread_pct/2 each side; Open is the prior close."""
    closes = np.asarray(closes, dtype=float)
    n = len(closes)
    idx = pd.bdate_range(start, periods=n)
    half = closes * (spread_pct / 100) / 2
    open_ = np.concatenate([[closes[0]], closes[:-1]])
    vol = np.full(n, 1_000_000.0) if volumes is None else np.asarray(volumes, dtype=float)
    return pd.DataFrame(
        {"Open": open_, "High": closes + half, "Low": closes - half,
         "Close": closes, "Volume": vol},
        index=idx,
    )


def make_trend_df(n, daily_pct, start_price=100.0, spread_pct=2.0):
    closes = start_price * (1 + daily_pct / 100) ** np.arange(n)
    return make_ohlcv(closes, spread_pct=spread_pct)


def assert_entry_invariants(bull, bear, df):
    """Every entry function must return clean, aligned, non-overlapping booleans."""
    for s in (bull, bear):
        assert s.dtype == bool, f"dtype is {s.dtype}, expected bool"
        assert s.index.equals(df.index)
        assert not s.isna().any()
    assert not (bull & bear).any(), "a bar fired bullish AND bearish"


@pytest.fixture
def uptrend_df():
    return make_trend_df(500, +0.20)


@pytest.fixture
def downtrend_df():
    return make_trend_df(500, -0.20)


@pytest.fixture
def flat_df():
    return make_ohlcv(np.full(500, 100.0), spread_pct=0.1)


@pytest.fixture
def market_df():
    """1500 bars of seeded random walk with drift + volatility clustering --
    realistic enough for smoke/invariant tests across strategies."""
    rng = np.random.default_rng(42)
    rets = rng.normal(0.0005, 0.015, 1500)
    closes = 100 * np.cumprod(1 + rets)
    vols = rng.integers(500_000, 3_000_000, 1500).astype(float)
    return make_ohlcv(closes, spread_pct=2.0, volumes=vols)
