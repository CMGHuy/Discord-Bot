# v251 — Volume profile without iterrows: a byte-identical vectorised loop (V245-5b) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V251-1b" -A 300 <this file>`).

**Bump:** bot patch
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [2026-11-26-v251-volume-profile-vectorised-design.md](../specs/2026-11-26-v251-volume-profile-vectorised-design.md)
**Brief:** `.superpowers/briefs/2026-11-26-v251-volume-profile-vectorised.md` (code read at a4663eb0; its excerpts override the spec's line cites where they disagree).

## Goal

`compute_volume_profile` in `swingbot/core/market/signals.py` is the single
largest cost in per-ticker analysis: the v245 profile measured it at 37.9 % of
local analysis time (8.8 s of 23.3 s over 66 tickers), and production still
runs at a p50 of 2.516 s per ticker in shadow mode against v245's 0.7 s
target. Nearly all of that is the per-bar `window.iterrows()` loop, which
builds one pandas Series per bar. The v245 prefix cache cannot absorb it: the
bin edges come from the window's own Low/High, so the forming bar moves every
edge and the histogram is rebuilt on every scan. The only lever is making each
call cheaper.

Once this ships, the loop is gone. For plain numeric frames (every frame the
scan and the charts produce), the histogram is built with array operations:
all midpoints at once, the same strict range test, the same
truncate-then-clamp bucket index, and `np.add.at`, which adds each bucket's
volumes one at a time in row order exactly as `bins[idx] += v` did. Frames
with object or nullable columns go through a row-by-row loop over plain column
lists (no Series per row) so that a missing volume still raises `TypeError`
only on an in-range bar, as today. A non-finite bucket quotient raises what
`int()` raised, instead of numpy's arbitrary integer cast.

It leaves alone everything a user or a backtest sees: the signature, the
return dict, the length guard, the window, the range derivation, and the
whole tail (`sum`, `max`, `index`, edges, POC) stay byte for byte, and no
caller changes. Success is measured in two ways. Parity: a test module holds a
verbatim copy of the old function as an oracle and compares the new one
against it by `float.hex`, by exact element type and by raised exception type,
over 300 seeded random frames and every edge case the spec lists, plus an
order proof that tells sequential from pairwise summation; the v245 scan
golden stays byte-identical. Speed: after the deploy, the controller compares
the production `analysis_phase_report.py` p50 against the 2.516 s baseline,
like for like (same `ANALYSIS_CACHE=shadow` mode); the spec sets no time
threshold.

## Architecture

The loop body (old `signals.py:633-644`) becomes one call,
`bins = _profile_bins(window, price_min, price_max, bin_size, n_bins)`.
`_profile_bins` dispatches on the three column dtypes: numpy int/uint/float
columns go to `_profile_bins_vectorised`, anything else (object, nullable
`Int64`/`Float64`, bool) to `_profile_bins_rowwise`. Both return a list of
Python floats. `_raise_like_int` turns the first non-finite quotient into the
exception `int()` raises. All four helpers live in `signals.py` directly above
`compute_volume_profile`; `signals.py` gains `import numpy as np`. The
complexity of `compute_volume_profile` drops from 11 to 8; every helper is 4
or lower (measured on a probe of this exact code).

**Tech Stack:** Python 3.11, pandas 2.3.3, numpy 2.4.6, pytest.

## Global Constraints

- Every element of `bin_volumes` and `bin_edges`, plus `poc_index`, `poc_price` and `poc_pct`, identical to the old loop's by `float.hex`, with the same `type()` (spec rules 1-2). `bin_volumes` elements are Python `float`, never numpy scalars, including when no bar is in range.
- Each bucket starts at `0.0` and adds its bars' volumes one at a time in window row order; no pairwise or reordered sum (rule 4).
- `sum(bins)`, `max(bins)` and `bins.index(...)` keep running over a Python list (rule 5): the tail after the loop is not edited.
- Same outcome on non-finite prices and missing volumes: the same result, or the same exception type, as the oracle (rules 3, 6).
- No new parameters, no caching, no change to `compute_hvn_level` or any caller (rule 9).
- Every function touched or added stays below cyclomatic complexity 15 (`scripts/dev/complexity_gate.py`).
- `tests/scanning/test_v245_scan_one_golden.py` and its fixture are never regenerated; never set `V245_REGEN_GOLDEN`.
- The new test module lives in `tests/market/` (suite `market-signals`, already listed in `tests/suites.toml`): no suite change.
- No task runs the full suite; CI does after the push.
- The main checkout may hold another session's uncommitted `frontend/` edits: stage by explicit path only, never `git add -A`.
- No `VERSION.json` bump inside the tasks: `Bump: bot patch` is applied by `/close-out`.

## Parallelisation

Strictly sequential: **V251-1 → V251-1b**.

- V251-1b appends tests to the module V251-1 creates (same file).
- V251-1 must copy the oracle from `signals.py` **before** V251-1b replaces the loop (spec § Parallelisation).
- Nothing else in flight may edit `swingbot/core/market/signals.py` lines 585-658 at the same time. v245 part 6 (V245-16/17) also edits the v245 section of `docs/deploy/DEPLOY_HETZNER.md`; if it lands first, re-read that section before V251-1b's doc step.

## Task ledger

| Task | Title | Part | Model | Files | Creates (consumed later) |
|---|---|---|---|---|---|
| V251-1 | Oracle test module: verbatim reference + parity, edge, missing-volume, non-finite and order cases | this file | opus | Create `tests/market/test_volume_profile_vectorised.py` | `_reference_compute_volume_profile(df, lookback, n_bins=20, price_min=None, price_max=None) -> dict \| None`; helpers `_canon(value)`, `_outcome(fn, df, lookback, **kw) -> tuple`, `_kind(outcome) -> str`, `_assert_matches_oracle(df, lookback, **kw) -> tuple`, `_framed(highs, lows, volumes, volume_dtype=None) -> (df, lookback)`, `_edge_bars() -> (highs, lows, vols)` |
| V251-1b | Vectorised rewrite, red tests, complexity gate, golden, deploy-doc soak command | this file | opus | Modify `swingbot/core/market/signals.py`, `tests/market/test_volume_profile_vectorised.py`, `docs/deploy/DEPLOY_HETZNER.md` | `signals._profile_bins(window, price_min, price_max, bin_size, n_bins) -> list[float]`, `signals._raise_like_int(quotients: np.ndarray) -> None`, `_profile_bins_vectorised`, `_profile_bins_rowwise`, `_is_plain_numeric` |

V251-1b is the `b` split of the spec's single task (the whole task passed 20 KB).

# Phase 1 — Oracle and rewrite

### Task V251-1: Oracle test module: verbatim reference + parity, edge, missing-volume, non-finite and order cases

**Model:** opus — exact-numerics oracle for an entry-signal module (Volume Profile strategy): the reference must be byte-verbatim and the cases must cover every spec exactness rule.

**Files:**
- Create: `tests/market/test_volume_profile_vectorised.py`

**Interfaces:**
- Consumes: `swingbot.core.market.signals.compute_volume_profile(df, lookback, n_bins=20, price_min=None, price_max=None) -> dict | None` (exists, `signals.py:585`, still the iterrows version in this task).
- Produces (V251-1b appends tests to this module and reuses these names): `_reference_compute_volume_profile` (same signature), `_canon(value)`, `_outcome(fn, df, lookback, **kwargs) -> ("ok", canon) | ("raise", exc_type_name)`, `_kind(outcome) -> "ok" | exc_type_name`, `_assert_matches_oracle(df, lookback, **kwargs) -> outcome`, `_framed(highs, lows, volumes, volume_dtype=None) -> (df, lookback)`, `_edge_bars() -> (highs, lows, vols)`.

This task runs **before** the rewrite: every test in it must pass against the
current iterrows code. That is the proof the reference is verbatim and the
comparison helpers are sound. V251-1b then swaps the loop and the same tests
must still pass.

Why the cases look the way they do:

- `_canon` turns floats into `(type name, float.hex)` and leaves lists as
  lists, so `0.0` vs `-0.0`, NaN positions and `float` vs `np.float64` all
  count. `np.float64` subclasses `float`, so `isinstance` cannot tell them
  apart. `type()` can (brief § 6).
- `_outcome` makes "same exception type" comparable to "same result" (spec
  rules 3 and 6).
- `_framed` puts two padding bars before the window, so `len(df) == lookback + 2`
  exactly (the spec's "frame of exactly `lookback + 2` rows").
- `_edge_bars` gives eleven flat bars whose midpoints sit exactly on
  100, 101, ..., 110: every interior edge of a 100..110 range in 10 bins, both
  bounds, and the `n_bins - 1` clamp at `mid == price_max`.
- Random frames use fractional volumes (`uniform(0, 5e6)`) and cycle five
  range modes: derived; narrower (skips) and wider (empty buckets), each with
  bounds as Python `float` and as `np.float64` (the chart caller's type).
- The order proof searches seeds for 200 fractional volumes where `np.sum`
  (pairwise) differs from the left-to-right sum, asserts that difference,
  then asserts the bucket equals the sequential sum. On a probe, seed 0
  already separates the two.

- [ ] **Step 1: Take the reference from the file, not by retyping**

The reference must be the function as it stands now. Generate it and compare it with the copy embedded in Step 2:

```bash
sed -n 585,658p swingbot/core/market/signals.py | sed 's/^def compute_volume_profile(/def _reference_compute_volume_profile(/' > /tmp/v251_ref.py
head -1 /tmp/v251_ref.py   # must print: def _reference_compute_volume_profile(
tail -8 /tmp/v251_ref.py   # must end with the return dict's closing brace
```

If `signals.py` moved (the first line is not `def compute_volume_profile(`), locate the function with `git grep -n "def compute_volume_profile" swingbot/core/market/signals.py` and take the function from its `def` line to the closing `}` of its return dict. Paste exactly that block (signature, docstring, body) into the module where Step 2 shows the reference, renamed and otherwise untouched.

- [ ] **Step 2: Write the test module**

Create `tests/market/test_volume_profile_vectorised.py`:

```python
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
```

- [ ] **Step 3: Run it against the current (iterrows) code**

Run: `python scripts/dev/testrun.py file tests/market/test_volume_profile_vectorised.py`
Expected: PASS, about 330 tests (300 random frames plus the edge cases), nothing failed, nothing skipped. A failure here means the reference is not verbatim or a helper is wrong: fix the test module, never `signals.py`.

- [ ] **Step 4: Complexity gate (it scans `tests/` too)**

Run: `python scripts/dev/complexity_gate.py`
Expected: `VERDICT: PASS`.

- [ ] **Step 5: Commit**

```bash
git add tests/market/test_volume_profile_vectorised.py
git commit -m "test(v251): verbatim compute_volume_profile oracle and parity cases (V251-1)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V251-1b: Vectorised rewrite, red tests, complexity gate, golden, deploy-doc soak command

**Model:** opus — rewrites a hot loop in an entry-signal module under byte-identical exactness rules (NaN/inf, dtype dispatch, summation order).

**Files:**
- Modify: `swingbot/core/market/signals.py` (imports near line 19; `compute_volume_profile` at 585-658, loop body 633-644)
- Modify: `tests/market/test_volume_profile_vectorised.py` (created by V251-1)
- Modify: `docs/deploy/DEPLOY_HETZNER.md` (section `### v245 analysis cache rollout`, soak command at line 752)

**Interfaces:**
- Consumes: V251-1's test module and its helpers `_assert_matches_oracle`, `_framed`, `_edge_bars`, `_kind`.
- Produces: in `swingbot/core/market/signals.py`, `_profile_bins(window: pd.DataFrame, price_min, price_max, bin_size, n_bins: int) -> list[float]`, `_profile_bins_vectorised(...)` and `_profile_bins_rowwise(...)` (same parameters and return), `_is_plain_numeric(column: pd.Series) -> bool`, `_raise_like_int(quotients: np.ndarray) -> None`. Private; no other module imports them.

How the rewrite meets each spec rule (all verified on a probe of this exact code against V251-1's module: 368 passed with the golden, 1 skipped):

- **Rule 3, conversion.** A numpy int/uint/float column converted whole with `to_numpy(dtype=np.float64)` gives the same value `float()` gives per element (int64 to float64 is round-to-nearest in both, float32 widens exactly) and can never raise. So converting skipped bars too changes nothing. Object or nullable columns can hold `None`/`pd.NA`, which must raise `TypeError` only on an in-range bar. Those frames take `_profile_bins_rowwise`, the old loop over `Series.tolist()` values, so it still evaluates row by row and raises at the first offending row.
- **Rule 6, non-finite.** Under `np.errstate` the array code computes `NaN`/`inf` silently. A NaN midpoint fails both comparisons, so it is kept, as before. `_raise_like_int` then calls `int()` on the first non-finite kept quotient, in row order, which raises `ValueError` (NaN) or `OverflowError` (inf), the same types the old `int(...)` raised. Nothing non-finite ever reaches `astype(np.int64)`.
- **Index.** `np.clip(q, 0, n_bins - 1).astype(np.int64)` equals `min(max(int(q), 0), n_bins - 1)` for every finite `q`: truncation and clamping commute on these bounds, and clipping first also keeps the cast inside int64.
- **Rule 4, order.** `np.add.at` is unbuffered and applies repeated indices one at a time in index order, starting from `np.zeros` (`+0.0`), the same IEEE adds as `bins[idx] += v`. V251-1's order proof checks this.
- **Rule 2, types.** `bins.tolist()` gives Python floats, including the all-zero case (no `np.bincount`). The tail is untouched, so `np.float64` bounds still yield `np.float64` edges and `poc_price`.

- [ ] **Step 1: Add the red tests**

In `tests/market/test_volume_profile_vectorised.py`, change the import block to:

```python
from __future__ import annotations

import inspect

import numpy as np
import pandas as pd
import pytest

from swingbot.core.market import signals
from swingbot.core.market.signals import compute_volume_profile
```

and append at the end of the module:

```python


def test_the_loop_no_longer_uses_iterrows():
    assert "iterrows" not in inspect.getsource(signals.compute_volume_profile)
    assert "iterrows" not in inspect.getsource(signals._profile_bins_rowwise)


@pytest.mark.parametrize("value, error", [(float("nan"), ValueError), (float("inf"), OverflowError)])
def test_non_finite_quotient_raises_what_int_raises(value, error):
    with pytest.raises(error):
        signals._raise_like_int(np.array([0.5, value, 1.5]))
    signals._raise_like_int(np.array([0.0, 3.25]))   # all finite: no raise


def test_plain_numeric_dispatch():
    df, _ = _framed(*_edge_bars())
    assert signals._is_plain_numeric(df["Volume"])
    assert signals._is_plain_numeric(df["High"].astype(np.float32))
    assert not signals._is_plain_numeric(pd.Series([1, None], dtype="Int64"))
    assert not signals._is_plain_numeric(df["Volume"].astype(object))
```

- [ ] **Step 2: Run to see them fail**

Run: `python scripts/dev/testrun.py file tests/market/test_volume_profile_vectorised.py`
Expected: 4 failed (`iterrows` still in the source; `AttributeError: module ... has no attribute '_raise_like_int'` twice; `_is_plain_numeric` missing). Every V251-1 test still passes.

- [ ] **Step 3: Import numpy in `signals.py`**

`signals.py` imports only pandas today. Directly above `import pandas as pd` (line 19, right after the module docstring), add:

```python
import numpy as np
```

- [ ] **Step 4: Add the helpers above `compute_volume_profile`**

Insert this block immediately above `def compute_volume_profile(`, below the `# Strategy 11: Volume Profile HVN Support/Resistance` comment block:

```python
def _is_plain_numeric(column: pd.Series) -> bool:
    """A numpy int/uint/float column: converting it whole with
    to_numpy(float64) gives the same values float() gives per element, and
    can never raise, so converting skipped bars too changes nothing."""
    return isinstance(column.dtype, np.dtype) and column.dtype.kind in "fiu"


def _raise_like_int(quotients: np.ndarray) -> None:
    """Raise what `int(q)` raises on the first non-finite bucket quotient
    (ValueError for NaN, OverflowError for +/-inf), in window row order --
    numpy would cast it to an arbitrary index instead."""
    bad = np.flatnonzero(~np.isfinite(quotients))
    if bad.size:
        int(quotients[bad[0]])


def _profile_bins_vectorised(
    window: pd.DataFrame, price_min, price_max, bin_size, n_bins: int,
) -> list[float]:
    """Array form of the per-bar loop for plain numeric columns. Same
    midpoint, same strict range test (a NaN midpoint is kept, as before),
    same truncate-then-clamp index (clipping first is equivalent for every
    finite quotient), and np.add.at adds each bucket's volumes one at a time
    in row order starting from 0.0, exactly as `bins[idx] += v` did."""
    high = window["High"].to_numpy(dtype=np.float64)
    low = window["Low"].to_numpy(dtype=np.float64)
    with np.errstate(invalid="ignore", over="ignore"):
        mid = (high + low) / 2
        keep = ~((mid < price_min) | (mid > price_max))
        quotients = (mid[keep] - price_min) / bin_size
    _raise_like_int(quotients)
    idx = np.clip(quotients, 0, n_bins - 1).astype(np.int64)
    volume = window["Volume"].to_numpy(dtype=np.float64)[keep]
    bins = np.zeros(n_bins, dtype=np.float64)
    np.add.at(bins, idx, volume)
    return bins.tolist()


def _profile_bins_rowwise(
    window: pd.DataFrame, price_min, price_max, bin_size, n_bins: int,
) -> list[float]:
    """Object or nullable columns: the old per-bar loop over plain column
    lists, with no Series built per row. Volume is converted only for
    in-range bars, so a None/pd.NA volume raises TypeError there and is
    never touched on a skipped bar, and the first offending row raises
    first."""
    bins = [0.0] * n_bins
    rows = zip(window["High"].tolist(), window["Low"].tolist(), window["Volume"].tolist())
    for high, low, volume in rows:
        mid = (float(high) + float(low)) / 2
        # A bar's midpoint can fall outside an explicitly widened range
        # only if it's narrower than the window's own extremes; skip
        # rather than clamp so volume never gets misattributed to an
        # edge bucket it didn't actually trade in.
        if mid < price_min or mid > price_max:
            continue
        idx = min(max(int((mid - price_min) / bin_size), 0), n_bins - 1)
        bins[idx] += float(volume)
    return bins


def _profile_bins(window: pd.DataFrame, price_min, price_max, bin_size, n_bins: int) -> list[float]:
    """Summed volume per bucket, a list of Python floats, identical (by
    float.hex, in type and in raised exception) to the pre-v251 per-bar
    loop (spec v251, Exactness rules)."""
    columns = (window["High"], window["Low"], window["Volume"])
    if all(_is_plain_numeric(column) for column in columns):
        return _profile_bins_vectorised(window, price_min, price_max, bin_size, n_bins)
    return _profile_bins_rowwise(window, price_min, price_max, bin_size, n_bins)
```

- [ ] **Step 5: Replace the loop with one call**

In `compute_volume_profile`, replace exactly these lines (old 633-644):

```python
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
```

with:

```python
    bins = _profile_bins(window, price_min, price_max, bin_size, n_bins)
```

Leave the docstring, everything above `bin_size = price_range / n_bins` and everything from `total_vol = sum(bins)` down to the return dict exactly as they are (spec § What changes).

- [ ] **Step 6: Run the module to see it pass**

Run: `python scripts/dev/testrun.py file tests/market/test_volume_profile_vectorised.py`
Expected: PASS, about 334 tests, 0 failed. A parity failure is a bug in the new `signals.py` code. Never edit `_reference_compute_volume_profile` or loosen `_canon`.

- [ ] **Step 7: Complexity**

Run: `python -m radon cc -s swingbot/core/market/signals.py` and `python scripts/dev/complexity_gate.py`
Expected: `compute_volume_profile` B (8), down from C (11); `_profile_bins_rowwise` A (4) and the other helpers at 3 or lower; gate `VERDICT: PASS`.

- [ ] **Step 8: Golden and the callers' existing tests, unchanged**

```bash
python scripts/dev/testrun.py file tests/scanning/test_v245_scan_one_golden.py
python scripts/dev/testrun.py file tests/charts/test_chart_layout.py
python scripts/dev/testrun.py file tests/admin/test_api_v1_market.py
git diff --stat -- tests/scanning tests/fixtures
```

Expected: golden 34 passed, 1 skipped (the regenerate test; never set `V245_REGEN_GOLDEN`); chart layout and admin market green; the `git diff` prints nothing. A golden diff is a bug in the rewrite, never a reason to regenerate. If the admin file reports database skips or errors, run `/replicate-prod-db` first (shared `swing-db` container, CLAUDE.md) and re-run that file alone.

- [ ] **Step 9: Commit the rewrite**

```bash
git add swingbot/core/market/signals.py tests/market/test_volume_profile_vectorised.py
git commit -m "perf(v251): compute_volume_profile without iterrows, byte-identical (V251-1b)

Array path for plain numeric columns (np.add.at keeps row-order
accumulation), row-wise list loop for object/nullable columns so a
missing in-range volume still raises TypeError, and int()-identical
raises on non-finite quotients. Tail and callers unchanged.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 10: Pin the soak command in `DEPLOY_HETZNER.md` (spec § Rollout, panel finding 7)**

In `docs/deploy/DEPLOY_HETZNER.md`, section `### v245 analysis cache rollout`, replace the line

```markdown
`bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python - --since-deploy" < scripts/perf/analysis_cache_soak_report.py`.
```

with

```markdown
`bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python - --since 2026-11-25T16:15:54Z --first-full-day 2026-11-27" < scripts/perf/analysis_cache_soak_report.py`.
Pinned to the shadow switch, not `--since-deploy`: later deploys (v251's
volume-profile rewrite among them) land inside the soak and must not restart
it. The soak is no parity evidence for v251, because the shadow runs the new
function on both sides; v251's parity rests on its oracle test and the v245
golden.
```

If V245-16/17 already rewrote this section, apply the same change to whichever line now carries the soak verdict command. Both flags exist: `analysis_cache_soak_report.py` `--since` (line 105) and `--first-full-day` (line 107).

Then run the tests that read this document:

```bash
python scripts/dev/testrun.py file tests/scripts/test_backup_db.py
python scripts/dev/testrun.py file tests/scripts/test_rollback_to_shape.py
python scripts/dev/testrun.py file tests/test_config_v239_keys.py
```

Expected: all green.

- [ ] **Step 11: Commit the doc**

```bash
git add docs/deploy/DEPLOY_HETZNER.md
git commit -m "docs(v251): pin the v245 soak verdict command to the shadow switch

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

## After the tasks: controller steps (not implementer steps)

These run once V251-1b is merged to `main`. They are listed here so the plan
is complete; no task implementer performs them.

1. **Push and watch CI** until green (`working-conventions.md` § Pipeline watch). The full suite runs there, not locally.
2. **Deploy** routinely (`/deploy`, `mirror-prod` rules). Note the deploy stamp (UTC) and the deployed commit. If v239 or anything else ships in the same deploy, record that the timing below is confounded.
3. **Leave `ANALYSIS_CACHE=shadow` as it is.** The v245 soak keeps running across the deploy and stays valid; read its verdict only with the pinned command from V251-1b Step 10.
4. **Like-for-like timing**, read-only, after at least a full session of scans:
   `bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python - --since <deploy stamp>" < scripts/perf/analysis_phase_report.py`
   Compare its `p50` with the 2.516 s baseline (spec § Why: bot 2.19.10, shadow, 74 scans, p90 3.333 s). Record `scans`, `p50`, `p90`, `cache_hit_rate`, `rss_mb_max`, the deployed commit, the bot version and any confound in the v245 results trail (`docs/superpowers/results/2026-11-23-v245-analysis-profile.md`, next to the hot-spot note). There is no pass/fail threshold here: the 0.7 s target stays v245's, judged there.
5. **`/close-out`**: applies `Bump: bot patch`, regenerates `swingbot/admin/version_history.json`, and moves this plan to `implemented/`.
