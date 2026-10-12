# v133 — Liquidity pools and four-role coverage: Part 1 (liquidity, roles, snapshot)

> Header block, goal, preconditions, frozen readings, global constraints and the parallelisation map live in [`2026-10-06-v133-liquidity-role-coverage_0-index.md`](2026-10-06-v133-liquidity-role-coverage_0-index.md). Read that file first; pull single tasks from this one (`/task-brief V133-2`).

# Phase 1 — Liquidity instrument and storage re-check

### Task V133-1: Pool event table — `pools` and `pools_asof`

**Files:**
- Create: `swingbot/core/market/liquidity.py`
- Create: `tests/market/liquidity_fixtures.py`
- Test: `tests/market/test_liquidity_pools.py`

**Interfaces:**
- Consumes: `structure.pivot_confirmations(df, k) -> (sh_flags, sl_flags)` indexed by confirmation bar; `structure.PIVOT_K`; `indicators.atr(df, 14)`.
- Produces: `liquidity.pools(df) -> DataFrame` with `POOL_COLUMNS`; `liquidity.pools_asof(table, t) -> DataFrame`; `liquidity._pool_table(df, atr_arr)`; constants `POOL_TOLERANCE_ATR`, `POOL_LOOKBACK_BARS`, `SWEEP_RECLAIM_BARS`, `SELL_SIDE`, `BUY_SIDE`, `POOL_COLUMNS`. The fixtures module `tests.market.liquidity_fixtures` (`build`, `walk`, `equal_lows`, `two_sided`, `rising`, `m`, `side`, `WICK`, `THIRD_BAR`, `FOURTH_BAR`, `REJECTION`, `FOLLOW_THROUGH`, `RECLAIM`, `I1`, `I2`, `EXISTS`, `EVENT`) is used by V133-2, V133-4, V133-5 and V133-7.

The buy side is computed by handing the same code negated highs and closes, so there is one implementation and "below" always means "through". `pools` is an event table over the whole frame and therefore holds facts dated after any earlier bar; `pools_asof` is the only reader allowed at a bar.

- [ ] **Step 1: Create the fixtures module**

`tests/market/liquidity_fixtures.py`:

```python
"""Hand-built OHLC frames with exact pool geometry (v133).

Closes move at most 1.0 per bar and every unedited bar spans close +/- 1.0, so
its true range is exactly 2.0 and ATR14 is 2.0: POOL_TOLERANCE_ATR is 0.5
price units and "0.2 ATR apart" is a 0.4 gap. ``mirror=True`` reflects every
price about 100 (``m``), turning each bullish case into its bearish twin.
"""
import numpy as np
import pandas as pd

AXIS = 200.0
WARM = [120, 130, 114, 126, 110, 122]     # turning points at bars 0, 10, 26, 38, 54, 66; no two within 0.5
I1, I2, EXISTS, END = 88, 104, 107, 110   # equal_lows(): the two pivots, the pool's first bar, the last bar
EVENT = 116                               # the first bar after equal_lows() plus a five-bar slide


def m(price: float, mirror: bool = True) -> float:
    return AXIS - price if mirror else price


def side(mirror: bool) -> str:
    return "bearish" if mirror else "bullish"


def walk(points) -> list[float]:
    """Closes from turning point to turning point in steps of at most 1.0."""
    closes = [float(points[0])]
    for target in points[1:]:
        while abs(target - closes[-1]) > 1.0:
            closes.append(closes[-1] + (1.0 if target > closes[-1] else -1.0))
        if target != closes[-1]:
            closes.append(float(target))
    return closes


def build(closes, *, edits=None, mirror=False) -> pd.DataFrame:
    """OHLCV from closes (Open = prior close, High/Low = close +/- 1), then
    per-bar ``edits`` ({pos: {"Low": x, ...}}), then the optional mirror."""
    close = np.asarray(closes, dtype=float)
    cols = {"Open": np.concatenate([[close[0]], close[:-1]]), "High": close + 1.0,
            "Low": close - 1.0, "Close": close.copy()}
    for pos, bar in (edits or {}).items():
        for name, value in bar.items():
            cols[name][pos] = value
    if mirror:
        cols = {"Open": AXIS - cols["Open"], "High": AXIS - cols["Low"],
                "Low": AXIS - cols["High"], "Close": AXIS - cols["Close"]}
    cols["Volume"] = np.full(len(close), 1_000_000.0)
    return pd.DataFrame(cols, index=pd.bdate_range("2019-01-01", periods=len(close)))


def equal_lows(gap=0.4, *, between=(108,), tail=(), edits=None, mirror=False) -> pd.DataFrame:
    """Swing low 99.0 at bar 88 and a second at 99.0 + gap (bar 104 with the
    default ``between``), a rise to close 106 (bar 110), then ``tail``."""
    closes = walk(WARM + [100, *between, 100 + gap, 106]) + [float(c) for c in tail]
    return build(closes, edits=edits, mirror=mirror)


SLIDE = (105, 104, 103, 102, 101)         # bars 111..115: back down, every low still above 99
WICK = dict(tail=SLIDE + (100.5, 101.5, 102.5, 103.5, 104.5), edits={EVENT: {"Low": 97.0}})
THIRD_BAR = dict(tail=SLIDE + (98.5, 98.0, 98.2, 99.5, 100.5, 101.5, 102.5, 103.5))
FOURTH_BAR = dict(tail=SLIDE + (98.5, 98.0, 98.2, 98.6, 99.5, 100.5, 101.5, 102.5, 103.5))


def two_sided(*, high_gap=0.4, mirror=False) -> pd.DataFrame:
    """Equal highs 123.0 and 123.0 - high_gap above, equal lows 99.0 and 99.4
    below, ending at close 110 between them."""
    return build(walk(WARM + [100, 122 - high_gap, 100.4, 110]), mirror=mirror)


def rising(*, mirror=False) -> pd.DataFrame:
    """71 bars straight up: no swing low ever confirms (mirrored: no swing high)."""
    return build(walk([100, 170]), mirror=mirror)


# Entry bars for the trigger. Bar 116 reacts at L = 99.4, the swing low at bar 104.
APPROACH = (105, 104, 103, 102, 101.4)    # bars 111..115
REJECTION = dict(tail=APPROACH + (101.8,), edits={EVENT: {"Low": 99.6, "High": 102.0}})
FOLLOW_THROUGH = dict(tail=APPROACH + (103.0,), edits={EVENT: {"Low": 99.8, "High": 103.2}})
RECLAIM = dict(tail=(105, 104, 103, 102, 99.0, 100.0))
```

Why the geometry is exact: a close path with steps of at most 1.0 and bars of close ± 1.0 has a true range of exactly 2.0 on every bar, so ATR14 is 2.0 and the tolerance is 0.5. `equal_lows(0.4)` puts the second low 0.2 ATR above the first; `equal_lows(0.6)` puts it 0.3 ATR above.

- [ ] **Step 2: Write the failing tests**

`tests/market/test_liquidity_pools.py`:

```python
"""v133: equal-high / equal-low pools and their sweeps, as an event table."""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from swingbot.core.market import liquidity as lq
from swingbot.core.market.indicators import atr
from tests.market import liquidity_fixtures as fx

MIRRORS = pytest.mark.parametrize("mirror", [False, True], ids=["bullish", "bearish"])
TSLA = Path(__file__).resolve().parents[1] / "fixtures" / "ohlcv" / "TSLA.csv"


def _pool_side(mirror):
    """The side the fixture's equal pivots form: equal lows, or equal highs when mirrored."""
    return lq.BUY_SIDE if mirror else lq.SELL_SIDE


def _own(table, mirror):
    return table[table["side"] == _pool_side(mirror)].reset_index(drop=True)


def _nan(value) -> bool:
    return bool(np.isnan(value))


def test_the_frozen_constants():
    assert (lq.POOL_TOLERANCE_ATR, lq.POOL_LOOKBACK_BARS, lq.SWEEP_RECLAIM_BARS) == (0.25, 100, 3)
    assert lq.POOL_COLUMNS == ("side", "level", "older_pos", "newer_pos", "exists_pos", "dead_pos", "sweep_pos")


@MIRRORS
def test_the_fixture_atr_is_two_so_a_quarter_atr_is_half_a_point(mirror):
    assert atr(fx.equal_lows(mirror=mirror), 14).iloc[fx.EXISTS] == pytest.approx(2.0)


@MIRRORS
def test_two_pivots_a_fifth_of_an_atr_apart_form_a_pool(mirror):
    table = lq.pools(fx.equal_lows(0.4, mirror=mirror))
    assert len(table) == 1
    pool = table.iloc[0]
    assert pool["side"] == _pool_side(mirror)
    assert pool["level"] == pytest.approx(fx.m(99.0, mirror))        # the more extreme of the two pivots
    assert (pool["older_pos"], pool["newer_pos"], pool["exists_pos"]) == (fx.I1, fx.I2, fx.EXISTS)
    assert _nan(pool["dead_pos"]) and _nan(pool["sweep_pos"])


@MIRRORS
def test_two_pivots_three_tenths_of_an_atr_apart_form_no_pool(mirror):
    assert lq.pools(fx.equal_lows(0.6, mirror=mirror)).empty


@MIRRORS
def test_pivots_exactly_100_bars_apart_pool_and_101_or_more_do_not(mirror):
    at_limit = lq.pools(fx.equal_lows(0.0, between=(150,), mirror=mirror))
    assert (at_limit.iloc[0]["newer_pos"] - at_limit.iloc[0]["older_pos"]) == 100
    assert lq.pools(fx.equal_lows(0.0, between=(151,), mirror=mirror)).empty     # 102 bars apart


@MIRRORS
def test_an_undercut_between_the_two_pivots_forms_no_pool(mirror):
    table = lq.pools(fx.equal_lows(0.4, between=(108, 98, 108), mirror=mirror))
    assert _own(table, mirror).empty
    assert len(table) == 1          # the two equal 108 turns either side of the undercut pool on the OTHER side


@MIRRORS
def test_a_pool_never_exists_before_its_newer_pivot_is_confirmed(mirror):
    df = fx.equal_lows(mirror=mirror)
    assert lq.pools(df.iloc[:fx.EXISTS]).empty                  # last bar is EXISTS - 1
    assert len(lq.pools(df.iloc[:fx.EXISTS + 1])) == 1
    assert lq.pools_asof(lq.pools(df), fx.EXISTS - 1).empty


@MIRRORS
def test_a_wick_through_the_pool_with_a_same_bar_close_back_is_a_sweep_at_that_bar(mirror):
    pool = _own(lq.pools(fx.equal_lows(mirror=mirror, **fx.WICK)), mirror).iloc[0]
    assert (pool["dead_pos"], pool["sweep_pos"]) == (fx.EVENT, fx.EVENT)


@MIRRORS
def test_a_close_back_on_the_third_bar_after_is_a_sweep(mirror):
    pool = _own(lq.pools(fx.equal_lows(mirror=mirror, **fx.THIRD_BAR)), mirror).iloc[0]
    assert (pool["dead_pos"], pool["sweep_pos"]) == (fx.EVENT, fx.EVENT + lq.SWEEP_RECLAIM_BARS)


@MIRRORS
def test_a_close_back_on_the_fourth_bar_after_is_a_break_with_no_sweep(mirror):
    pool = _own(lq.pools(fx.equal_lows(mirror=mirror, **fx.FOURTH_BAR)), mirror).iloc[0]
    assert pool["dead_pos"] == fx.EVENT and _nan(pool["sweep_pos"])


@MIRRORS
def test_a_sweep_is_not_visible_before_its_reclaim_bar(mirror):
    df = fx.equal_lows(mirror=mirror, **fx.THIRD_BAR)
    reclaim = fx.EVENT + lq.SWEEP_RECLAIM_BARS
    for t in range(fx.EVENT, reclaim):
        for seen in (lq.pools(df.iloc[:t + 1]), lq.pools_asof(lq.pools(df), t)):
            pool = _own(seen, mirror).iloc[0]
            assert pool["dead_pos"] == fx.EVENT and _nan(pool["sweep_pos"]), t
    assert _own(lq.pools(df.iloc[:reclaim + 1]), mirror).iloc[0]["sweep_pos"] == reclaim


def _assert_every_cut_matches(df, start=0):
    full = lq.pools(df)
    for t in range(start, len(df)):
        pd.testing.assert_frame_equal(lq.pools(df.iloc[:t + 1]), lq.pools_asof(full, t), obj=f"cut {t}")


@MIRRORS
@pytest.mark.parametrize("make", [lambda mirror: fx.equal_lows(mirror=mirror, **fx.WICK),
                                  lambda mirror: fx.equal_lows(mirror=mirror, **fx.THIRD_BAR),
                                  lambda mirror: fx.equal_lows(mirror=mirror, **fx.FOURTH_BAR),
                                  lambda mirror: fx.two_sided(mirror=mirror)],
                         ids=["wick", "third-bar", "fourth-bar", "two-sided"])
def test_truncation_equals_the_as_of_view_at_every_cut_of_the_fixtures(make, mirror):
    _assert_every_cut_matches(make(mirror))


@pytest.mark.slow
def test_truncation_equals_the_as_of_view_at_every_cut_of_a_real_symbol():
    df = pd.read_csv(TSLA, index_col="Date", parse_dates=True).iloc[:400]
    full = lq.pools(df)
    assert len(full) >= 5 and full["sweep_pos"].notna().any() and full["dead_pos"].notna().any()
    assert {lq.SELL_SIDE, lq.BUY_SIDE} <= set(full["side"])
    _assert_every_cut_matches(df)


def test_a_frame_too_short_for_any_pivot_gives_an_empty_table_with_the_columns():
    table = lq.pools(fx.equal_lows().iloc[:5])
    assert table.empty and tuple(table.columns) == lq.POOL_COLUMNS
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/market/test_liquidity_pools.py`
Expected: FAIL at collection with `ImportError: cannot import name 'liquidity' from 'swingbot.core.market'`.

- [ ] **Step 4: Write the implementation**

`swingbot/core/market/liquidity.py`:

```python
"""Equal-high / equal-low liquidity pools and their sweeps (v133).

A pool is two confirmed k=3 swing pivots at nearly the same price. Pivots come
only from v121's ``structure.pivot_confirmations`` -- the single home of the
confirmation lag -- so a pool whose newer pivot is at ``i2`` exists from bar
``i2 + 3`` and is never back-dated. A pool is live until the first bar that
trades through its level, and dead from that bar whatever follows. If a close
comes back across the level within ``SWEEP_RECLAIM_BARS`` bars, that is a
sweep-and-reclaim: dated at the reclaim bar and a fact only from that bar on.

``reaction.is_reclaim`` is deliberately not used: it needs an earlier CLOSE
through the level, so it misses the wick-only sweep.

NO-LOOKAHEAD: ``pools(df)`` is an event table over the whole frame, so a row
can hold facts dated after any earlier bar. ``pools_asof(table, t)`` is the
only way to read it at bar ``t``, and ``features_at`` always goes through it.
The constants are frozen descriptive definitions, not config knobs. No I/O.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from swingbot.core.market.indicators import atr
from swingbot.core.market.structure import PIVOT_K, pivot_confirmations

POOL_TOLERANCE_ATR = 0.25    # two pivots this close are "equal"
POOL_LOOKBACK_BARS = 100     # a pool's older pivot is at most this far behind its newer one
SWEEP_RECLAIM_BARS = 3       # a sweep must close back within this many bars
SELL_SIDE, BUY_SIDE = "sell", "buy"   # equal lows / equal highs
POOL_COLUMNS = ("side", "level", "older_pos", "newer_pos", "exists_pos", "dead_pos", "sweep_pos")
POOL_DTYPES = {"side": object, "level": float, "older_pos": "int64", "newer_pos": "int64",
               "exists_pos": "int64", "dead_pos": float, "sweep_pos": float}


def _is_pool(ext: np.ndarray, i1: int, i2: int, k: int, tolerance: float) -> bool:
    """Equal within tolerance, and nothing in i1+1 .. i2+k except i2 itself undercut them."""
    if abs(ext[i1] - ext[i2]) > tolerance:
        return False
    level = min(ext[i1], ext[i2])
    return not ((ext[i1 + 1:i2] < level).any() or (ext[i2 + 1:i2 + k + 1] < level).any())


def _fate(ext: np.ndarray, close: np.ndarray, level: float, exists: int) -> tuple[float, float]:
    """(dead_pos, sweep_pos): the first bar after ``exists`` that trades through the
    level, and the first close back across it within SWEEP_RECLAIM_BARS. NaN = never."""
    through = np.flatnonzero(ext[exists + 1:] < level)
    if not len(through):
        return math.nan, math.nan
    dead = exists + 1 + int(through[0])
    back = np.flatnonzero(close[dead:dead + SWEEP_RECLAIM_BARS + 1] > level)
    sweep = float(dead + int(back[0])) if len(back) else math.nan
    return float(dead), sweep


def _side_pools(ext: np.ndarray, close: np.ndarray, atr_arr: np.ndarray, flags: np.ndarray, k: int) -> list:
    """(level, older, newer, dead, sweep) per pool, in LOW space: the buy-side
    caller passes negated highs and closes, so "below" always means "through"."""
    pivots = np.flatnonzero(flags) - k
    out = []
    for b, i2 in enumerate(pivots):
        tolerance = POOL_TOLERANCE_ATR * atr_arr[i2 + k]   # ATR at the newer pivot's confirmation bar
        if not np.isfinite(tolerance):
            continue
        first = int(np.searchsorted(pivots, i2 - POOL_LOOKBACK_BARS))
        for i1 in pivots[first:b]:
            if _is_pool(ext, i1, i2, k, tolerance):
                level = float(min(ext[i1], ext[i2]))
                out.append((level, int(i1), int(i2)) + _fate(ext, close, level, int(i2) + k))
    return out


def _pool_table(df: pd.DataFrame, atr_arr: np.ndarray) -> pd.DataFrame:
    sh, sl = pivot_confirmations(df, PIVOT_K)
    high, low, close = (df[name].to_numpy(dtype=float) for name in ("High", "Low", "Close"))
    rows = [(SELL_SIDE, level, i1, i2, i2 + PIVOT_K, dead, sweep)
            for level, i1, i2, dead, sweep in _side_pools(low, close, atr_arr, sl, PIVOT_K)]
    rows += [(BUY_SIDE, -level, i1, i2, i2 + PIVOT_K, dead, sweep)
             for level, i1, i2, dead, sweep in _side_pools(-high, -close, atr_arr, sh, PIVOT_K)]
    return pd.DataFrame(rows, columns=list(POOL_COLUMNS)).astype(POOL_DTYPES)


def pools(df: pd.DataFrame) -> pd.DataFrame:
    """One row per pool over the whole frame: side, level, the two pivot bars,
    the bar it exists from (newer pivot + 3), the bar it died and its
    sweep-and-reclaim bar (NaN where neither happened). Positional indices.
    Read it at a bar only through ``pools_asof``."""
    return _pool_table(df, atr(df, 14).to_numpy(dtype=float))


def pools_asof(table: pd.DataFrame, t: int) -> pd.DataFrame:
    """What bar ``t`` knew: pools that exist by ``t``, with any death or sweep
    dated after ``t`` blanked. ``pools(df.iloc[:t + 1])`` equals this exactly."""
    known = table[table["exists_pos"] <= t].copy()
    for column in ("dead_pos", "sweep_pos"):
        known[column] = known[column].where(known[column] <= t)
    return known.reset_index(drop=True)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/market/test_liquidity_pools.py`
Expected: `0 failed`. The real-symbol test is `slow` and takes about 2–4 s.

- [ ] **Step 6: Complexity**

Run: `python -m radon cc -s -n C swingbot/core/market/liquidity.py`
Expected: no output (every function is A or B).

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/market/liquidity.py tests/market/liquidity_fixtures.py tests/market/test_liquidity_pools.py
git commit -m "feat(v133): equal-high/low liquidity pools and sweeps as a causal event table"
```

### Task V133-2: The five liquidity keys — `features_at` and `liquidity_features`

**Files:**
- Modify: `swingbot/core/market/liquidity.py` (append; one import line and one constant change)
- Test: `tests/market/test_liquidity_features.py`

**Interfaces:**
- Consumes: `_pool_table(df, atr_arr)`, `pools`, `pools_asof`, `SELL_SIDE`, `BUY_SIDE`, `POOL_TOLERANCE_ATR` (V133-1); `structure.MIN_BARS`, `structure._num`.
- Produces: `liquidity.LIQUIDITY_KEYS = ("liq_stop_side_atr", "liq_target_side_atr", "liq_sweep_bars_ago", "stop_in_pool", "target_past_pool")`; `liquidity.features_at(table, t, close, atr_value, direction, stop, target) -> dict`; `liquidity.liquidity_features(df, direction, stop, target) -> dict`. V133-4, V133-5 and V133-7 import these.

Everything is stated for the trade's direction through one `sign`: `+1` bullish (stop side = sell-side pools below the close), `−1` bearish (stop side = buy-side pools above it). `liq_sweep_bars_ago` judges "stop side" by the pool's kind only, not by where its level sits against the close.

- [ ] **Step 1: Write the failing tests**

`tests/market/test_liquidity_features.py`:

```python
"""v133: the five liquidity keys at the entry bar."""
import json
from pathlib import Path

import pandas as pd
import pytest

from swingbot.core.market import liquidity as lq
from swingbot.core.market.indicators import atr
from swingbot.core.market.structure import _num
from tests.market import liquidity_fixtures as fx

MIRRORS = pytest.mark.parametrize("mirror", [False, True], ids=["bullish", "bearish"])
TSLA = Path(__file__).resolve().parents[1] / "fixtures" / "ohlcv" / "TSLA.csv"
NONE = dict.fromkeys(lq.LIQUIDITY_KEYS)


def _features(df, mirror, *, stop=90.0, target=130.0):
    """Stop and target are written for the bullish frame and mirrored with it."""
    return lq.liquidity_features(df, fx.side(mirror), fx.m(stop, mirror), fx.m(target, mirror))


def test_the_key_list():
    assert lq.LIQUIDITY_KEYS == ("liq_stop_side_atr", "liq_target_side_atr", "liq_sweep_bars_ago",
                                 "stop_in_pool", "target_past_pool")


@MIRRORS
def test_distances_to_the_nearest_live_pool_on_each_side(mirror):
    out = _features(fx.two_sided(mirror=mirror), mirror)        # close 110, pools at 99 and 123, ATR 2
    assert out["liq_stop_side_atr"] == pytest.approx(5.5)
    assert out["liq_target_side_atr"] == pytest.approx(6.5)
    assert out["liq_sweep_bars_ago"] is None


def test_the_sides_swap_with_the_trade_direction_on_one_frame():
    df = fx.two_sided()
    short = lq.liquidity_features(df, "bearish", 123.2, 97.0)   # a short's stop side is the equal highs
    assert (short["liq_stop_side_atr"], short["liq_target_side_atr"]) == (pytest.approx(6.5), pytest.approx(5.5))
    assert short["stop_in_pool"] is True and short["target_past_pool"] is True


@MIRRORS
@pytest.mark.parametrize("stop,expected", [(98.8, True),     # just beyond the level, inside 0.25 ATR
                                           (99.0, True),     # on the level
                                           (99.3, False),    # short of the level
                                           (98.0, False)],   # beyond the tolerance
                         ids=["just-beyond", "on-level", "short-of-level", "past-tolerance"])
def test_stop_in_pool(mirror, stop, expected):
    assert _features(fx.two_sided(mirror=mirror), mirror, stop=stop)["stop_in_pool"] is expected


@MIRRORS
@pytest.mark.parametrize("target,expected", [(125.0, True), (123.0, False), (120.0, False)],
                         ids=["past", "at", "before"])
def test_target_past_pool(mirror, target, expected):
    assert _features(fx.two_sided(mirror=mirror), mirror, target=target)["target_past_pool"] is expected


@MIRRORS
def test_no_target_side_pool_gives_none_not_false(mirror):
    out = _features(fx.two_sided(high_gap=2.0, mirror=mirror), mirror)
    assert out["target_past_pool"] is None and out["liq_target_side_atr"] is None
    assert out["liq_stop_side_atr"] == pytest.approx(5.5)


@MIRRORS
def test_no_stop_side_pool_gives_none_distance_and_false_flag(mirror):
    out = _features(fx.rising(mirror=mirror), mirror)
    assert out["liq_stop_side_atr"] is None and out["stop_in_pool"] is False
    assert out["liq_sweep_bars_ago"] is None


@MIRRORS
def test_sweep_bars_ago_counts_from_the_reclaim_bar(mirror):
    df = fx.equal_lows(mirror=mirror, **fx.THIRD_BAR)
    reclaim = fx.EVENT + lq.SWEEP_RECLAIM_BARS
    assert _features(df.iloc[:reclaim], mirror)["liq_sweep_bars_ago"] is None      # last bar is reclaim - 1
    assert _features(df.iloc[:reclaim + 1], mirror)["liq_sweep_bars_ago"] == 0
    assert _features(df.iloc[:reclaim + 3], mirror)["liq_sweep_bars_ago"] == 2


@MIRRORS
def test_a_same_bar_wick_sweep_is_dated_at_that_bar(mirror):
    df = fx.equal_lows(mirror=mirror, **fx.WICK)
    assert _features(df.iloc[:fx.EVENT], mirror)["liq_sweep_bars_ago"] is None
    assert _features(df.iloc[:fx.EVENT + 1], mirror)["liq_sweep_bars_ago"] == 0


@MIRRORS
def test_a_swept_pool_counts_by_its_kind_even_when_price_is_back_through_it(mirror):
    tail = fx.THIRD_BAR["tail"][:9] + (98.0,)                    # reclaim at bar 119, then a close under 99 again
    out = _features(fx.equal_lows(mirror=mirror, tail=tail), mirror)
    assert out["liq_sweep_bars_ago"] == 1
    assert out["liq_stop_side_atr"] is None                      # the pool is dead; nothing live remains


@MIRRORS
def test_a_broken_pool_is_never_live_again(mirror):
    df = fx.equal_lows(mirror=mirror, **fx.FOURTH_BAR)           # ends at close 103.5, back above 99
    out = _features(df, mirror, stop=98.8)
    assert out["liq_stop_side_atr"] is None and out["liq_sweep_bars_ago"] is None
    assert out["stop_in_pool"] is False
    before = _features(df.iloc[:fx.EVENT], mirror, stop=98.8)    # the bar before it broke
    assert before["liq_stop_side_atr"] is not None and before["stop_in_pool"] is True


@MIRRORS
@pytest.mark.parametrize("bars", [0, 10, 59])
def test_short_frames_return_all_none(mirror, bars):
    assert _features(fx.two_sided(mirror=mirror).iloc[:bars], mirror) == NONE


def test_a_missing_frame_stop_or_target_never_raises():
    df = fx.two_sided()
    assert lq.liquidity_features(None, "bullish", 98.8, 125.0) == NONE
    out = lq.liquidity_features(df, "bullish", None, float("nan"))
    assert out["stop_in_pool"] is None and out["target_past_pool"] is None
    assert out["liq_stop_side_atr"] == pytest.approx(5.5)


def test_a_flat_frame_has_no_atr_and_no_pools():
    out = lq.liquidity_features(fx.build([100.0] * 80, edits={i: {"High": 100.0, "Low": 100.0} for i in range(80)}),
                                "bullish", 99.0, 101.0)
    assert out["liq_stop_side_atr"] is None and out["stop_in_pool"] is None and out["target_past_pool"] is None


def _assert_every_cut_matches(df, direction, start=lq.MIN_BARS - 1):
    """liquidity_features on df.iloc[:t + 1] == the keys read at row t of the FULL frame's pool table."""
    table, atr_full = lq.pools(df), atr(df, 14)
    close = df["Close"].to_numpy(dtype=float)
    sign = 1.0 if direction == "bullish" else -1.0
    for t in range(start, len(df)):
        stop, target = close[t] * (1 - sign * 0.03), close[t] * (1 + sign * 0.06)
        expected = lq.features_at(table, t, float(close[t]), _num(atr_full.iloc[t]), direction, stop, target)
        assert lq.liquidity_features(df.iloc[:t + 1], direction, stop, target) == expected, t


@MIRRORS
@pytest.mark.parametrize("spec", [fx.WICK, fx.THIRD_BAR, fx.FOURTH_BAR], ids=["wick", "third-bar", "fourth-bar"])
def test_truncation_equality_at_every_cut_of_the_sweep_fixtures(spec, mirror):
    _assert_every_cut_matches(fx.equal_lows(mirror=mirror, **spec), fx.side(mirror))


@pytest.mark.slow
@MIRRORS
@pytest.mark.parametrize("direction", ["bullish", "bearish"])
def test_truncation_equality_at_every_cut_of_the_two_sided_fixture(mirror, direction):
    _assert_every_cut_matches(fx.two_sided(mirror=mirror), direction)


@pytest.mark.slow
@pytest.mark.parametrize("direction", ["bullish", "bearish"])
def test_truncation_equality_at_every_cut_of_a_real_symbol(direction):
    df = pd.read_csv(TSLA, index_col="Date", parse_dates=True).iloc[:400]
    _assert_every_cut_matches(df, direction)
    seen = [lq.liquidity_features(df.iloc[:t + 1], direction, 1.0, 1e6) for t in range(100, 400, 25)]
    assert any(row["liq_stop_side_atr"] is not None for row in seen)        # not a vacuous pass


PLAIN = {"liq_stop_side_atr": float, "liq_target_side_atr": float, "liq_sweep_bars_ago": int,
         "stop_in_pool": bool, "target_past_pool": bool}


@MIRRORS
def test_every_value_is_a_plain_json_type(mirror):
    """The snapshot is stored as JSONB: no numpy scalar may leak out."""
    filled = set()
    for df in (fx.two_sided(mirror=mirror), fx.equal_lows(mirror=mirror, **fx.THIRD_BAR)):
        out = _features(df, mirror)
        assert json.loads(json.dumps(out)) == out
        assert all(value is None or type(value) is PLAIN[key] for key, value in out.items())
        filled |= {key for key, value in out.items() if value is not None}
    assert filled == set(lq.LIQUIDITY_KEYS)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/market/test_liquidity_features.py`
Expected: FAIL with `AttributeError: module 'swingbot.core.market.liquidity' has no attribute 'LIQUIDITY_KEYS'`.

- [ ] **Step 3: Write the implementation**

In `swingbot/core/market/liquidity.py`, change the structure import to:

```python
from swingbot.core.market.structure import MIN_BARS, PIVOT_K, _num, pivot_confirmations
```

Add this constant directly below `POOL_DTYPES`:

```python
LIQUIDITY_KEYS = ("liq_stop_side_atr", "liq_target_side_atr", "liq_sweep_bars_ago",
                  "stop_in_pool", "target_past_pool")
```

Append to the end of the file:

```python
def _finite(value) -> bool:
    try:
        return value is not None and math.isfinite(float(value))
    except (TypeError, ValueError, OverflowError):
        return False


def _nearest(levels: np.ndarray, close: float, sign: float) -> tuple[float, float] | None:
    """(distance, level) of the nearest level with sign * (close - level) > 0."""
    distance = sign * (close - levels)
    if not (distance > 0).any():
        return None
    pick = int(np.argmin(np.where(distance > 0, distance, np.inf)))
    return float(distance[pick]), float(levels[pick])


def _stop_in_pool(levels: np.ndarray, stop, sign: float, atr_value: float | None) -> bool | None:
    if not atr_value or not _finite(stop):
        return None
    beyond = sign * (levels - float(stop))      # how far the stop sits past each level
    return bool(((beyond >= 0) & (beyond <= POOL_TOLERANCE_ATR * atr_value)).any())


def _target_past(nearest: tuple[float, float] | None, target, sign: float) -> bool | None:
    if nearest is None or not _finite(target):
        return None
    return bool(sign * (float(target) - nearest[1]) > 0)


def features_at(table: pd.DataFrame, t: int, close: float, atr_value: float | None,
                direction: str, stop, target) -> dict:
    """Every LIQUIDITY_KEYS value at bar ``t``, stated for the trade's direction,
    from a pool table that may extend past ``t``. Reads no pool fact dated after ``t``."""
    known = pools_asof(table, t)
    sign = 1.0 if direction == "bullish" else -1.0
    stop_kind, target_kind = (SELL_SIDE, BUY_SIDE) if sign > 0 else (BUY_SIDE, SELL_SIDE)
    live = known[known["dead_pos"].isna()]
    stop_levels = live.loc[live["side"] == stop_kind, "level"].to_numpy(dtype=float)
    stop_levels = stop_levels[sign * (close - stop_levels) > 0]
    target_levels = live.loc[live["side"] == target_kind, "level"].to_numpy(dtype=float)
    nearest_stop, nearest_target = _nearest(stop_levels, close, sign), _nearest(target_levels, close, -sign)
    swept = known.loc[(known["side"] == stop_kind) & known["sweep_pos"].notna(), "sweep_pos"]
    return {
        "liq_stop_side_atr": _num(nearest_stop[0] / atr_value) if atr_value and nearest_stop else None,
        "liq_target_side_atr": _num(nearest_target[0] / atr_value) if atr_value and nearest_target else None,
        "liq_sweep_bars_ago": int(t - swept.max()) if len(swept) else None,
        "stop_in_pool": _stop_in_pool(stop_levels, stop, sign, atr_value),
        "target_past_pool": _target_past(nearest_target, target, sign),
    }


def liquidity_features(df: pd.DataFrame, direction: str, stop, target) -> dict:
    """Every LIQUIDITY_KEYS value at ``df``'s final bar. Reads only ``df``;
    fewer than 60 bars (or no frame) returns all None. Never raises on a
    missing stop or target: that key is None."""
    out = dict.fromkeys(LIQUIDITY_KEYS)
    if df is None or len(df) < MIN_BARS:
        return out
    close = float(df["Close"].iloc[-1])
    if not math.isfinite(close):
        return out
    atr_arr = atr(df, 14).to_numpy(dtype=float)
    out.update(features_at(_pool_table(df, atr_arr), len(df) - 1, close, _num(atr_arr[-1]),
                           direction, stop, target))
    return out
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/market/test_liquidity_features.py`
Expected: `0 failed`. Then re-run V133-1's file, which shares the module: `python scripts/dev/testrun.py file tests/market/test_liquidity_pools.py`, `0 failed`.

- [ ] **Step 5: Complexity**

Run: `python -m radon cc -s -n C swingbot/core/market/liquidity.py`
Expected: no output. `features_at` is the largest at `B (8)`.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/market/liquidity.py tests/market/test_liquidity_features.py
git commit -m "feat(v133): five liquidity keys at the entry bar, read as-of from the pool table"
```

### Task V133-3: Storage re-check for the ten new `entry_context` keys

**Files:**
- Test: `tests/db/test_entry_context_roles_doc.py` (new)
- No schema, repository or Alembic file changes are expected. If Step 2 finds otherwise, stop: see Step 5.

**Interfaces:**
- Consumes: `TradeRepository`, `schema.trades`, `schema.plans`, `performance._db_record` / `_json_record`, `context.FEATURE_KEYS` (all pre-existing). Names the ten new keys as string literals, so it does not wait for V133-1.
- Produces: the recorded finding "add → `doc`, no revision", which V133-5 relies on.

- [ ] **Step 1: Invoke the `schema-change` skill** and read `docs/claude/schema-evolution.md`. The operation under test is **add**: "Write the field. It lands in `doc`. Migration: none."

- [ ] **Step 2: Confirm how v121's and v125's keys are stored**

```bash
git grep -n "entry_context" -- swingbot/core/db
git grep -n "\"entry_context\"" -- swingbot/core/tracking/performance.py
python -m alembic heads
```

Expected: the first command prints nothing (`entry_context` is not a promoted column on any table, so it rides in `doc JSONB`); the second shows `performance.py` writing `"entry_context": entry_context or {}` into the trade record; the third prints exactly one head. Write the head id into the commit body in Step 4: it must be the same after this plan.

- [ ] **Step 3: Write the pinning test**

`tests/db/test_entry_context_roles_doc.py`:

```python
"""v133: the ten liquidity / role keys ride in trades.doc JSONB -- an "add", so no revision."""
from swingbot.core.db.repositories.trades import TradeRepository
from swingbot.core.db.schema import plans, trades
from swingbot.core.edge.context import FEATURE_KEYS
from swingbot.core.tracking.performance import _db_record, _json_record

V133 = {"liq_stop_side_atr": 0.8, "liq_target_side_atr": 2.5, "liq_sweep_bars_ago": 3, "stop_in_pool": True,
        "target_past_pool": False, "role_context": True, "role_location": False, "role_path": True,
        "role_trigger": None, "role_coverage": None}


def _trade(trade_id, context):
    return {"id": trade_id, "ticker": "AAPL", "strategy": "RSI", "horizon_key": "2w",
            "direction": "bullish", "status": "open", "opened_at": "2026-10-06T15:00:00+00:00",
            "entry_context": context}


def test_entry_context_is_a_doc_payload_on_both_tables():
    assert "entry_context" not in trades.c and "entry_context" not in plans.c
    assert not {column.name for column in trades.c} & set(V133)


def test_the_ten_keys_round_trip_with_their_types(db_conn):
    context = {key: None for key in FEATURE_KEYS} | V133
    repository = TradeRepository()
    repository.insert(_db_record(_trade("V133-T1", context)), conn=db_conn)
    back = _json_record(repository.get("V133-T1", conn=db_conn))["entry_context"]
    assert back == context
    assert type(back["liq_sweep_bars_ago"]) is int and type(back["liq_stop_side_atr"]) is float
    assert back["stop_in_pool"] is True and back["target_past_pool"] is False
    assert "role_trigger" in back and back["role_trigger"] is None       # an explicit None survives as a key


def test_a_full_coverage_count_round_trips_as_an_int(db_conn):
    context = V133 | {"role_trigger": True, "role_coverage": 3}
    repository = TradeRepository()
    repository.insert(_db_record(_trade("V133-T2", context)), conn=db_conn)
    back = _json_record(repository.get("V133-T2", conn=db_conn))["entry_context"]
    assert type(back["role_coverage"]) is int and back["role_coverage"] == 3


def test_an_old_record_reads_every_new_key_as_none(db_conn):
    repository = TradeRepository()
    repository.insert(_db_record(_trade("V133-T0", {"vol_ratio_20": 1.2})), conn=db_conn)
    back = _json_record(repository.get("V133-T0", conn=db_conn))["entry_context"]
    assert all(back.get(key) is None for key in V133)
    assert back == {"vol_ratio_20": 1.2}       # nothing upcast on read
```

This is a pinning test: it passes on first run, because the storage layer already does the right thing. A failure is the finding.

- [ ] **Step 4: Run and commit**

Run: `python scripts/dev/testrun.py file tests/db/test_entry_context_roles_doc.py`, then the unknown-field contract test the skill names: `python scripts/dev/testrun.py file tests/db/test_unknown_field_round_trip.py`.
Expected: `0 failed`. The `db_conn` fixture needs the test Postgres (`tests/db/conftest.py`); if the verdict line reports the tests as skipped rather than passed, say so in the task report instead of calling it green.

```bash
git add tests/db/test_entry_context_roles_doc.py
git commit -m "test(v133): ten liquidity/role keys round-trip through trades.doc -- add, no revision"
```

Commit body: the Step 2 findings in two lines (no promoted column; Alembic head id unchanged).

- [ ] **Step 5 (only if Step 2 or Step 4 contradicts the above):** stop and report BLOCKED with the evidence. A promoted `entry_context` column or a failing round trip means the keys need an Alembic revision (`v133_001`, `down_revision` = the current head, following the skill's Steps 2–4), and that is a scope change the controller must approve before any DDL is written.

# Phase 2 — Role flags and the snapshot

### Task V133-4: Role flags — `roles.py`

**Files:**
- Create: `swingbot/core/market/roles.py`
- Test: `tests/market/test_roles.py`

**Interfaces:**
- Consumes: the v121 dict keys `structure_aligned`, `swing_low_atr`, `swing_high_atr` (`structure.structure_features`; `swing_high_atr = (last_sh − close) / ATR`, `swing_low_atr = (close − last_sl) / ATR`, not direction-stated); the liquidity dict keys `liq_stop_side_atr`, `liq_sweep_bars_ago` (V133-2); `reaction.Bars.from_frame(df)`, `reaction.is_test(bars, t, level, direction, k, atr_t)`, `reaction.reaction_kind(bars, t, level, direction, *, tested_now, tested_prev, floor_index)`, `reaction.R1` / `R2` / `R3`, `reaction.RECLAIM_BARS`; `structure.confirmed_pivots(df, k)` columns `last_sl` / `last_sh`.
- Produces: `roles.role_features(df, direction, structure, liquidity) -> dict` and `roles.flags_at(bars, atr_arr, t, level, direction, structure, liquidity) -> dict`, both returning `ROLE_KEYS = ("role_context", "role_location", "role_path", "role_trigger", "role_coverage")`; `roles.ROLE_FLAGS` (the first four); constants `PATH_NEAR_ATR`, `PATH_SWEEP_RECENT_BARS`, `TRIGGER_TEST_K`, `TRIGGER_KINDS`.

Three flags are pure dict logic. Only the trigger reads bars, and it reads bar `t` and `t − 1` (plus `reaction_kind`'s two-bar reclaim window). `role_location` is direction-stated here: a long needs `swing_low_atr ≤ swing_high_atr` (lower half), a short the reverse.

- [ ] **Step 1: Write the failing tests**

`tests/market/test_roles.py`:

```python
"""v133: the four role flags and role_coverage."""
import json
from pathlib import Path

import pandas as pd
import pytest

from swingbot.core.market import reaction, roles
from swingbot.core.market.indicators import atr
from swingbot.core.market.liquidity import LIQUIDITY_KEYS, liquidity_features
from swingbot.core.market.structure import confirmed_pivots, structure_features
from tests.market import liquidity_fixtures as fx

MIRRORS = pytest.mark.parametrize("mirror", [False, True], ids=["bullish", "bearish"])
TSLA = Path(__file__).resolve().parents[1] / "fixtures" / "ohlcv" / "TSLA.csv"
NO_POOLS = dict.fromkeys(LIQUIDITY_KEYS) | {"stop_in_pool": False}
ALIGNED_DISCOUNT = {"structure_aligned": True, "swing_low_atr": 1.0, "swing_high_atr": 3.0}


def _structure(mirror, *, aligned=True, near=1.0, far=3.0):
    """v121 keys with the close ``near`` ATR from the swing on the trade's own side."""
    low, high = (far, near) if mirror else (near, far)
    return {"structure_aligned": aligned, "swing_low_atr": low, "swing_high_atr": high}


def _roles(df, mirror, structure=None, liquidity=None):
    return roles.role_features(df, fx.side(mirror), _structure(mirror) if structure is None else structure,
                               NO_POOLS if liquidity is None else liquidity)


def test_the_frozen_constants_and_keys():
    assert (roles.PATH_NEAR_ATR, roles.PATH_SWEEP_RECENT_BARS, roles.TRIGGER_TEST_K) == (1.0, 5, 0.25)
    assert roles.ROLE_KEYS == ("role_context", "role_location", "role_path", "role_trigger", "role_coverage")
    assert roles.TRIGGER_KINDS == (reaction.R1, reaction.R3)


@MIRRORS
@pytest.mark.parametrize("aligned,expected", [(True, True), (False, False), (None, None)])
def test_role_context_is_structure_aligned(mirror, aligned, expected):
    out = _roles(fx.equal_lows(mirror=mirror), mirror, _structure(mirror, aligned=aligned))
    assert out["role_context"] is expected


@MIRRORS
@pytest.mark.parametrize("near,far,expected", [(1.0, 3.0, True),     # inside the range, own half
                                               (2.0, 2.0, True),     # the midpoint counts
                                               (3.0, 1.0, False),    # inside, the wrong half
                                               (-0.5, 4.0, False),   # through its own swing: outside the range
                                               (1.0, -0.5, False)],  # beyond the far swing: outside the range
                         ids=["own-half", "midpoint", "wrong-half", "through-own-swing", "past-far-swing"])
def test_role_location_is_discount_for_longs_and_premium_for_shorts(mirror, near, far, expected):
    out = _roles(fx.equal_lows(mirror=mirror), mirror, _structure(mirror, near=near, far=far))
    assert out["role_location"] is expected


@pytest.mark.parametrize("missing", ["swing_low_atr", "swing_high_atr"])
def test_role_location_is_none_when_either_swing_distance_is_none(missing):
    out = _roles(fx.equal_lows(), False, ALIGNED_DISCOUNT | {missing: None})
    assert out["role_location"] is None and out["role_coverage"] is None


@pytest.mark.parametrize("near,swept,expected", [(None, None, True),    # no stop-side pool at all
                                                 (1.5, None, True),     # a pool, but more than 1 ATR away
                                                 (1.0, None, False),    # a pool within 1 ATR, never swept
                                                 (0.4, 5, True),        # in the way, but swept 5 bars ago
                                                 (0.4, 6, False),       # swept too long ago
                                                 (None, 2, True)],
                         ids=["no-pool", "far-pool", "near-pool", "recent-sweep", "stale-sweep", "swept-and-gone"])
def test_role_path(near, swept, expected):
    liquidity = NO_POOLS | {"liq_stop_side_atr": near, "liq_sweep_bars_ago": swept}
    assert _roles(fx.equal_lows(), False, liquidity=liquidity)["role_path"] is expected


def test_role_path_is_none_without_an_atr():
    flat = fx.build([100.0] * 80, edits={i: {"High": 100.0, "Low": 100.0} for i in range(80)})
    out = _roles(flat, False)
    assert out["role_path"] is None and out["role_coverage"] is None


@MIRRORS
@pytest.mark.parametrize("spec,kind,expected", [(fx.REJECTION, reaction.R1, True),
                                                (fx.RECLAIM, reaction.R3, True),
                                                (fx.FOLLOW_THROUGH, reaction.R2, False),
                                                ({}, None, False)],
                         ids=["rejection", "reclaim", "follow-through-alone", "no-reaction"])
def test_role_trigger_is_r1_or_r3_at_the_last_confirmed_swing(mirror, spec, kind, expected):
    df = fx.equal_lows(mirror=mirror, **spec)
    direction, t, level = fx.side(mirror), len(df) - 1, fx.m(99.4, mirror)
    bars, atr_arr = reaction.Bars.from_frame(df), atr(df, 14).to_numpy(dtype=float)
    tested = [reaction.is_test(bars, i, level, direction, roles.TRIGGER_TEST_K, atr_arr[i]) for i in (t, t - 1)]
    assert reaction.reaction_kind(bars, t, level, direction, tested_now=tested[0], tested_prev=tested[1],
                                  floor_index=t - reaction.RECLAIM_BARS) == kind       # the fixture is what it says
    assert _roles(df, mirror)["role_trigger"] is expected


@MIRRORS
def test_role_trigger_is_none_when_no_swing_is_confirmed(mirror):
    out = _roles(fx.rising(mirror=mirror), mirror)
    assert out["role_trigger"] is None and out["role_coverage"] is None
    assert out["role_path"] is True                              # the other flags are still stated


@MIRRORS
def test_role_coverage_counts_the_true_flags(mirror):
    all_four = _roles(fx.equal_lows(mirror=mirror, **fx.REJECTION), mirror)
    assert all_four == {"role_context": True, "role_location": True, "role_path": True,
                        "role_trigger": True, "role_coverage": 4}
    none = _roles(fx.equal_lows(mirror=mirror), mirror, _structure(mirror, aligned=False, near=3.0, far=1.0),
                  NO_POOLS | {"liq_stop_side_atr": 0.5})
    assert none["role_coverage"] == 0 and list(none.values())[:4] == [False] * 4


def test_role_coverage_is_none_when_any_flag_is_none():
    out = _roles(fx.equal_lows(**fx.REJECTION), False, ALIGNED_DISCOUNT | {"structure_aligned": None})
    assert out["role_context"] is None and out["role_coverage"] is None
    assert (out["role_location"], out["role_path"], out["role_trigger"]) == (True, True, True)


@MIRRORS
@pytest.mark.parametrize("bars", [0, 10, 59])
def test_short_frames_return_all_none(mirror, bars):
    assert _roles(fx.equal_lows(mirror=mirror).iloc[:bars], mirror) == dict.fromkeys(roles.ROLE_KEYS)
    assert roles.role_features(None, "bullish", {}, {}) == dict.fromkeys(roles.ROLE_KEYS)


@MIRRORS
def test_on_real_dicts_the_flags_follow_the_v121_and_liquidity_keys(mirror):
    df, direction = fx.equal_lows(mirror=mirror, **fx.REJECTION), fx.side(mirror)
    structure = structure_features(df, direction)
    liquidity = liquidity_features(df, direction, fx.m(95.0, mirror), fx.m(120.0, mirror))
    out = roles.role_features(df, direction, structure, liquidity)
    assert out["role_context"] is (structure["structure_aligned"] is True)
    assert (out["role_location"], out["role_path"], out["role_trigger"]) == (True, True, True)
    assert out["role_coverage"] == 3 + int(out["role_context"])


@MIRRORS
def test_every_value_is_a_plain_json_type(mirror):
    """The snapshot is stored as JSONB: no numpy scalar may leak out."""
    out = _roles(fx.equal_lows(mirror=mirror, **fx.REJECTION), mirror)
    assert json.loads(json.dumps(out)) == out
    assert [type(out[flag]) for flag in roles.ROLE_FLAGS] == [bool] * 4 and type(out["role_coverage"]) is int


def _assert_every_cut_matches(df, direction, start=roles.MIN_BARS - 1):
    """role_features on df.iloc[:t + 1] == flags_at row t of the FULL frame's arrays."""
    bars, atr_arr = reaction.Bars.from_frame(df), atr(df, 14).to_numpy(dtype=float)
    levels = confirmed_pivots(df)["last_sl" if direction == "bullish" else "last_sh"].to_numpy(dtype=float)
    structure = {"structure_aligned": True, "swing_low_atr": 1.0, "swing_high_atr": 1.0}
    seen = set()
    for t in range(start, len(df)):
        expected = roles.flags_at(bars, atr_arr, t, levels[t], direction, structure, NO_POOLS)
        assert roles.role_features(df.iloc[:t + 1], direction, structure, NO_POOLS) == expected, t
        seen.add(expected["role_trigger"])
    return seen


@MIRRORS
@pytest.mark.parametrize("spec", [fx.REJECTION, fx.RECLAIM, fx.FOLLOW_THROUGH, fx.THIRD_BAR],
                         ids=["rejection", "reclaim", "follow-through", "third-bar"])
def test_truncation_equality_at_every_cut_of_the_fixtures(spec, mirror):
    _assert_every_cut_matches(fx.equal_lows(mirror=mirror, **spec), fx.side(mirror))


@pytest.mark.slow
@pytest.mark.parametrize("direction", ["bullish", "bearish"])
def test_truncation_equality_at_every_cut_of_a_real_symbol(direction):
    df = pd.read_csv(TSLA, index_col="Date", parse_dates=True).iloc[:400]
    assert _assert_every_cut_matches(df, direction) == {True, False}     # both outcomes occur: not vacuous
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/market/test_roles.py`
Expected: FAIL at collection with `ImportError: cannot import name 'roles' from 'swingbot.core.market'`.

- [ ] **Step 3: Write the implementation**

`swingbot/core/market/roles.py`:

```python
"""Four-role coverage flags at the entry bar (v133).

One pass / fail / unknown flag per KIND of evidence -- context (v121
structure), location (discount or premium inside the last k=3 swing range),
path (stop-side liquidity) and trigger (a v88 reaction on the entry bar) --
and their count. The 12 level families all vote on location; this records
whether a setup has evidence of the other kinds too. Descriptive only:
nothing gates on it.

``role_features`` takes the already-computed v121 and liquidity dicts and
reads bars only for the trigger. NO-LOOKAHEAD: ``flags_at`` at bar ``t``
indexes its arrays at ``t`` and earlier only. Frozen constants, no config,
no I/O.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from swingbot.core.market import reaction
from swingbot.core.market.indicators import atr
from swingbot.core.market.structure import MIN_BARS, PIVOT_K, confirmed_pivots

PATH_NEAR_ATR = 1.0            # a stop-side pool nearer than this is "in the way"
PATH_SWEEP_RECENT_BARS = 5     # a stop-side sweep this recent clears the path
TRIGGER_TEST_K = 0.25          # reaction.is_test tolerance, in ATR
ROLE_FLAGS = ("role_context", "role_location", "role_path", "role_trigger")
ROLE_KEYS = ROLE_FLAGS + ("role_coverage",)
TRIGGER_KINDS = (reaction.R1, reaction.R3)   # R2 (follow-through) is left out on purpose


def _context(structure: dict) -> bool | None:
    aligned = structure.get("structure_aligned")
    return None if aligned is None else bool(aligned)


def _location(structure: dict, bullish: bool) -> bool | None:
    """Close inside the last k=3 swing range, in its discount (bullish) or premium (bearish) half."""
    low, high = structure.get("swing_low_atr"), structure.get("swing_high_atr")
    if low is None or high is None:
        return None
    return bool(low > 0 and high > 0 and (low <= high if bullish else high <= low))


def _path(liquidity: dict, atr_t: float) -> bool | None:
    if not (np.isfinite(atr_t) and atr_t > 0):
        return None
    near, swept = liquidity.get("liq_stop_side_atr"), liquidity.get("liq_sweep_bars_ago")
    clear = near is None or near > PATH_NEAR_ATR
    return bool(clear or (swept is not None and swept <= PATH_SWEEP_RECENT_BARS))


def _trigger(bars: reaction.Bars, atr_arr: np.ndarray, t: int, level, direction: str) -> bool | None:
    """R1 or R3 on bar ``t`` against ``level``; None when there is no level."""
    if level is None or not math.isfinite(level):
        return None
    tested_now = reaction.is_test(bars, t, level, direction, TRIGGER_TEST_K, atr_arr[t])
    tested_prev = reaction.is_test(bars, t - 1, level, direction, TRIGGER_TEST_K, atr_arr[t - 1])
    kind = reaction.reaction_kind(bars, t, level, direction, tested_now=tested_now,
                                  tested_prev=tested_prev, floor_index=t - reaction.RECLAIM_BARS)
    return kind in TRIGGER_KINDS


def flags_at(bars: reaction.Bars, atr_arr: np.ndarray, t: int, level, direction: str,
             structure: dict, liquidity: dict) -> dict:
    """Every ROLE_KEYS value at bar ``t`` of arrays that may extend past ``t``.
    ``level`` is the last confirmed k=3 swing low (bearish: swing high) known at ``t``."""
    flags = {"role_context": _context(structure),
             "role_location": _location(structure, direction == "bullish"),
             "role_path": _path(liquidity, atr_arr[t]),
             "role_trigger": _trigger(bars, atr_arr, t, level, direction)}
    known = all(value is not None for value in flags.values())
    return {**flags, "role_coverage": sum(1 for value in flags.values() if value) if known else None}


def role_features(df: pd.DataFrame, direction: str, structure: dict, liquidity: dict) -> dict:
    """Every ROLE_KEYS value at ``df``'s final bar. ``structure`` is
    ``structure_features(df, direction)`` and ``liquidity`` is
    ``liquidity_features(df, direction, stop, target)``, both for this same
    frame. Fewer than 60 bars (or no frame) returns all None."""
    if df is None or len(df) < MIN_BARS:
        return dict.fromkeys(ROLE_KEYS)
    column = "last_sl" if direction == "bullish" else "last_sh"
    level = float(confirmed_pivots(df, PIVOT_K)[column].iloc[-1])
    return flags_at(reaction.Bars.from_frame(df), atr(df, 14).to_numpy(dtype=float), len(df) - 1,
                    level, direction, structure, liquidity)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/market/test_roles.py`
Expected: `0 failed`.

- [ ] **Step 5: Complexity**

Run: `python -m radon cc -s -n C swingbot/core/market/roles.py`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/market/roles.py tests/market/test_roles.py
git commit -m "feat(v133): four role flags and role_coverage from the v121 and liquidity dicts"
```

### Task V133-5: Snapshot merge — ten keys on `entry_context`

**Files:**
- Modify: `swingbot/core/edge/context.py` (`FEATURE_KEYS`; one helper; two lines inside `entry_context`)
- Create: `tests/edge/context_witness.py`, `tests/fixtures/v133/entry_context_witness.json` (generated in Step 1), `tests/edge/test_edge_context_roles.py`
- Modify: `tests/edge/test_edge_context_location.py:57-58`
- Modify: `tests/backtesting/instrument/golden.py` (`golden_records`: assert-and-drop the ten new context keys, Step 6)

**Interfaces:**
- Consumes: `liquidity_features(df, direction, stop, target)` and `LIQUIDITY_KEYS` (V133-2); `role_features(df, direction, structure, liquidity)` and `ROLE_KEYS` (V133-4); `structure_features(df, direction)`; `entry_context(df, *, direction, horizon_key, stop, target, asof=None, entry=None)`.
- Produces: `FEATURE_KEYS` ending in the ten keys `LIQUIDITY_KEYS + ROLE_KEYS`. `planning/params.py:stamp_entry_context` (live) and `backtesting/backtest.py` / `backtest_scenarios.py` (replay) gain them with no edit: all three already pass `stop` and `target`.

**Do not run this task beside v130's V130-4 in the same tree** (both edit `FEATURE_KEYS`). `entry_context` is `C (17)`: the edit below adds no branch.

- [ ] **Step 1: Capture the witness before touching `context.py`**

Confirm the file is untouched (`git diff --stat -- swingbot/core/edge/context.py` prints nothing), then create `tests/edge/context_witness.py`:

```python
"""v133 witness: every entry_context value that existed before the liquidity / role merge."""
import json
from pathlib import Path

from swingbot.core.edge.context import entry_context
from tests.market.structure_fixtures import wavy_frame

PATH = Path(__file__).resolve().parents[1] / "fixtures" / "v133" / "entry_context_witness.json"
ASOF = {"regime2_state": "bull_quiet", "rs_pctile": 64.0, "sector_pctile": None, "rs_combined": 61.0}
DIRECTIONS = ("bullish", "bearish")


def snapshot(direction: str) -> dict:
    df = wavy_frame()
    close = float(df["Close"].iloc[-1])
    sign = 1 if direction == "bullish" else -1
    return entry_context(df, direction=direction, horizon_key="2w", stop=close - sign * 6.0,
                         target=close + sign * 12.0, asof=ASOF, entry=close)


def write() -> None:
    """Run ONCE, before context.py is edited. Never regenerate it to make a test pass."""
    PATH.parent.mkdir(parents=True, exist_ok=True)
    PATH.write_text(json.dumps({direction: snapshot(direction) for direction in DIRECTIONS},
                               indent=1, sort_keys=True), encoding="utf-8")
```

Run: `python -c "from tests.edge.context_witness import write; write()"`
Then: `python -c "import json; b = json.load(open('tests/fixtures/v133/entry_context_witness.json')); print({d: len(v) for d, v in b.items()})"`
Expected: `{'bullish': 43, 'bearish': 43}` (51 each if v130 landed first). Commit the witness alone, so its provenance is a commit that predates the merge:

```bash
git add tests/edge/context_witness.py tests/fixtures/v133/entry_context_witness.json
git commit -m "test(v133): witness every entry_context value before the liquidity/role merge"
```

- [ ] **Step 2: Write the failing tests**

`tests/edge/test_edge_context_roles.py`:

```python
"""v133: entry_context carries five liquidity keys and five role keys; nothing older moved."""
import json
from types import SimpleNamespace

import pytest

from swingbot.core.edge.context import FEATURE_KEYS, entry_context
from swingbot.core.market.liquidity import LIQUIDITY_KEYS, liquidity_features
from swingbot.core.market.roles import ROLE_KEYS, role_features
from swingbot.core.market.structure import structure_features
from tests.edge.context_witness import ASOF, DIRECTIONS, PATH, snapshot
from tests.market import liquidity_fixtures as fx

V133_NEW = ("liq_stop_side_atr", "liq_target_side_atr", "liq_sweep_bars_ago", "stop_in_pool", "target_past_pool",
            "role_context", "role_location", "role_path", "role_trigger", "role_coverage")
WITNESS = json.loads(PATH.read_text(encoding="utf-8"))
MIRRORS = pytest.mark.parametrize("mirror", [False, True], ids=["bullish", "bearish"])


def _context(df, mirror, *, stop=98.8, target=125.0):
    return entry_context(df, direction=fx.side(mirror), horizon_key="2w", stop=fx.m(stop, mirror),
                         target=fx.m(target, mirror), asof=None)


def test_feature_keys_end_with_the_ten_v133_keys_in_order():
    assert FEATURE_KEYS[-10:] == V133_NEW == LIQUIDITY_KEYS + ROLE_KEYS
    assert len(set(FEATURE_KEYS)) == len(FEATURE_KEYS)                       # nothing duplicated
    assert set(FEATURE_KEYS[:-10]) == set(WITNESS["bullish"])               # nothing older added or dropped


@pytest.mark.parametrize("direction", DIRECTIONS)
def test_every_pre_existing_key_is_byte_identical(direction):
    out = snapshot(direction)
    kept = {key: out[key] for key in WITNESS[direction]}
    assert json.dumps(kept, sort_keys=True) == json.dumps(WITNESS[direction], sort_keys=True)
    assert not set(WITNESS[direction]) & set(V133_NEW)


@MIRRORS
def test_snapshot_carries_the_liquidity_and_role_features(mirror):
    df, direction = fx.two_sided(mirror=mirror), fx.side(mirror)
    out = _context(df, mirror)
    assert set(out) == set(FEATURE_KEYS)
    liquidity = liquidity_features(df, direction, fx.m(98.8, mirror), fx.m(125.0, mirror))
    assert {key: out[key] for key in LIQUIDITY_KEYS} == liquidity
    assert {key: out[key] for key in ROLE_KEYS} == role_features(df, direction,
                                                                 structure_features(df, direction), liquidity)
    assert out["liq_stop_side_atr"] == pytest.approx(5.5) and out["stop_in_pool"] is True     # not a vacuous pass
    assert out["target_past_pool"] is True and out["role_coverage"] == 2


@MIRRORS
def test_the_roles_read_the_same_v121_values_the_snapshot_stores(mirror):
    out = _context(fx.two_sided(mirror=mirror), mirror)
    near, far = (out["swing_high_atr"], out["swing_low_atr"]) if mirror else (out["swing_low_atr"], out["swing_high_atr"])
    assert out["role_location"] is (near > 0 and far > 0 and near <= far)
    assert out["role_context"] is out["structure_aligned"]


@MIRRORS
@pytest.mark.parametrize("bars", [10, 40, 59])
def test_frames_under_60_bars_leave_every_new_key_none(mirror, bars):
    out = _context(fx.two_sided(mirror=mirror).iloc[:bars], mirror)
    assert set(out) == set(FEATURE_KEYS)
    assert all(out[key] is None for key in V133_NEW)


def test_the_whole_snapshot_is_json_serialisable():
    out = _context(fx.equal_lows(**fx.THIRD_BAR), False)
    assert json.loads(json.dumps(out)) == out


def test_live_stamp_carries_the_new_keys():
    from swingbot.core.planning.params import stamp_entry_context
    df = fx.two_sided(mirror=True)
    plan = SimpleNamespace(direction="bearish", horizon_key="2w", stop_loss=fx.m(98.8), tp1=fx.m(125.0),
                           entry_context=None)
    stamp_entry_context(plan, df, ASOF)
    assert set(plan.entry_context) == set(FEATURE_KEYS)
    assert plan.entry_context["stop_in_pool"] is True and plan.entry_context["role_path"] is True
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/edge/test_edge_context_roles.py`
Expected: FAIL. `test_feature_keys_end_with_the_ten_v133_keys_in_order` fails on the tuple comparison and `test_snapshot_carries_the_liquidity_and_role_features` on `KeyError: 'liq_stop_side_atr'`. `test_every_pre_existing_key_is_byte_identical` already passes: that is the witness doing its job.

- [ ] **Step 4: Write the implementation**

In `swingbot/core/edge/context.py`:

(a) Add two imports beside the existing `market` imports, keeping them alphabetical:

```python
from swingbot.core.market.liquidity import liquidity_features
from swingbot.core.market.location import location_features
from swingbot.core.market.roles import role_features
from swingbot.core.market.structure import structure_features
```

(b) Extend the end of the `FEATURE_KEYS` tuple. The current last entries are the v125 line; add the v133 comment and two lines after it:

```python
                # v125: plan provenance (plan_provenance) and location / leg / zone (market/location.py)
                "target_capped", "stop_clamped", "zone_dist_atr", "room_atr", "range_pos", "leg_phase",
                "zone_state", "zone_touches", "zone_departure_atr",
                # v133: liquidity pools (market/liquidity.py) and four-role coverage (market/roles.py)
                "liq_stop_side_atr", "liq_target_side_atr", "liq_sweep_bars_ago", "stop_in_pool",
                "target_past_pool", "role_context", "role_location", "role_path", "role_trigger", "role_coverage")
```

If v130 landed first its eight keys sit between the v125 and v133 lines; leave them where they are and append v133's after them.

(c) Add this helper directly above `def entry_context`:

```python
def _liquidity_and_roles(df, direction: str, stop, target, structure: dict) -> dict:
    """v133: the five liquidity keys and the five role keys. Both functions return
    all None below 60 bars and never raise. ``structure`` is the v121 dict already
    computed for this frame, so nothing is computed twice."""
    liquidity = liquidity_features(df, direction, stop, target)
    return {**liquidity, **role_features(df, direction, structure, liquidity)}
```

(d) Inside `entry_context`, replace the single line

```python
    out.update(structure_features(df, direction))   # v121; all None below 60 bars
```

with

```python
    structure = structure_features(df, direction)   # v121; all None below 60 bars
    out.update(structure)
```

and add one line directly after the existing `out.update(location_features(df, direction, horizon_key))` line:

```python
    out.update(_liquidity_and_roles(df, direction, stop, target, structure))   # v133; all None below 60 bars
```

No `if`, no `try`: the early `return out` for frames under 20 bars already leaves every key `None`, and both new functions guard 20–59 bars themselves.

(e) In `tests/edge/test_edge_context_location.py`, replace lines 57–58

```python
    assert len(FEATURE_KEYS) == 43
    assert FEATURE_KEYS[34:] == V125_NEW
```

with

```python
    assert len(FEATURE_KEYS) >= 43
    assert FEATURE_KEYS[34:43] == V125_NEW
```

(If v130 already made this edit, leave it.) No v125 behaviour changes.

- [ ] **Step 5: Run the tests to verify they pass**

Run each, expecting `0 failed`:

```bash
python scripts/dev/testrun.py file tests/edge/test_edge_context_roles.py
python scripts/dev/testrun.py file tests/edge/test_edge_context_location.py
python scripts/dev/testrun.py file tests/edge/test_edge_context_structure.py
python scripts/dev/testrun.py file tests/backtesting/test_backtest_context.py
python scripts/dev/testrun.py file tests/backtesting/test_replay_context.py
```

The last two prove both replay paths stamp the ten keys with no new wiring (`set(context) == set(FEATURE_KEYS)`).

- [ ] **Step 6: Keep the v1 instrument golden byte-identical**

Every replay trade's `context` now carries ten more keys, so `tests/backtesting/instrument/test_v1_golden.py` would go red. The golden fixture `tests/fixtures/instrument/v1_golden.jsonl` carries exactly the 43 pre-v133 `FEATURE_KEYS` in each trade's `context` and **must NOT be regenerated** (regenerating it is a cutover decision, not a fix). Instead, in `tests/backtesting/instrument/golden.py:golden_records`, follow the v131 `limit_orders` precedent: for each trade whose `trade["context"]` is truthy, assert every key of `(*LIQUIDITY_KEYS, *ROLE_KEYS)` is present, then drop them before yielding:

```python
from swingbot.core.market.liquidity import LIQUIDITY_KEYS  # noqa: E402
from swingbot.core.market.roles import ROLE_KEYS  # noqa: E402

V133_CONTEXT_KEYS = (*LIQUIDITY_KEYS, *ROLE_KEYS)
...
            for k, trade in enumerate(trades):
                context = trade.get("context")
                if context:
                    # v133 fields: present on every stamped trade, kept out of the golden bytes.
                    assert all(key in context for key in V133_CONTEXT_KEYS)
                    for key in V133_CONTEXT_KEYS:
                        del context[key]
                yield {"case": case, "trade": k, "row": trade}
```

v157 FC6 also edits `golden_records` (it drops `signal_date`). If that edit is already there, keep it and add this one beside it; whichever lands second rebases onto the other — keep both.

Run: `python scripts/dev/testrun.py file tests/backtesting/instrument/test_v1_golden.py`
Expected: `0 failed`.

- [ ] **Step 7: Complexity**

Run: `python -m radon cc -s -n C swingbot/core/edge/context.py`
Expected: exactly one line, `entry_context - C (17)` (pre-existing, unchanged). A higher number means a branch was added: remove it.

- [ ] **Step 8: Commit**

```bash
git add swingbot/core/edge/context.py tests/edge/test_edge_context_roles.py tests/edge/test_edge_context_location.py tests/backtesting/instrument/golden.py
git commit -m "feat(v133): entry_context carries five liquidity keys and five role keys"
```
