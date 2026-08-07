"""Shared synthetic-OHLCV builders for backtest/entry-filter tests.

All series are deterministic (fixed seed where randomness is used) so
test failures are reproducible.
"""
import os
import sys

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


def assert_rendered(path, min_colors=16):
    """Assert `path` is a real rendered chart, not a blank canvas or a stub.

    Replaces the `os.path.getsize(path) > N` proxy the chart tests used to
    share. That proxy conflated "big file" with "actually drew something": it
    passed for a large blank canvas, and it broke the moment render DPI
    changed (at dpi=30 a genuine treemap render came in at 3719 bytes against
    a 5000-byte threshold). Counting distinct colors is resolution-
    independent, so it survives any DPI and is a strictly stronger check.
    """
    from PIL import Image

    assert os.path.exists(path), f"no file at {path}"
    with Image.open(path) as img:
        img.load()
        assert img.width > 0 and img.height > 0, f"{path} has zero extent"
        colors = img.convert("RGB").getcolors(maxcolors=1 << 24)
    assert colors is not None, f"{path}: too many colors to count (unexpected)"
    assert len(colors) >= min_colors, (
        f"{path} looks blank: only {len(colors)} distinct colors "
        f"(expected >= {min_colors})"
    )


def assert_entry_invariants(bull, bear, df):
    """Every entry function must return clean, aligned, non-overlapping booleans."""
    for s in (bull, bear):
        assert s.dtype == bool, f"dtype is {s.dtype}, expected bool"
        assert s.index.equals(df.index)
        assert not s.isna().any()
    assert not (bull & bear).any(), "a bar fired bullish AND bearish"


TEST_DPI = 30


@pytest.fixture(autouse=True)
def _low_dpi_renders(monkeypatch):
    """Render test charts at a low DPI -- the tier's dominant cost is raster
    resolution, which nothing asserts on.

    The chart tests draw 16x9 figures at dpi=110-150; forcing dpi=30 measured
    the 5 core chart files down from 84s to 44s. Safe because the render
    assertions are `assert_rendered`, which counts colors rather than bytes
    (see T9/T10) -- the byte-threshold proxies this would have broken are gone.

    Set SWINGBOT_TEST_FULL_DPI=1 to render at production fidelity when you
    need to actually look at a test-generated PNG.
    """
    if os.environ.get("SWINGBOT_TEST_FULL_DPI"):
        return

    # Only patch when matplotlib is already loaded. A chart test imports it at
    # module scope, so it is present by the time this runs; a non-chart test
    # never triggers the import. This keeps the fast tier free of matplotlib's
    # 3.8s-per-process import, which is much of why that tier is fast at all.
    if "matplotlib" not in sys.modules:
        return

    import matplotlib.pyplot as plt
    from matplotlib.figure import Figure

    def _forced(fn):
        def wrapper(*args, **kwargs):
            kwargs["dpi"] = TEST_DPI
            return fn(*args, **kwargs)
        return wrapper

    monkeypatch.setattr(Figure, "savefig", _forced(Figure.savefig))
    monkeypatch.setattr(plt, "figure", _forced(plt.figure))
    monkeypatch.setattr(plt, "subplots", _forced(plt.subplots))


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
