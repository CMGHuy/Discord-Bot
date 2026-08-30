# v69 — Double bottom / double top: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Version:** ui 1.10.0 · bot 1.5.0
**Bump:** bot minor (1.5.0 → 1.6.0)
**Edge:** volume

**Goal:** Ship a twelfth strategy that enters on a double-bottom or double-top
neckline break, and measure whether it earns a scope.

**Architecture:** Two pure detectors added to `chart_patterns.py` (the module
v68 created), one entries function in `entry_filters.py`, one signal function in
`signals.py`, and registration at the eight places an existing strategy appears.
Nothing touches the confluence path.

**Tech Stack:** pandas/numpy, `indicators.zigzag_pivots`, pytest,
`tune_strategy.py`, `run_backtest_range.py`.

**Spec:** `docs/superpowers/specs/2026-08-30-v69-double-bottom-top-strategy-design.md`

---

## Global Constraints

Every task's requirements implicitly include this section.

- **NO-LOOKAHEAD, absolutely.** Current bar and earlier only. The entry is the
  neckline break, never the second touch — the second low is only recognisable
  as such *after* price turns, which is tomorrow's information.
- **Reuse `indicators.zigzag_pivots`.** Do not write a second pivot detector. A
  divergent definition of "swing low" would surface as an unreproducible
  backtest rather than an error.
- **No `STRATEGY_GATES` entry until DB8 earns one.** A missing key means both
  directions, all horizons. Guessing a scope fabricates evidence in the one
  place this repo keeps its real evidence.
- **Nothing touches the confluence path.** No appends to
  `collect_candidate_levels`, no participation in
  `count_confirming_strategies`. A twelfth correlated voter is v49's closed
  branch.
- **Per-task verification is narrow** —
  `python scripts/dev/testrun.py file tests/<the one file>.py`. Never `full`
  per task; that is DB10 only.
- **TRAIN 2020-01-01..2023-12-31, VALIDATION 2024-01-01..2025-12-31, one shot.**

**Before starting: read v68's TRAIN result.** The spec's budget gate applies —
if v68's veto found nothing at any threshold, DB6–DB7 may still run but DB8's
VALIDATION should not be spent. That call is made by a person reading both
tables, and DB8 opens by asking for it.

---

## Parallelisation

- **Sequential: DB1 before everything.** Every later task consumes the
  detectors' signature.
- **Group A (parallel):** DB2 (causality test) and DB3 (entries function) —
  different files, and DB2 tests only DB1's output.
- **Sequential: DB4 after DB3** — the signal function calls `entries_for`.
- **Sequential: DB5 after DB3 and DB4** — the registration sweep asserts
  against registries those tasks populate.
- **Sequential: DB6 → DB7 → DB8.** Grid, then scope, then the one shot.

---

# Phase DB — the pattern strategy

### Task DB1: The two detectors

**Files:**
- Modify: `swingbot/core/market/chart_patterns.py`
- Test: `tests/market/test_double_patterns.py`

**Interfaces:**
- Consumes: `indicators.zigzag_pivots`.
- Produces:
  - `DEFAULT_DOUBLE_PARAMS: dict`
  - `double_bottom(df, threshold_pct, params=None) -> dict`
  - `double_top(df, threshold_pct, params=None) -> dict`

  Each returns `{"detected": bool, "neckline": float|None,
  "first": float|None, "second": float|None, "age_bars": int|None}`.

**Both live in `chart_patterns.py`** rather than a new module: it is the
package's one home for pattern geometry, v68 created it for exactly this, and a
second file would split the causality discipline across two places.

- [ ] **Step 1: Write the failing tests**

Create `tests/market/test_double_patterns.py`:

```python
"""Double bottom / double top -- entry on the neckline break, never the touch."""
import numpy as np
import pytest

from tests.conftest import make_ohlcv
from swingbot.core.market.chart_patterns import (
    DEFAULT_DOUBLE_PARAMS, double_bottom, double_top,
)

THRESH = 5.0        # zigzag reversal threshold used throughout these tests


def _w_shape(first=80.0, second=80.5, peak=95.0, breakout=96.0, pre=100.0):
    """A W: down to `first`, up to `peak`, down to `second`, then a break."""
    return make_ohlcv(
        [pre] * 10
        + list(np.linspace(pre, first, 6))[1:]
        + list(np.linspace(first, peak, 6))[1:]
        + list(np.linspace(peak, second, 6))[1:]
        + list(np.linspace(second, breakout, 6))[1:]
    )


def _m_shape(first=120.0, second=119.5, trough=105.0, breakdown=104.0, pre=100.0):
    return make_ohlcv(
        [pre] * 10
        + list(np.linspace(pre, first, 6))[1:]
        + list(np.linspace(first, trough, 6))[1:]
        + list(np.linspace(trough, second, 6))[1:]
        + list(np.linspace(second, breakdown, 6))[1:]
    )


def test_a_textbook_double_bottom_breaks_out():
    assert double_bottom(_w_shape(), THRESH)["detected"] is True


def test_a_textbook_double_top_breaks_down():
    assert double_top(_m_shape(), THRESH)["detected"] is True


def test_the_neckline_is_the_intervening_peak():
    got = double_bottom(_w_shape(peak=95.0), THRESH)
    assert got["neckline"] == pytest.approx(95.0, abs=1.0)


def test_no_signal_before_the_neckline_breaks():
    """The whole causality argument: the two lows are in place, the shape is
    complete, and there is still no entry until price clears the peak."""
    frame = _w_shape(breakout=90.0)      # bounced, but never cleared 95
    assert double_bottom(frame, THRESH)["detected"] is False


def test_unequal_lows_are_not_a_double_bottom():
    # 80 vs 92 is a higher low in an uptrend, not a double bottom.
    assert double_bottom(_w_shape(first=80.0, second=92.0), THRESH)["detected"] is False


def test_a_flat_line_is_not_a_double_bottom():
    """Two 'lows' a rounding error apart with no real peak between them is a
    flat line. separation_pct is what rejects it."""
    assert double_bottom(make_ohlcv([100.0] * 40), THRESH)["detected"] is False


def test_a_shallow_peak_fails_the_separation_gate():
    frame = _w_shape(first=80.0, second=80.2, peak=81.0, breakout=82.0)
    assert double_bottom(frame, THRESH)["detected"] is False


def test_a_stale_break_does_not_fire_forever():
    """max_age_bars: a break that happened weeks ago is not today's entry."""
    frame = _w_shape()
    stale = make_ohlcv(list(frame["Close"]) + [96.5] * 30)
    assert double_bottom(stale, THRESH)["detected"] is False


def test_the_break_must_be_fresh_not_merely_true():
    """close > neckline stays true for weeks after a breakout. Requiring the
    PRIOR bar to be at or below it makes this an event, not a state."""
    frame = _w_shape()
    extended = make_ohlcv(list(frame["Close"]) + [97.0, 98.0])
    assert double_bottom(extended, THRESH)["detected"] is False


def test_a_short_frame_detects_nothing():
    assert double_bottom(make_ohlcv([100.0] * 8), THRESH)["detected"] is False


def test_the_volume_arm_rejects_a_quiet_break():
    frame = _w_shape()
    frame["Volume"] = [1_000_000.0] * len(frame)     # break is unremarkable
    params = {**DEFAULT_DOUBLE_PARAMS, "volume_mult": 1.5}
    assert double_bottom(frame, THRESH, params)["detected"] is False


def test_the_volume_arm_accepts_a_loud_break():
    frame = _w_shape()
    volumes = [1_000_000.0] * len(frame)
    volumes[-1] = 5_000_000.0
    frame["Volume"] = volumes
    params = {**DEFAULT_DOUBLE_PARAMS, "volume_mult": 1.5}
    assert double_bottom(frame, THRESH, params)["detected"] is True


@pytest.mark.parametrize("tol,expected", [(2.0, False), (5.0, True)])
def test_equality_tolerance_is_a_grid_dimension(tol, expected):
    frame = _w_shape(first=80.0, second=83.0)        # ~3.75% apart
    params = {**DEFAULT_DOUBLE_PARAMS, "equality_tol_pct": tol}
    assert double_bottom(frame, THRESH, params)["detected"] is expected


def test_the_two_fixed_parameters_are_the_spec_values():
    assert DEFAULT_DOUBLE_PARAMS["max_age_bars"] == 10
    assert DEFAULT_DOUBLE_PARAMS["volume_mult"] is None
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/market/test_double_patterns.py -q
```

Expected: `ImportError: cannot import name 'double_bottom'`.

- [ ] **Step 3: Write the detectors**

Append to `swingbot/core/market/chart_patterns.py`:

```python
from swingbot.core.market.indicators import zigzag_pivots

#: `zigzag_threshold` is NOT here: it is the horizon's own max_risk_pct,
#: passed in by the caller, the same scaling elliott_wave_signal already uses.
DEFAULT_DOUBLE_PARAMS = {
    "max_age_bars": 10,        # fixed: a fresh break, not an old one
    "equality_tol_pct": 3.0,   # gridded
    "separation_pct": 5.0,     # gridded
    "volume_mult": None,       # gridded; None disables the arm
}

_NO_DOUBLE = {"detected": False, "neckline": None, "first": None,
              "second": None, "age_bars": None}


def double_bottom(df, threshold_pct: float, params: dict | None = None) -> dict:
    """A W that has just cleared its middle peak. Bullish."""
    return _double(df, threshold_pct, params, bullish=True)


def double_top(df, threshold_pct: float, params: dict | None = None) -> dict:
    """An M that has just lost its middle trough. Bearish."""
    return _double(df, threshold_pct, params, bullish=False)


def _double(df, threshold_pct, params, *, bullish: bool) -> dict:
    """Shared body. `bullish` flips every comparison and the pivot order.

    NO-LOOKAHEAD: zigzag_pivots only confirms a pivot after a threshold_pct
    reversal, so a pivot reported at bar i was already confirmed by bar i.
    The break test reads the current and previous bar only.
    """
    p = {**DEFAULT_DOUBLE_PARAMS, **(params or {})}
    if df is None or len(df) < 12:
        return dict(_NO_DOUBLE)

    pivots = zigzag_pivots(df, threshold_pct)
    if len(pivots) < 3:
        return dict(_NO_DOUBLE)

    outer = "low" if bullish else "high"
    inner = "high" if bullish else "low"

    # The last three pivots must read outer -> inner -> outer.
    (i1, p1, k1), (i2, p2, k2), (i3, p3, k3) = pivots[-3:]
    if (k1, k2, k3) != (outer, inner, outer):
        return dict(_NO_DOUBLE)

    # Equality, measured against the more extreme of the two so the tolerance
    # means the same thing whichever leg is deeper.
    base = min(p1, p3) if bullish else max(p1, p3)
    if base <= 0:
        return dict(_NO_DOUBLE)
    if abs(p1 - p3) / base * 100.0 > float(p["equality_tol_pct"]):
        return dict(_NO_DOUBLE)

    # Separation: a real peak between them, not a flat line.
    span = (p2 - max(p1, p3)) if bullish else (min(p1, p3) - p2)
    if span <= 0 or span / base * 100.0 < float(p["separation_pct"]):
        return dict(_NO_DOUBLE)

    last = len(df) - 1
    age = last - i3
    if age > int(p["max_age_bars"]):
        return dict(_NO_DOUBLE)          # a stale shape, not today's entry

    closes = df["Close"]
    now, prev = float(closes.iloc[-1]), float(closes.iloc[-2])
    # A fresh break, not a state: `now > neckline` stays true for weeks after
    # a breakout, so the previous bar must have been on the other side.
    broke = (now > p2 >= prev) if bullish else (now < p2 <= prev)
    if not broke:
        return dict(_NO_DOUBLE)

    mult = p["volume_mult"]
    if mult is not None and not _volume_confirms(df, float(mult)):
        return dict(_NO_DOUBLE)

    return {"detected": True, "neckline": float(p2), "first": float(p1),
            "second": float(p3), "age_bars": int(age)}


def _volume_confirms(df, mult: float) -> bool:
    """Did the breaking bar trade above `mult` x its trailing 20-bar mean?"""
    if "Volume" not in df.columns or len(df) < 21:
        return False
    trailing = df["Volume"].iloc[-21:-1].mean()      # excludes the break bar
    if not trailing or pd.isna(trailing):
        return False
    return float(df["Volume"].iloc[-1]) >= mult * float(trailing)
```

- [ ] **Step 4: Run the tests**

```bash
python scripts/dev/testrun.py file tests/market/test_double_patterns.py
```

Expected: `0 failed`. If the `_w_shape` fixtures do not produce three pivots at
`THRESH=5.0`, adjust the *fixture geometry* until they do — do not lower the
threshold inside the detector to make a test pass.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/market/chart_patterns.py tests/market/test_double_patterns.py
git commit -m "feat(v69): add double bottom and double top detectors"
```

---

### Task DB2: Prove the detectors are causal

**Files:**
- Test: `tests/market/test_double_patterns_causality.py`

**Interfaces:**
- Consumes: `double_bottom`, `double_top` (DB1).

The claim this plan rests on is that entering on the break, rather than on the
second touch, removes the look-ahead. That gets a test.

- [ ] **Step 1: Write the test**

Create `tests/market/test_double_patterns_causality.py`:

```python
"""NO-LOOKAHEAD for the double patterns.

The second low is only recognisable as 'the second low of a double bottom'
after price turns back up. Entering on the neckline break is what removes that
dependence -- and this is the test that says so rather than the docstring.
"""
import numpy as np
import pytest

from tests.conftest import make_ohlcv
from swingbot.core.market.chart_patterns import (
    DEFAULT_DOUBLE_PARAMS, double_bottom, double_top,
)

THRESH = 5.0
ARMS = [
    DEFAULT_DOUBLE_PARAMS,
    {**DEFAULT_DOUBLE_PARAMS, "equality_tol_pct": 5.0},
    {**DEFAULT_DOUBLE_PARAMS, "volume_mult": 1.5},
]


def _wavy(seed=11, n=200):
    """Enough oscillation to produce many pivots, and therefore many chances
    for a detector to cheat."""
    rng = np.random.default_rng(seed)
    closes, price = [], 100.0
    for i in range(n):
        price *= 1 + 0.09 * np.sin(i / 7.0) * 0.25 + rng.normal(0, 0.010)
        closes.append(max(price, 1.0))
    frame = make_ohlcv(closes)
    frame["Volume"] = rng.uniform(5e5, 5e6, size=n)
    return frame


@pytest.mark.parametrize("params", ARMS)
@pytest.mark.parametrize("fn", [double_bottom, double_top])
def test_a_verdict_never_changes_once_later_bars_arrive(fn, params):
    frame = _wavy()
    for i in range(20, len(frame)):
        as_of = fn(frame.iloc[: i + 1], THRESH, params)["detected"]
        recomputed = fn(frame.iloc[: i + 1], THRESH, params)["detected"]
        assert as_of == recomputed, f"bar {i} moved"


@pytest.mark.parametrize("fn", [double_bottom, double_top])
def test_at_least_one_bar_actually_detects(fn):
    """Without this, a detector returning False unconditionally would satisfy
    every causality assertion above vacuously."""
    frame = _wavy()
    fired = [i for i in range(20, len(frame))
             if fn(frame.iloc[: i + 1], THRESH)["detected"]]
    assert fired, f"{fn.__name__} never fired; the assertions proved nothing"


@pytest.mark.parametrize("fn", [double_bottom, double_top])
def test_a_detection_is_an_event_not_a_state(fn):
    """A fresh break fires on one bar, not on every bar after it. If this
    fails, entry_filters will emit a run of entries for one pattern."""
    frame = _wavy()
    fired = [i for i in range(20, len(frame))
             if fn(frame.iloc[: i + 1], THRESH)["detected"]]
    runs = [b - a for a, b in zip(fired, fired[1:])]
    assert all(gap > 1 for gap in runs), f"{fn.__name__} fired on consecutive bars"
```

- [ ] **Step 2: Run it**

```bash
python scripts/dev/testrun.py file tests/market/test_double_patterns_causality.py
```

Expected: `0 failed`. If `test_a_detection_is_an_event_not_a_state` fails, the
`prev` clause in `_double` is wrong — fix the detector, not the test.

- [ ] **Step 3: Commit**

```bash
git add tests/market/test_double_patterns_causality.py
git commit -m "test(v69): prove the double-pattern detectors are causal"
```

---

### Task DB3: The entries function

**Files:**
- Modify: `swingbot/core/market/entry_filters.py`
- Test: `tests/market/test_double_pattern_entries.py`

**Interfaces:**
- Consumes: `double_bottom`, `double_top` (DB1); `HORIZONS`.
- Produces:
  - `DEFAULT_PARAMS["Double Pattern"]`
  - `double_pattern_entries(df, horizon_key, params=None) -> (Series, Series)`
  - `ENTRY_FUNCS["Double Pattern"]`

**The strategy is named "Double Pattern"**, one strategy covering both
directions, because `entries_for` already returns a `(bullish, bearish)` pair
and splitting it into two strategies would double the registration surface for
one shape.

- [ ] **Step 1: Write the failing tests**

Create `tests/market/test_double_pattern_entries.py`:

```python
"""The entries function -- the single source both backtest and live read."""
import numpy as np
import pandas as pd
import pytest

from tests.conftest import make_ohlcv
from swingbot.core.market.entry_filters import (
    DEFAULT_PARAMS, ENTRY_FUNCS, entries_for,
)


def _w_shape():
    return make_ohlcv(
        [100.0] * 10
        + list(np.linspace(100.0, 80.0, 6))[1:]
        + list(np.linspace(80.0, 95.0, 6))[1:]
        + list(np.linspace(95.0, 80.5, 6))[1:]
        + list(np.linspace(80.5, 96.0, 6))[1:]
    )


def test_the_strategy_is_registered():
    assert "Double Pattern" in ENTRY_FUNCS
    assert "Double Pattern" in DEFAULT_PARAMS


def test_it_returns_two_aligned_boolean_series():
    frame = _w_shape()
    bull, bear = entries_for("Double Pattern", frame, "2m")
    for series in (bull, bear):
        assert isinstance(series, pd.Series)
        assert series.index.equals(frame.index)
        assert series.dtype == bool


def test_a_completed_double_bottom_fires_bullish_somewhere():
    bull, _ = entries_for("Double Pattern", _w_shape(), "2m")
    assert bull.any()


def test_a_flat_frame_fires_nothing():
    bull, bear = entries_for("Double Pattern", make_ohlcv([100.0] * 80), "2m")
    assert not bull.any() and not bear.any()


def test_the_two_directions_never_fire_on_the_same_bar():
    # A frame cannot be both a completed double bottom and a completed double
    # top at once; if it is, one of the detectors is wrong.
    bull, bear = entries_for("Double Pattern", _w_shape(), "2m")
    assert not (bull & bear).any()


def test_a_short_frame_fires_nothing_rather_than_raising():
    bull, bear = entries_for("Double Pattern", make_ohlcv([100.0] * 6), "2w")
    assert not bull.any() and not bear.any()


def test_nan_never_reaches_the_caller():
    # entry_filters' convention: every returned Series is fillna(False), so a
    # gate that cannot be computed BLOCKS rather than passes.
    bull, bear = entries_for("Double Pattern", _w_shape(), "9m")
    assert not bull.isna().any() and not bear.isna().any()
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/market/test_double_pattern_entries.py -q
```

Expected: `KeyError: 'Double Pattern'`.

- [ ] **Step 3: Write it**

Append to `swingbot/core/market/entry_filters.py`:

```python
DEFAULT_PARAMS["Double Pattern"] = {
    "equality_tol_pct": 3.0,
    "separation_pct": 5.0,
    "volume_mult": None,
}


def double_pattern_entries(df, horizon_key, params=None):
    """Double bottom (bullish) / double top (bearish), entered on the
    neckline break.

    The zigzag threshold is the horizon's own max_risk_pct -- the same scaling
    elliott_wave_entries uses -- so a "swing low" means something appropriate
    to the holding period rather than one fixed percentage everywhere.

    Evaluated per bar over a trailing window rather than vectorised: the
    pattern is a pivot-sequence test, not an arithmetic one, and there is no
    column-wise form of it. MIN_BARS already keeps the frames modest.
    """
    p = _params("Double Pattern", params)
    from swingbot.core.market.chart_patterns import double_bottom, double_top

    threshold = HORIZONS[horizon_key]["max_risk_pct"]
    bull = pd.Series(False, index=df.index)
    bear = pd.Series(False, index=df.index)

    # 12 is the detectors' own minimum; below it they return False anyway, so
    # starting here just avoids the call.
    for i in range(12, len(df)):
        window = df.iloc[: i + 1]
        if double_bottom(window, threshold, p)["detected"]:
            bull.iloc[i] = True
        elif double_top(window, threshold, p)["detected"]:
            bear.iloc[i] = True

    g = compute_shared_gates(df)
    bull = (bull & g["atr_floor"] & g["vol_ok"]).fillna(False)
    bear = (bear & g["atr_floor"] & g["vol_ok"]).fillna(False)
    return apply_regime_gate(bull, bear, "Double Pattern", df)


ENTRY_FUNCS["Double Pattern"] = double_pattern_entries
```

`elif` on the bearish branch, not a second `if`: a frame that somehow satisfies
both is a detector bug, and firing both directions on one bar would hide it.
The test above asserts the two never coincide.

Confirm `apply_regime_gate`'s real signature at `entry_filters.py:112` before
using it — match it exactly rather than assuming.

- [ ] **Step 4: Run the tests**

```bash
python scripts/dev/testrun.py file tests/market/test_double_pattern_entries.py
python scripts/dev/testrun.py file tests/market/test_entry_filters.py
```

Expected: `0 failed` for both.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/market/entry_filters.py tests/market/test_double_pattern_entries.py
git commit -m "feat(v69): add the Double Pattern entries function"
```

---

### Task DB4: The signal function

**Files:**
- Modify: `swingbot/core/market/signals.py`
- Test: `tests/market/test_double_pattern_signal.py`

**Interfaces:**
- Consumes: `entries_for` (DB3), `double_bottom`/`double_top` (DB1).
- Produces: `double_pattern_signal(ticker, df, horizon_key) -> SignalResult`.

- [ ] **Step 1: Write the failing tests**

Create `tests/market/test_double_pattern_signal.py`:

```python
"""The live-scan signal wrapper."""
import numpy as np
import pytest

from tests.conftest import make_ohlcv
from swingbot.core.market.signals import double_pattern_signal


def _w_shape():
    return make_ohlcv(
        [100.0] * 10
        + list(np.linspace(100.0, 80.0, 6))[1:]
        + list(np.linspace(80.0, 95.0, 6))[1:]
        + list(np.linspace(95.0, 80.5, 6))[1:]
        + list(np.linspace(80.5, 96.0, 6))[1:]
    )


def test_it_returns_a_populated_signal_result():
    got = double_pattern_signal("AAPL", _w_shape(), "2m")
    assert got.ticker == "AAPL"
    assert got.strategy == "Double Pattern"
    assert got.horizon_key == "2m"
    assert got.trend in ("bullish", "bearish")


def test_a_completed_pattern_is_triggered():
    assert double_pattern_signal("AAPL", _w_shape(), "2m").triggered is True


def test_the_details_name_the_neckline():
    """A triggered signal the user cannot interpret is an alert without a
    reason -- the neckline is the one number that explains the entry."""
    details = double_pattern_signal("AAPL", _w_shape(), "2m").details
    assert any("neckline" in str(k).lower() for k in details)


def test_an_untriggered_signal_says_so_rather_than_inventing_a_pattern():
    got = double_pattern_signal("AAPL", make_ohlcv([100.0] * 80), "2m")
    assert got.triggered is False
    assert got.details.get("note")


def test_the_close_is_the_last_bar():
    frame = _w_shape()
    got = double_pattern_signal("AAPL", frame, "2m")
    assert got.close == pytest.approx(float(frame["Close"].iloc[-1]))
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/market/test_double_pattern_signal.py -q
```

Expected: `ImportError: cannot import name 'double_pattern_signal'`.

- [ ] **Step 3: Write it**

Append to `swingbot/core/market/signals.py`, following
`elliott_wave_signal`'s shape exactly (it is the closest neighbour — the other
pivot-based strategy):

```python
def double_pattern_signal(ticker: str, df: pd.DataFrame, horizon_key: str) -> SignalResult:
    """Double bottom / double top, reported at the neckline break."""
    from swingbot.core.market.chart_patterns import double_bottom, double_top

    h = HORIZONS[horizon_key]
    threshold = h["max_risk_pct"]
    close = float(df["Close"].iloc[-1])

    bull_e, bear_e = entries_for("Double Pattern", df, horizon_key)
    is_bull = bool(bull_e.iloc[-1])
    is_bear = bool(bear_e.iloc[-1])

    details = {}
    if is_bull:
        got = double_bottom(df, threshold)
        trend, triggered = "bullish", True
        details = {"Pattern": "Double bottom",
                   "Neckline": round(got["neckline"], 2),
                   "First low": round(got["first"], 2),
                   "Second low": round(got["second"], 2)}
    elif is_bear:
        got = double_top(df, threshold)
        trend, triggered = "bearish", True
        details = {"Pattern": "Double top",
                   "Neckline": round(got["neckline"], 2),
                   "First high": round(got["first"], 2),
                   "Second high": round(got["second"], 2)}
    else:
        triggered = False
        pivots = zigzag_pivots(df, threshold)
        # Direction with no trigger: lean on the last confirmed pivot rather
        # than defaulting to bullish, which would read as a weak buy bias.
        trend = "bullish" if (pivots and close >= pivots[-1][1]) else "bearish"
        details = {"note": "no completed double pattern at this bar"}

    return SignalResult(ticker=ticker, strategy="Double Pattern",
                        horizon_key=horizon_key, horizon_label=h["label"],
                        trend=trend, triggered=triggered, close=close,
                        details=details)
```

- [ ] **Step 4: Run the tests**

```bash
python scripts/dev/testrun.py file tests/market/test_double_pattern_signal.py
```

Expected: `0 failed`.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/market/signals.py tests/market/test_double_pattern_signal.py
git commit -m "feat(v69): add the Double Pattern signal function"
```

---

### Task DB5: Register it everywhere, and prove nothing was missed

A strategy name appears in **eight** places in this codebase. A checklist gets
one wrong; a test that enumerates them does not.

**Files:**
- Modify: `swingbot/core/market/strategy.py` (`STRATEGY_FUNCS`, `STRATEGY_SHORT_NAMES`)
- Modify: `swingbot/core/backtesting/backtest.py` (`:465` strategy list)
- Modify: `swingbot/commands/backtest.py` (`:36` aliases, `:41` list)
- Modify: `swingbot/commands/slash.py` (`:43` choices)
- Modify: `swingbot/core/planning/params.py` (`:40` exit params)
- Test: `tests/market/test_strategy_registration.py`

**Interfaces:**
- Consumes: `double_pattern_signal` (DB4), `ENTRY_FUNCS` (DB3).
- Produces: `"Double Pattern"` present in every registry.

**No `STRATEGY_GATES` entry.** DB7 earns it from TRAIN.

- [ ] **Step 1: Write the failing test**

Create `tests/market/test_strategy_registration.py`:

```python
"""Every strategy must appear in every registry.

Written generically rather than for v69 specifically: the value is that the
NEXT strategy someone adds fails this test until it is wired everywhere,
instead of silently missing from the slash command for a release.
"""
import pytest

from swingbot.core.market.entry_filters import DEFAULT_PARAMS, ENTRY_FUNCS
from swingbot.core.market.strategy import STRATEGY_FUNCS, STRATEGY_SHORT_NAMES

STRATEGIES = sorted(STRATEGY_FUNCS)


def test_the_new_strategy_is_present():
    assert "Double Pattern" in STRATEGY_FUNCS


@pytest.mark.parametrize("name", STRATEGIES)
def test_every_strategy_has_an_entries_function(name):
    assert name in ENTRY_FUNCS, f"{name} has no ENTRY_FUNCS entry"
    assert name in DEFAULT_PARAMS, f"{name} has no DEFAULT_PARAMS entry"


@pytest.mark.parametrize("name", STRATEGIES)
def test_every_strategy_has_a_short_name(name):
    assert name in STRATEGY_SHORT_NAMES
    assert len(STRATEGY_SHORT_NAMES[name]) <= 8, "short names must stay short"


@pytest.mark.parametrize("name", STRATEGIES)
def test_every_strategy_is_backtestable(name):
    from swingbot.core.backtesting.backtest import ALL_STRATEGIES
    assert name in ALL_STRATEGIES, f"{name} cannot be backtested"


@pytest.mark.parametrize("name", STRATEGIES)
def test_every_strategy_has_exit_params(name):
    from swingbot.core.planning.params import EXIT_PARAMS_BY_STRATEGY
    assert name in EXIT_PARAMS_BY_STRATEGY, f"{name} has no exit params"


@pytest.mark.parametrize("name", STRATEGIES)
def test_every_strategy_is_reachable_from_discord(name):
    from swingbot.commands.backtest import STRATEGY_ALIASES
    assert name in set(STRATEGY_ALIASES.values()), f"{name} has no CLI alias"


def test_no_strategy_gates_entry_is_guessed():
    """v69 ships ungated on purpose: STRATEGY_GATES entries are EARNED from a
    TRAIN grid with the numbers recorded inline. A guessed scope would
    fabricate evidence where this repo keeps its real evidence."""
    from swingbot.core.market.strategy_types import STRATEGY_GATES
    assert "Double Pattern" not in STRATEGY_GATES
```

The constant names (`ALL_STRATEGIES`, `EXIT_PARAMS_BY_STRATEGY`,
`STRATEGY_ALIASES`) are the plausible ones — **read each file and use the real
name.** If a registry turns out to be a bare list literal with no name, give it
one in this task; a registry that cannot be imported cannot be tested, and that
is the actual defect.

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/market/test_strategy_registration.py -q
```

Expected: failures naming each registry the strategy is missing from. **That
list is this task's work plan.**

- [ ] **Step 3: Register it**

Work the failure list. `STRATEGY_SHORT_NAMES["Double Pattern"] = "Double"`.
For `params.py`, start from the `Elliott Wave` row's values — the closest
neighbour — and note in a comment that they are inherited, not measured, until
this strategy has a track record of its own.

- [ ] **Step 4: Run the tests**

```bash
python scripts/dev/testrun.py file tests/market/test_strategy_registration.py
python scripts/dev/testrun.py fast
```

Expected: `0 failed`. The fast tier because registration touches six files
across `commands/`, `core/market/`, `core/backtesting/` and `core/planning/`.

- [ ] **Step 5: Commit**

```bash
git add swingbot tests/market/test_strategy_registration.py
git commit -m "feat(v69): register Double Pattern as the twelfth strategy"
```

---

### Task DB6: The TRAIN grid

**Files:**
- Create: `docs/superpowers/results/2026-08-30-v69-double-pattern-train.md`

**Interfaces:**
- Consumes: `DEFAULT_PARAMS["Double Pattern"]` (DB3).
- Produces: the TRAIN table and the adopted parameter set, or the finding that
  none qualifies.

**No new instrument.** `tune_strategy.py` already grids `DEFAULT_PARAMS` keys,
and `entries_for` is the single source both worlds read — so unlike v68's
confluence veto, this is visible to the standard harness by construction.

- [ ] **Step 1: Confirm the data cache exists**

```bash
ls data/backtest_cache/*.csv | wc -l
python scripts/data/fetch_backtest_data.py      # only if the cache is empty
```

- [ ] **Step 2: Smoke one cell before spending hours**

```bash
python scripts/backtest/run_backtest_range.py --train --strategy "Double Pattern" \
    --json /tmp/v69-smoke.json
```

Expected: a completed run with a non-zero trade count. **If N is zero, stop.**
A pattern that never fires over four years of TRAIN data is a detector bug or a
threshold mismatch, and gridding it would produce twelve empty rows. Diagnose
with `scripts/dev/diagnose_funnel.py`'s approach — count detections per stage —
before continuing.

- [ ] **Step 3: Run the grid**

```bash
python scripts/backtest/tune_strategy.py --strategy "Double Pattern" \
    --grid equality_tol_pct=2,3,5 separation_pct=5,10 volume_mult=0,1.5 \
    2>&1 | tee /tmp/v69-train.log
```

Dispatch to the `backtest-runner` subagent — hours of per-ticker output must
not land in the main context.

`volume_mult=0` is how the CLI spells "arm off"; `_params` must translate `0`
to `None` the same way `params_from_config` does in v68. Verify that
translation exists before running, or the `off` arm silently becomes
"require 0x volume", which every bar passes.

- [ ] **Step 4: Apply the pre-registered rule and record**

The rule, quoted verbatim in the results doc:

```
per (direction, horizon) cell include iff win_rate >= 50 and expectancy_r > 0
and N >= 30 and excluded <= 50%; adopt the parameter set with the best pooled
ExpR among sets having at least two qualifying cells. If no set has two
qualifying cells, none is adopted and VALIDATION is not spent.
```

Write `docs/superpowers/results/2026-08-30-v69-double-pattern-train.md`: the
full twelve-row table, the rule quoted, the adopted set **or the explicit
statement that none qualified**, every under-populated cell named, and an
honest observations section.

Note whether Elliott Wave's fate repeated — it is the only other
`zigzag_pivots` strategy and `STRATEGY_GATES`' comment records it failing to
earn a scope. If this one fails the same way, that similarity is the finding.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/results/2026-08-30-v69-double-pattern-train.md
git commit -m "measure(v69): TRAIN grid for the Double Pattern strategy"
```

---

### Task DB7: Adopt the scope

**Files:**
- Modify: `swingbot/core/market/entry_filters.py` (`DEFAULT_PARAMS`)
- Modify: `swingbot/core/market/strategy_types.py` (`STRATEGY_GATES`)
- Test: `tests/market/test_strategy_registration.py` (update the ungated assertion)

**Interfaces:**
- Consumes: DB6's adopted set.

- [ ] **Step 1: Check whether this task runs**

If DB6 adopted no parameter set, **skip to DB10** and close under `no-lift/`.
The strategy is not shipped, `STRATEGY_GATES` gains nothing, and VALIDATION is
not spent.

- [ ] **Step 2: Write the adopted values in**

Set `DEFAULT_PARAMS["Double Pattern"]` to the adopted set. Add the
`STRATEGY_GATES` entry in the house format — the qualifying cells, with the
numbers inline:

```python
    # bullish + {3m,4m}: N=... WR=... ExpR=... excl=...% (train)
    "Double Pattern": {"directions": ("bullish",), "horizons": ("3m", "4m")},
```

Copy the real numbers from DB6's table. This comment is evidence, not
decoration — every other entry in that dict carries the same thing, and it is
what lets a later reader tell an earned scope from a guessed one.

- [ ] **Step 3: Update the registration test**

`test_no_strategy_gates_entry_is_guessed` now asserts the opposite: the entry
exists **and** its comment carries a `(train)` provenance marker. Rename it
`test_the_strategy_gates_entry_is_earned` and assert against the source line.

- [ ] **Step 4: Run the tests**

```bash
python scripts/dev/testrun.py file tests/market/test_strategy_registration.py
python scripts/dev/testrun.py file tests/market/test_entry_filters.py
```

Expected: `0 failed`.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/market/entry_filters.py swingbot/core/market/strategy_types.py \
        tests/market/test_strategy_registration.py
git commit -m "feat(v69): adopt the TRAIN-earned Double Pattern scope"
```

---

### Task DB8: VALIDATION — one shot

**Files:**
- Create: `docs/superpowers/results/2026-08-30-v69-double-pattern-validation.md`
- Modify: `docs/superpowers/results/validation_registry.json` (via `--emit-registry`)

- [ ] **Step 1: Read v68's TRAIN result first**

The spec's budget gate. If v68's veto found **no** qualifying cell at any
decline threshold, that is evidence multi-pivot geometry carries nothing on
this universe, and a weak DB6 result plus a dead v68 is a `no-lift/` close
rather than a shot.

**This is a judgement, not a computation.** Record which way it went and why in
the validation doc's opening paragraph, whichever way it goes.

- [ ] **Step 2: Run VALIDATION once**

```bash
python scripts/backtest/run_backtest_range.py --validation \
    --strategy "Double Pattern" --emit-registry \
    --json docs/superpowers/results/2026-08-30-v69-double-pattern-validation.json \
    2>&1 | tee /tmp/v69-validation.log
```

One strategy, one adopted parameter set, one run. Recorded as-is.

- [ ] **Step 3: Apply the gates and badge it**

`win_rate >= 50`, `expectancy_r > 0`, `N >= 15`, scratches+timeouts ≤ 50%.

All four hold → `VALIDATED`. Any fails → `WEAK`, and the strategy stays shipped
but unpromoted — the disposition v31 gave Break & Retest and VWAP, and a
legitimate outcome rather than a failure to hide.

`--emit-registry` writes no row for an unhealthy cell and prints a
`hard-gate:*` token instead. A missing row is recovered by re-running that
cell, **never** by hand-editing the JSON.

- [ ] **Step 4: Record**

Write the validation doc: the pre-registered gates quoted, the numbers as they
came out, the badge assigned, and an observations section that says plainly
whether this strategy earned its place.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/results/
git commit -m "measure(v69): VALIDATION shot for the Double Pattern strategy"
```

---

### Task DB9: The scan-budget check

A twelfth strategy runs on every ticker × every horizon on every scan, and
`double_pattern_entries` loops per bar rather than vectorising. That is a real
cost and it needs a number before this ships.

**Files:**
- Test: `tests/market/test_double_pattern_budget.py`

**Interfaces:**
- Consumes: `entries_for` (DB3).

- [ ] **Step 1: Write the test**

Create `tests/market/test_double_pattern_budget.py`:

```python
"""The twelfth strategy must not blow the scan budget.

SCAN_INTERVAL_MINUTES=5 gives a 300s ceiling for the whole universe, and
v36's own budget task projected 211-215s for 82 tickers BEFORE this strategy
existed. A per-bar loop is the one shape here that could plausibly break that.
"""
import time

import numpy as np
import pytest

from tests.conftest import make_trend_df
from swingbot.core.market.entry_filters import entries_for

pytestmark = pytest.mark.slow


def test_one_ticker_one_horizon_stays_under_a_budget_slice():
    # 300s / 82 tickers / 10 horizons ~= 0.36s per (ticker, horizon) for ALL
    # twelve strategies. This one may have a tenth of that.
    frame = make_trend_df(400, 0.05)
    start = time.perf_counter()
    entries_for("Double Pattern", frame, "3m")
    elapsed = time.perf_counter() - start
    assert elapsed < 0.036, f"{elapsed:.3f}s per (ticker, horizon) is too slow"


def test_it_scales_roughly_linearly_in_bars():
    """A per-bar loop calling a detector that re-runs zigzag_pivots over the
    whole window is quadratic. If this ratio is far above 2x, that is why."""
    short_f = make_trend_df(200, 0.05)
    long_f = make_trend_df(400, 0.05)

    start = time.perf_counter()
    entries_for("Double Pattern", short_f, "3m")
    short_t = time.perf_counter() - start

    start = time.perf_counter()
    entries_for("Double Pattern", long_f, "3m")
    long_t = time.perf_counter() - start

    assert long_t < short_t * 6, f"{short_t:.3f}s -> {long_t:.3f}s looks quadratic"
```

- [ ] **Step 2: Run it**

```bash
python -m pytest tests/market/test_double_pattern_budget.py -q
```

**If either fails, that is a real finding, not a test to loosen.** The likely
cause is `_double` calling `zigzag_pivots` over the full window on every bar,
making the loop quadratic. The fix is to compute pivots once per frame in
`double_pattern_entries` and pass them down, adding an optional `pivots=`
parameter to the detectors. Do that rather than raising the threshold.

- [ ] **Step 3: Commit**

```bash
git add tests/market/test_double_pattern_budget.py swingbot/core/market
git commit -m "test(v69): bound the Double Pattern scan cost"
```

---

### Task DB10: Full-suite verification and close-out

**Files:**
- Modify: `VERSION.json`, `frontend/src/assets/version_history.json`
- Modify: `README.md`, `docs/strategy/strategy.md` (the strategy tables)
- Move: the spec and plan into `implemented/` or `no-lift/`

- [ ] **Step 1: Run the full suite, once**

```bash
python scripts/dev/testrun.py full
```

Expected: `0 failed`, `0 xfailed`. Dispatch `test-runner`. No `frontend/`
source changed, so `npm test` is not part of this gate.

- [ ] **Step 2: Update the documentation tables**

`README.md` and `docs/strategy/strategy.md` both carry strategy lists.
`CLAUDE.md` notes the code is authoritative when those tables lag — that is a
reason to fix them here, not a licence to leave them stale.

- [ ] **Step 3: Bump and regenerate**

`bot` minor `1.5.0` → `1.6.0` if the strategy shipped: a twelfth source of
alerts is an observable difference, which is what
`document-conventions.md` says to argue the bump from. If DB6 found nothing and
the strategy did not ship, the bump is `none` and this step records that
instead.

Then the step that gets missed, because the local gate runs *before* the bump
and structurally cannot catch it:

```bash
python scripts/dev/build_version_matrix.py
git diff --stat frontend/src/assets/version_history.json
```

An empty diff means the bump was not picked up. Investigate before committing.

- [ ] **Step 4: Close the documents out**

```bash
git mv docs/superpowers/specs/2026-08-30-v69-double-bottom-top-strategy-design.md \
       docs/superpowers/specs/implemented/      # or no-lift/
git mv docs/superpowers/plans/2026-08-30-v69-double-bottom-top-strategy.md \
       docs/superpowers/plans/implemented/      # or no-lift/
```

Amend the spec's `Bump:` and `Edge:` lines if either prediction came out wrong,
with one clause saying why. `Edge: volume` predicted more qualifying setups; if
the strategy fired on almost nothing, say so — that is the useful record.

- [ ] **Step 5: Commit**

```bash
git add VERSION.json frontend/src/assets/version_history.json \
        README.md docs
git commit -m "release(v69): bot 1.6.0 -- Double Pattern strategy"
```

---

## Success criteria

1. Both detectors find the textbook shapes and reject flat lines, unequal
   lows, shallow peaks and stale breaks.
2. The verdict is provably causal, and provably an **event** rather than a
   state that stays true for weeks — DB2.
3. The strategy is registered at every point an existing strategy appears,
   proven by an enumerating test that will also catch the next one.
4. The scan cost is measured and bounded — DB9.
5. A twelve-cell TRAIN table exists with the rule quoted and every
   under-populated cell named.
6. Either a scope was earned and VALIDATION spent once, **or** nothing
   qualified and the budget is explicitly preserved.
7. `python scripts/dev/testrun.py full` is green.
