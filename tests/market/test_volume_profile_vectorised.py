"""v251: compute_volume_profile without iterrows, byte-identical to the old loop.

`_reference_compute_volume_profile` is a verbatim copy of
swingbot/core/market/signals.py::compute_volume_profile as it stood at
a4663eb0, iterrows loop included. Every case compares the new function with
it: values by float.hex, element types by type() (np.float64 subclasses
float, so isinstance cannot tell them apart), and raised exception types.
Never edit the reference to make a case pass -- a difference is a bug in
signals.py (spec v251, Exactness rules).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from swingbot.core.market.signals import compute_volume_profile


def _reference_compute_volume_profile(
    df: pd.DataFrame, lookback: int, n_bins: int = 20,
    price_min: float = None, price_max: float = None,
) -> dict | None:
    """
    Bins the last `lookback` bars' trading range into `n_bins` price
    buckets and sums each bucket's traded volume -- the full Volume
    Profile histogram, not just its single busiest bucket. compute_hvn_level
    (below) calls this and keeps only the winning bucket; trade_chart.py's
    left-side volume profile panel uses the full histogram to draw every
    bucket, not just the busiest one.

    By default (`price_min`/`price_max` both None, the only way every
    existing caller uses this), the bucketed price range is exactly the
    last `lookback` bars' own High/Low extremes, same as always. Passing
    explicit `price_min`/`price_max` overrides that -- trade_chart.py's
    panel does this, passing the price PANEL's actual final y-axis range
    (which is padded, and further widened to fit the entry/stop/target
    lines -- an entry can be a deliberate pullback level well away from
    where price has recently traded, not necessarily "now"). Without
    this, buckets only covered the recent window's own narrow range,
    leaving the portion of the panel above/below that range with no
    buckets at all -- a visible unbinned gap wherever the chart's visible
    prices (including a distant entry/stop/target) fell outside it.

    Returns a dict with:
      - "bin_edges": list of n_bins+1 price boundaries, low to high
      - "bin_volumes": list of n_bins summed-volume totals, one per bucket,
        in the same low-to-high order as bin_edges
      - "poc_index": index of the busiest bucket (Point of Control)
      - "poc_price": price at the center of that bucket
      - "poc_pct": that bucket's % share of total period volume

    Returns None if there isn't enough history, or the resulting range
    (explicit or derived) is flat/inverted.
    """
    if len(df) < lookback + 2:
        return None
    window = df.iloc[-lookback:]
    if price_min is None:
        price_min = float(window["Low"].min())
    if price_max is None:
        price_max = float(window["High"].max())
    price_range = price_max - price_min
    if price_range <= 0:
        return None

    bin_size = price_range / n_bins
    bins = [0.0] * n_bins
    for _, row in window.iterrows():
        mid = (float(row["High"]) + float(row["Low"])) / 2
        # A bar's midpoint can fall outside an explicitly widened range
        # only if it's narrower than the window's own extremes (not the
        # normal case here, since the panel only ever widens); skip
        # rather than clamp so volume never gets misattributed to an
        # edge bucket it didn't actually trade in.
        if mid < price_min or mid > price_max:
            continue
        idx = min(max(int((mid - price_min) / bin_size), 0), n_bins - 1)
        bins[idx] += float(row["Volume"])

    total_vol = sum(bins)
    poc_idx = bins.index(max(bins)) if total_vol > 0 else n_bins // 2
    bin_edges = [price_min + i * bin_size for i in range(n_bins + 1)]
    poc_price = price_min + (poc_idx + 0.5) * bin_size
    poc_pct = (bins[poc_idx] / total_vol * 100) if total_vol else 0.0

    return {
        "bin_edges": bin_edges,
        "bin_volumes": bins,
        "poc_index": poc_idx,
        "poc_price": poc_price,
        "poc_pct": poc_pct,
    }


def _canon(value):
    """Exact, comparable form: lists stay lists, floats become (type, hex)."""
    if isinstance(value, list):
        return ("list", [_canon(v) for v in value])
    if isinstance(value, dict):
        return {key: _canon(v) for key, v in value.items()}
    if isinstance(value, (float, np.floating)):
        return (type(value).__name__, float.hex(float(value)))
    return (type(value).__name__, value)


def _outcome(fn, df, lookback, **kwargs):
    try:
        return ("ok", _canon(fn(df, lookback, **kwargs)))
    except Exception as exc:  # the exception type is part of the contract
        return ("raise", type(exc).__name__)


def _kind(outcome):
    """"ok", or the raised exception's type name."""
    return outcome[1] if outcome[0] == "raise" else "ok"


def _assert_matches_oracle(df, lookback, **kwargs):
    expected = _outcome(_reference_compute_volume_profile, df, lookback, **kwargs)
    assert _outcome(compute_volume_profile, df, lookback, **kwargs) == expected
    return expected


def _framed(highs, lows, volumes, volume_dtype=None):
    """The given bars are the window; two padding bars sit before it, so the
    frame has exactly lookback + 2 rows. Returns (df, lookback)."""
    high = [50.0, 50.0, *highs]
    low = [49.0, 49.0, *lows]
    vols = [1, 1, *volumes]
    volume = pd.array(vols, dtype=volume_dtype) if volume_dtype else vols
    df = pd.DataFrame(
        {"Open": low, "High": high, "Low": low, "Close": high, "Volume": volume},
        index=pd.bdate_range("2024-01-02", periods=len(high)),
    )
    return df, len(highs)


def _edge_bars():
    """Eleven flat bars whose midpoints sit exactly on 100, 101, ..., 110:
    every bin edge of a 100..110 range in 10 bins, both bounds included."""
    prices = [100.0 + k for k in range(11)]
    return prices, list(prices), [0.5 + 1.25 * k for k in range(11)]


def _random_range(df, lookback, mode):
    """mode 0 derived; 1/3 narrower than the window (skips); 2/4 much wider
    (empty buckets); 1/2 as Python float, 3/4 as np.float64 (the chart's type)."""
    if mode == 0:
        return {}
    lo = float(df["Low"].iloc[-lookback:].min())
    hi = float(df["High"].iloc[-lookback:].max())
    width = hi - lo
    bounds = (lo + 0.3 * width, hi - 0.3 * width) if mode in (1, 3) else (lo * 0.5, hi * 1.5)
    cast = np.float64 if mode >= 3 else float
    return {"price_min": cast(bounds[0]), "price_max": cast(bounds[1])}


def _random_case(seed):
    rng = np.random.default_rng(seed)
    n = int(rng.integers(10, 250))
    lookback = int(rng.integers(1, n - 1))
    closes = 100.0 * np.exp(np.cumsum(rng.normal(0.0, 0.02, n)))
    spread = closes * rng.uniform(0.0, 0.03, n)
    df = pd.DataFrame(
        {"Open": closes, "High": closes + spread, "Low": closes - spread,
         "Close": closes, "Volume": rng.uniform(0.0, 5e6, n)},
        index=pd.bdate_range("2020-01-01", periods=n),
    )
    n_bins = int(rng.choice([1, 2, 3, 7, 20, 24, 50]))
    return df, lookback, n_bins, _random_range(df, lookback, seed % 5)


@pytest.mark.parametrize("seed", range(300))
def test_random_frames_match_the_oracle(seed):
    df, lookback, n_bins, bounds = _random_case(seed)
    _assert_matches_oracle(df, lookback, n_bins=n_bins, **bounds)


@pytest.mark.parametrize("bounds", [
    {},
    {"price_min": 100.0, "price_max": 110.0},
    {"price_min": np.float64(100.0), "price_max": np.float64(110.0)},
])
def test_midpoints_on_every_bin_edge_and_the_clamp(bounds):
    df, lookback = _framed(*_edge_bars())
    assert _assert_matches_oracle(df, lookback, n_bins=10, **bounds)[0] == "ok"


@pytest.mark.parametrize("bounds", [
    {"price_min": 103.0, "price_max": 107.0},   # narrower: out-of-range bars skipped
    {"price_min": 50.0, "price_max": 200.0},    # much wider: empty buckets
    {"price_min": 500.0, "price_max": 600.0},   # zero bars in range
    {"price_min": np.float64(500.0), "price_max": np.float64(600.0)},
])
def test_explicit_ranges_match_the_oracle(bounds):
    df, lookback = _framed(*_edge_bars())
    _assert_matches_oracle(df, lookback, n_bins=30, **bounds)


def test_zero_bars_in_range_keeps_python_float_zeros():
    df, lookback = _framed(*_edge_bars())
    result = compute_volume_profile(df, lookback, n_bins=5, price_min=500.0, price_max=600.0)
    assert [type(v) for v in result["bin_volumes"]] == [float] * 5
    assert result["poc_index"] == 2 and result["poc_pct"] == 0.0


def test_all_zero_volume_puts_poc_in_the_middle():
    highs, lows, _ = _edge_bars()
    df, lookback = _framed(highs, lows, [0.0] * 11)
    assert _assert_matches_oracle(df, lookback, n_bins=10)[1]["poc_index"] == ("int", 5)


def test_tied_busiest_buckets_pick_the_first():
    prices = [101.5, 103.5, 105.5, 100.0, 110.0]
    df, lookback = _framed(prices, list(prices), [7.25, 7.25, 1.0, 0.0, 0.0])
    assert _assert_matches_oracle(df, lookback, n_bins=10)[1]["poc_index"] == ("int", 1)


def test_int64_volumes_above_two_to_the_53():
    highs, lows, _ = _edge_bars()
    vols = [2**53 + 1, 2**60 + 3, 7, 2**62 + 5, 9, 11, 2**53 + 3, 13, 15, 17, 19]
    df, lookback = _framed(highs, lows, vols, volume_dtype="int64")
    assert df["Volume"].dtype == np.int64
    _assert_matches_oracle(df, lookback, n_bins=4)


def test_extra_object_column_and_float32_frames():
    df, lookback = _framed(*_edge_bars())
    df["Note"] = "x"
    _assert_matches_oracle(df, lookback, n_bins=7)
    df32, lookback = _framed(*_edge_bars())
    _assert_matches_oracle(df32.astype(np.float32), lookback, n_bins=7)


@pytest.mark.parametrize("bar", [3, 10])   # bar 10 carries the largest volume
def test_nan_volume_propagates_like_the_oracle(bar):
    highs, lows, vols = _edge_bars()
    vols[bar] = float("nan")
    df, lookback = _framed(highs, lows, vols)
    _assert_matches_oracle(df, lookback, n_bins=10)


def test_negative_zero_prices_and_volumes():
    df, lookback = _framed([-0.0, 0.0, 1.0, 2.0], [-0.0, -0.0, 0.5, 1.0], [-0.0, 2.5, -0.0, 4.0])
    _assert_matches_oracle(df, lookback, n_bins=3)
    _assert_matches_oracle(df, lookback, n_bins=3, price_min=-0.0, price_max=2.0)


def test_single_bin():
    df, lookback = _framed(*_edge_bars())
    assert _assert_matches_oracle(df, lookback, n_bins=1)[1]["poc_index"] == ("int", 0)


@pytest.mark.parametrize("volume_dtype", ["object", "Int64", "Float64"])
@pytest.mark.parametrize("bounds, expected", [
    ({}, "TypeError"),                                  # the missing bar is in range
    ({"price_min": 100.0, "price_max": 105.0}, "ok"),   # the missing bar is skipped
])
def test_missing_volume_raises_only_when_in_range(volume_dtype, bounds, expected):
    highs, lows, vols = _edge_bars()
    vols = [int(v * 4) for v in vols]
    vols[10] = None                                     # midpoint 110
    df, lookback = _framed(highs, lows, vols, volume_dtype=volume_dtype)
    assert _kind(_assert_matches_oracle(df, lookback, n_bins=10, **bounds)) == expected


@pytest.mark.parametrize("column, value, bounds, expected", [
    ("High", float("nan"), {}, "ValueError"),
    ("Low", float("nan"), {}, "ValueError"),
    ("High", float("inf"), {}, "ValueError"),
    ("Low", float("-inf"), {}, "ValueError"),
    ("High", float("-inf"), {}, "ok"),
    ("Low", float("inf"), {}, "ok"),
    ("High", float("inf"), {"price_min": 100.0, "price_max": 110.0}, "ok"),
])
def test_non_finite_prices_match_the_oracle(column, value, bounds, expected):
    df, lookback = _framed(*_edge_bars())
    df.loc[df.index[5], column] = value
    assert _kind(_assert_matches_oracle(df, lookback, n_bins=10, **bounds)) == expected


def _volumes_np_sum_cannot_reproduce():
    """200 fractional volumes whose np.sum (pairwise) differs from the
    left-to-right sum -- the case that tells the two orders apart."""
    for seed in range(1000):
        vols = np.random.default_rng(seed).uniform(0.0, 1e6, 200)
        sequential = 0.0
        for v in vols:
            sequential += float(v)
        if float(np.sum(vols)) != sequential:
            return vols, sequential
    pytest.fail("no seed separates np.sum from the sequential sum")


def test_one_bucket_accumulates_in_row_order():
    vols, sequential = _volumes_np_sum_cannot_reproduce()
    assert float(np.sum(vols)) != sequential
    flat = [100.0] * len(vols)
    df, lookback = _framed(flat, list(flat), [float(v) for v in vols])
    result = compute_volume_profile(df, lookback, n_bins=4, price_min=90.0, price_max=110.0)
    assert float.hex(result["bin_volumes"][2]) == float.hex(sequential)
    _assert_matches_oracle(df, lookback, n_bins=4, price_min=90.0, price_max=110.0)
