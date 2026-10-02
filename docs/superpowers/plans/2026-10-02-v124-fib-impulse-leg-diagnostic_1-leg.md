# Fibonacci impulse-leg instrument and anchor diagnostic — implementation plan, part 1 (Phase 1)

> Part of v124. Header, global constraints, file map, the arm 4 identification route, review focus and `## Parallelisation` live in `2026-10-02-v124-fib-impulse-leg-diagnostic_0-index.md`; read it and the spec (`docs/superpowers/specs/2026-10-02-v124-fib-impulse-leg-diagnostic-design.md`) with any task here.

# Phase 1 — The leg

### Task V124-1: Leg origin, end and the no-leg cases

**Files:** Create `swingbot/core/market/fib_leg.py`, `tests/market/fib_leg_fixtures.py`, `tests/market/test_fib_leg.py`.

**Interfaces:**
- Consumes (v121, merged): `structure.confirmed_pivots(df, k) -> DataFrame` with `last_sh_pos`, `last_sl_pos` (positional floats, NaN when absent); `structure.pivot_confirmations(df, k) -> (sh, sl)`, boolean arrays indexed by confirmation bar `j` (True when bar `j - k` is a pivot).
- Produces: `ORIGIN_DIVISOR = 6`, `MIN_ORIGIN_K = 3`, `MIN_END_AGE = 3`, `RATIOS`, `LEG_COLUMNS` (13-tuple below), `PRICE_COLUMNS`, `origin_strength(horizon_key: str, divisor: int = ORIGIN_DIVISOR) -> int`, `impulse_leg(df, direction, origin_k) -> pd.DataFrame` (float columns `LEG_COLUMNS`, index `df.index`), `leg_at(df, direction, origin_k) -> dict` (`LEG_COLUMNS` → float, NaN for no leg; equals `impulse_leg(df, ...).iloc[-1]`). Private `_features(o, t, origin, end)`, which V124-2 replaces. Fixtures: `MIRROR`, `path_frame`, `CLEAN`, `TIE`, `BROKEN`, `RESTART`, `walk_frame()`.

- [ ] **Step 0: Precondition.** Run `git grep -n "def confirmed_pivots\|def pivot_confirmations\|^PIVOT_K" -- swingbot/core/market/structure.py`. Expect three hits. If there are none, stop: report `BLOCKED: v121 structure.py not merged`.

- [ ] **Step 1: Write the fixtures.** Every bar has `High = p + 0.5`, `Low = p - 0.5`, `Open = Close = p`. The mirror uses `30 - p`, so a bearish expectation for a price is `30 - bullish`. Ratios are unchanged.

```python
# tests/market/fib_leg_fixtures.py
"""Hand-built price paths for fib_leg (v124). Bar i: High = p + 0.5,
Low = p - 0.5, Open = Close = p. mirror=True uses MIRROR - p, so every
bearish price expectation is MIRROR - (bullish price) and ratios are equal.

CLEAN (bars 0..17), k = 3:
  bar 3  p=13  swing high (H 13.5), confirmed at bar 6   -- the swing before the origin
  bar 7  p=9   swing low  (L 8.5),  confirmed at bar 10  -- the origin
  bar 13 p=15  highest High in (7, t] (H 15.5)           -- the end; >= 3 bars old from t=16
"""
import numpy as np
import pandas as pd

from tests.conftest import make_ohlcv

MIRROR = 30.0
CLEAN = [10, 11, 12, 13, 12, 11, 10, 9, 10, 11, 12, 13, 14, 15, 14, 13.5, 13, 12]
TIE = CLEAN[:14] + [15, 13.5, 13]            # bars 13 and 14 share High 15.5
BROKEN = CLEAN + [8]                          # bar 18 Low 7.5 undercuts the origin (8.5)
RESTART = CLEAN + [11.5, 12.5, 13.5, 14.5, 16, 15.5, 15, 14.8]   # bar 18 higher low (L 11.0), confirmed at 21
HIGH_PRIOR = CLEAN[:3] + [17] + CLEAN[4:]     # swing before the origin at H 17.5 > end 15.5
NO_PRIOR = [13, 12, 11, 10, 9, 10, 11, 12, 13, 14, 13, 12.5, 12]  # origin bar 4, end bar 9, no earlier swing high


def path_frame(path, *, mirror=False):
    p = np.asarray(path, dtype=float)
    if mirror:
        p = MIRROR - p
    idx = pd.bdate_range("2015-01-01", periods=len(p))
    return pd.DataFrame({"Open": p, "High": p + 0.5, "Low": p - 0.5, "Close": p,
                         "Volume": np.full(len(p), 1_000_000.0)}, index=idx)


def walk_frame(n=120, seed=124):
    closes = 100 + np.cumsum(np.random.default_rng(seed).normal(0.0, 1.0, n))
    return make_ohlcv(closes, spread_pct=2.0)
```

- [ ] **Step 2: Write the failing tests.**

```python
# tests/market/test_fib_leg.py
from pathlib import Path

import numpy as np
import pytest

from swingbot.core.market import fib_leg as fl
from tests.market.fib_leg_fixtures import (BROKEN, CLEAN, MIRROR, RESTART, TIE, path_frame,
                                           walk_frame)

SIDES = [(False, "bullish"), (True, "bearish")]


def leg(path, mirror, direction, t, k=3):
    return fl.impulse_leg(path_frame(path[:t + 1], mirror=mirror), direction, k).iloc[-1]


def expect(row, expected, mirror):
    for key, value in expected.items():
        want = MIRROR - value if mirror and key in fl.PRICE_COLUMNS else value
        assert row[key] == pytest.approx(want), key


def assert_no_leg(row):
    assert row.isna().all(), row[row.notna()]


@pytest.mark.parametrize("horizon_key,divisor,expected", [
    ("1w", 6, 3), ("2w", 6, 3), ("4w", 6, 7), ("9m", 6, 63), ("9m", 4, 94), ("9m", 8, 47), ("2w", 8, 3)])
def test_origin_strength(horizon_key, divisor, expected):
    assert fl.origin_strength(horizon_key, divisor) == expected


@pytest.mark.parametrize("mirror,direction", SIDES)
def test_clean_leg_bounds(mirror, direction):
    expect(leg(CLEAN, mirror, direction, 16),
           {"origin_idx": 7, "origin_price": 8.5, "end_idx": 13, "end_price": 15.5, "leg_bars": 6}, mirror)


@pytest.mark.parametrize("mirror,direction", SIDES)
def test_end_younger_than_three_bars_is_no_leg(mirror, direction):
    assert_no_leg(leg(CLEAN, mirror, direction, 15))      # end bar 13 is 2 bars old


@pytest.mark.parametrize("mirror,direction", SIDES)
def test_equal_highs_take_the_first_bar(mirror, direction):
    row = leg(TIE, mirror, direction, 16)                  # last-occurrence would be 2 bars old -> NaN
    assert row["end_idx"] == 13


@pytest.mark.parametrize("mirror,direction", SIDES)
def test_broken_origin_is_no_leg(mirror, direction):
    assert_no_leg(leg(BROKEN, mirror, direction, 18))


@pytest.mark.parametrize("mirror,direction", SIDES)
def test_higher_major_low_restarts_the_leg(mirror, direction):
    assert leg(RESTART, mirror, direction, 20)["origin_idx"] == 7    # bar 18 not confirmed yet
    assert_no_leg(leg(RESTART, mirror, direction, 21))               # new origin, end is bar 21 itself
    expect(leg(RESTART, mirror, direction, 25),
           {"origin_idx": 18, "origin_price": 11.0, "end_idx": 22, "end_price": 16.5, "leg_bars": 4}, mirror)


@pytest.mark.parametrize("n", [0, 1, 2, 5, 9])
@pytest.mark.parametrize("mirror,direction", SIDES)
def test_short_frames_are_all_nan(n, mirror, direction):
    df = path_frame(CLEAN[:n], mirror=mirror)
    out = fl.impulse_leg(df, direction, 3)
    assert out.shape == (n, len(fl.LEG_COLUMNS))
    assert out.isna().all().all()
    assert all(np.isnan(v) for v in fl.leg_at(df, direction, 3).values())


@pytest.mark.parametrize("mirror,direction", SIDES)
def test_nan_bar_inside_the_leg_is_no_leg(mirror, direction):
    df = path_frame(CLEAN[:17], mirror=mirror)
    df.iloc[10, df.columns.get_indexer(["High", "Low"])] = np.nan
    assert_no_leg(fl.impulse_leg(df, direction, 3).iloc[-1])


def test_flat_frame_is_all_nan():
    out = fl.impulse_leg(path_frame([10.0] * 40), "bullish", 3)
    assert out.isna().all().all()


@pytest.mark.parametrize("origin_k", [3, 7])
@pytest.mark.parametrize("direction", ["bullish", "bearish"])
def test_row_t_equals_last_row_of_prefix(direction, origin_k):
    df = walk_frame()
    full = fl.impulse_leg(df, direction, origin_k)
    for t in range(len(df)):
        prefix = df.iloc[:t + 1]
        np.testing.assert_array_equal(fl.impulse_leg(prefix, direction, origin_k).iloc[-1].to_numpy(),
                                      full.iloc[t].to_numpy(), err_msg=f"t={t}")
        last = fl.leg_at(prefix, direction, origin_k)
        np.testing.assert_array_equal(np.array([last[c] for c in fl.LEG_COLUMNS], dtype=float),
                                      full.iloc[t].to_numpy(), err_msg=f"leg_at t={t}")
    if origin_k == 3:
        assert full["end_idx"].notna().any()     # the walk really produces legs


def test_no_live_module_imports_fib_leg():
    root = Path(__file__).resolve().parents[2]
    sources = [*(root / "swingbot").rglob("*.py"), root / "bot.py", root / "admin_ui.py"]
    hits = [str(path) for path in sources
            if path.name != "fib_leg.py" and "fib_leg" in path.read_text(encoding="utf-8")]
    assert hits == []
```

- [ ] **Step 3: Run** `python scripts/dev/testrun.py file tests/market/test_fib_leg.py`. Expect FAIL (`ModuleNotFoundError: swingbot.core.market.fib_leg`).

- [ ] **Step 4: Implement.**

```python
# swingbot/core/market/fib_leg.py
"""Causal Fibonacci impulse leg (v124) -- a pure instrument with no live caller.

Bullish leg at bar t: the origin is the most recent swing low of strength
``origin_k`` confirmed at t (``structure.confirmed_pivots``); the end is the
FIRST bar holding the highest High in (origin, t], and the leg exists only
once that bar is at least MIN_END_AGE bars old. No leg (all NaN) when no
origin is confirmed, the end is too young, a bar in (origin, t] is not
finite, or any Low after the origin undercuts the origin price. A later
confirmed swing low simply becomes the new origin.

Bearish mirrors every comparison. The module works in an oriented space:
bearish negates prices and swaps High/Low (hi = -Low, lo = -High), runs the
bullish logic, and negates the price columns back.

Causality: row t of impulse_leg(df) equals impulse_leg(df.iloc[:t+1]).iloc[-1].
Pivot lag lives only in structure.py; nothing here detects pivots.
"""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd

from swingbot.core.market.indicators import atr
from swingbot.core.market.strategy_types import HORIZONS
from swingbot.core.market.structure import confirmed_pivots, pivot_confirmations

ORIGIN_DIVISOR = 6   # frozen descriptive default (spec "Origin strength")
MIN_ORIGIN_K = 3
MIN_END_AGE = 3      # bars; the lag v121 uses
RATIOS = (0.382, 0.5, 0.618)
LEG_COLUMNS = ("origin_idx", "origin_price", "end_idx", "end_price", "leg_atr", "leg_bars",
               "level_382", "level_500", "level_618", "retrace_now", "retrace_deepest",
               "zone_touch", "broke_structure")
PRICE_COLUMNS = ("origin_price", "end_price", "level_382", "level_500", "level_618")
_SIDES = {"bullish": ("last_sl_pos", 1.0), "bearish": ("last_sh_pos", -1.0)}
_NO_LEG = dict.fromkeys(LEG_COLUMNS, np.nan)


def origin_strength(horizon_key: str, divisor: int = ORIGIN_DIVISOR) -> int:
    """Pivot strength of the leg origin: max(3, fib_lookback // divisor)."""
    return max(MIN_ORIGIN_K, int(HORIZONS[horizon_key]["fib_lookback"]) // divisor)


def _oriented(df: pd.DataFrame, direction: str, origin_k: int) -> SimpleNamespace:
    """Bullish-oriented arrays. ``prior`` holds positions of the opposite-side
    pivots (swing highs for a bullish leg) for the structure-break check."""
    origin_col, sign = _SIDES[direction]
    high, low = df["High"].to_numpy(float), df["Low"].to_numpy(float)
    sh, sl = pivot_confirmations(df, origin_k)
    hi, lo = (high, low) if sign > 0 else (-low, -high)
    prior_flags = sh if sign > 0 else sl
    return SimpleNamespace(
        sign=sign, hi=hi, lo=lo, close=sign * df["Close"].to_numpy(float),
        origin=confirmed_pivots(df, origin_k)[origin_col].to_numpy(float),
        prior=np.flatnonzero(prior_flags) - origin_k,
        atr=atr(df).to_numpy(float))


def _bounds(o: SimpleNamespace, t: int) -> tuple[int, int] | None:
    """(origin, end) positions of the leg at bar t, or None for no leg."""
    origin = o.origin[t]
    if not np.isfinite(origin):
        return None
    origin = int(origin)
    seg_hi, seg_lo = o.hi[origin + 1:t + 1], o.lo[origin + 1:t + 1]
    if seg_hi.size == 0 or not (np.isfinite(seg_hi).all() and np.isfinite(seg_lo).all()):
        return None
    end = origin + 1 + int(np.argmax(seg_hi))          # first occurrence on ties
    if t - end < MIN_END_AGE or seg_lo.min() < o.lo[origin]:
        return None
    return origin, end


def _features(o: SimpleNamespace, t: int, origin: int, end: int) -> dict | None:
    """Oriented leg row. V124-1 fills the bounds; V124-2 adds the rest."""
    return {**_NO_LEG, "origin_idx": float(origin), "origin_price": float(o.lo[origin]),
            "end_idx": float(end), "end_price": float(o.hi[end]), "leg_bars": float(end - origin)}


def _real(row: dict, sign: float) -> dict:
    return {**row, **{key: sign * row[key] for key in PRICE_COLUMNS}}


def _row(o: SimpleNamespace, t: int) -> dict:
    bounds = _bounds(o, t)
    row = _features(o, t, *bounds) if bounds else None
    return _real(row, o.sign) if row else dict(_NO_LEG)


def impulse_leg(df: pd.DataFrame, direction: str, origin_k: int) -> pd.DataFrame:
    """One row per bar: the leg known at that bar (all NaN when there is none)."""
    if len(df) == 0:
        return pd.DataFrame(columns=list(LEG_COLUMNS), index=df.index, dtype=float)
    o = _oriented(df, direction, origin_k)
    rows = [_row(o, t) for t in range(len(df))]
    return pd.DataFrame(rows, index=df.index, columns=list(LEG_COLUMNS), dtype=float)


def leg_at(df: pd.DataFrame, direction: str, origin_k: int) -> dict:
    """The leg at the last bar only -- equal to impulse_leg(df, ...).iloc[-1]."""
    if len(df) == 0:
        return dict(_NO_LEG)
    return _row(_oriented(df, direction, origin_k), len(df) - 1)
```

- [ ] **Step 5: Run** `python scripts/dev/testrun.py file tests/market/test_fib_leg.py`. Expect PASS. Run `python -m radon cc -s -n C swingbot/core/market/fib_leg.py tests/market/test_fib_leg.py tests/market/fib_leg_fixtures.py` and expect no output.
- [ ] **Step 6: Commit.**

```bash
git add swingbot/core/market/fib_leg.py tests/market/fib_leg_fixtures.py tests/market/test_fib_leg.py
git commit -m "feat(v124): causal impulse-leg origin and end in market/fib_leg.py"
```

### Task V124-2: Leg features — levels, retracement, zone touch, structure break

**Files:** Modify `swingbot/core/market/fib_leg.py` (replace `_features`, add `_prior_break`); modify `tests/market/test_fib_leg.py`.

**Interfaces:**
- Consumes (V124-1): `_oriented` namespace (`hi`, `lo`, `close`, `prior`, `atr`), `_bounds`, `_NO_LEG`, `RATIOS`, fixtures `CLEAN`, `HIGH_PRIOR`, `NO_PRIOR`, `RESTART`.
- Produces: every `LEG_COLUMNS` value filled. `leg_atr` = leg size / ATR14 at `t` (NaN while ATR is undefined or 0). `level_r = end − r·size` (bullish). `retrace_now` is measured from Close, `retrace_deepest` from the lowest Low in `(end, t]`. `zone_touch` is `1.0`/`0.0`. `broke_structure` is `1.0`/`0.0`, or NaN when there is no opposite-side pivot before the origin. `_features` returns `None` when size `<= 0`.

- [ ] **Step 0: Precondition** as in V124-1 Step 0.
- [ ] **Step 1: Write the failing tests.** Extend the import to `from tests.market.fib_leg_fixtures import (BROKEN, CLEAN, HIGH_PRIOR, MIRROR, NO_PRIOR, RESTART, TIE, path_frame, walk_frame)`, add `from swingbot.core.market.indicators import atr`, and append:

```python
# CLEAN at t=16: origin L 8.5, end H 15.5, size 7.0, Close 13, lows since the end 13.5/13/12.5.
CLEAN_16 = {"level_382": 12.826, "level_500": 12.0, "level_618": 11.174,
            "retrace_now": 2.5 / 7, "retrace_deepest": 3.0 / 7, "zone_touch": 0.0, "broke_structure": 1.0}


@pytest.mark.parametrize("mirror,direction", SIDES)
def test_clean_leg_features(mirror, direction):
    df = path_frame(CLEAN[:17], mirror=mirror)
    row = fl.impulse_leg(df, direction, 3).iloc[-1]
    expect(row, CLEAN_16, mirror)
    assert row["leg_atr"] == pytest.approx(7.0 / atr(df).iloc[-1])


@pytest.mark.parametrize("mirror,direction", SIDES)
def test_zone_touch_true(mirror, direction):
    # bar 17: p=12 -> Low 11.5 <= level_500 12.0 and Close 12.0 >= level_618 11.174
    expect(leg(CLEAN, mirror, direction, 17),
           {"zone_touch": 1.0, "retrace_now": 3.5 / 7, "retrace_deepest": 4.0 / 7}, mirror)


@pytest.mark.parametrize("mirror,direction", SIDES)
def test_leg_that_does_not_break_the_prior_high(mirror, direction):
    assert leg(HIGH_PRIOR, mirror, direction, 16)["broke_structure"] == 0.0   # 15.5 < 17.5


@pytest.mark.parametrize("mirror,direction", SIDES)
def test_restarted_leg_breaks_the_previous_end(mirror, direction):
    # origin bar 18; the swing high before it is bar 13 (H 15.5); end 16.5 > 15.5
    assert leg(RESTART, mirror, direction, 25)["broke_structure"] == 1.0


@pytest.mark.parametrize("mirror,direction", SIDES)
def test_no_prior_pivot_gives_nan_break_and_young_atr_gives_nan(mirror, direction):
    row = leg(NO_PRIOR, mirror, direction, 12)           # 13 bars: ATR14 not defined yet
    expect(row, {"origin_idx": 4, "end_idx": 9, "end_price": 14.5}, mirror)
    assert np.isnan(row["broke_structure"])
    assert np.isnan(row["leg_atr"])
```

- [ ] **Step 2: Run** `python scripts/dev/testrun.py file tests/market/test_fib_leg.py`. Expect the five new tests to FAIL (levels NaN). The V124-1 tests still pass.
- [ ] **Step 3: Implement.** Replace `_features` and add `_prior_break` above it:

```python
def _prior_break(o: SimpleNamespace, origin: int, end_price: float) -> float:
    """1.0 if the end exceeds the last opposite-side pivot BEFORE the origin,
    0.0 if not, NaN if none exists. Any such pivot is confirmed by t: its
    confirmation bar is < origin + k <= t."""
    earlier = o.prior[o.prior < origin]
    if earlier.size == 0:
        return np.nan
    return float(end_price > o.hi[earlier[-1]])


def _features(o: SimpleNamespace, t: int, origin: int, end: int) -> dict | None:
    """Oriented leg row at bar t; None when the leg has no size."""
    origin_price, end_price = float(o.lo[origin]), float(o.hi[end])
    size = end_price - origin_price
    if not size > 0:
        return None
    levels = {f"level_{round(ratio * 1000)}": end_price - ratio * size for ratio in RATIOS}
    atr_t = float(o.atr[t])
    return {"origin_idx": float(origin), "origin_price": origin_price,
            "end_idx": float(end), "end_price": end_price,
            "leg_atr": size / atr_t if atr_t > 0 else np.nan,
            "leg_bars": float(end - origin), **levels,
            "retrace_now": (end_price - float(o.close[t])) / size,
            "retrace_deepest": (end_price - float(o.lo[end + 1:t + 1].min())) / size,
            "zone_touch": float(o.lo[t] <= levels["level_500"] and o.close[t] >= levels["level_618"]),
            "broke_structure": _prior_break(o, origin, end_price)}
```

- [ ] **Step 4: Run** `python scripts/dev/testrun.py file tests/market/test_fib_leg.py`. Expect PASS (the truncation test now covers every column). Run `python -m radon cc -s -n C swingbot/core/market/fib_leg.py` and expect no output.
- [ ] **Step 5: Commit.**

```bash
git add swingbot/core/market/fib_leg.py tests/market/test_fib_leg.py
git commit -m "feat(v124): impulse-leg levels, retracement, zone touch and structure break"
```

