# v128 FVG lift audit, Part 1: signal code (V128-1 .. V128-3)

> Header, Global Constraints, Review Focus, the spec-assumption table (A1–A12), the file map and `## Parallelisation` live in `2026-10-02-v128-fvg-displacement-audit_0-index.md`. Every task here implicitly includes those constraints. Work in the worktree `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-02-v128-fvg-displacement-audit`; all paths below are relative to it.

# Phase 1 — Signal code (inert at default)

### Task V128-1: Displacement predicate and mode filter in `fvg.py`

**Files:**
- Create: `tests/market/fvg_frames.py` (shared hand-built frames; no `test_` prefix, so pytest does not collect it)
- Create: `tests/fixtures/v128/fvg_all_witness.json` (captured on the **unchanged** `fvg.py`)
- Create: `tests/market/test_fvg_displacement.py`
- Modify: `swingbot/core/market/fvg.py`

**Interfaces:**
- Consumes: `indicators.atr(df, period=14) -> pd.Series` (Wilder EWM, `min_periods=period`; the value at row `m` reads rows `≤ m` only). `fvg.find_fair_value_gaps_detailed(df, lookback, max_per_side) -> list[dict]` with keys `bottom, top, mid, bar_index, direction`.
- Produces (`swingbot.core.market.fvg`):
  - `FVG_MODES: tuple[str, ...] = ("all", "displacement", "off")`
  - `DEFAULT_DISPLACEMENT_ATR_K: float = 1.5`, `DISPLACEMENT_ATR_PERIOD: int = 14`
  - `is_displacement_gap(df, gap: dict, k: float, atr_series: pd.Series | None = None) -> bool`
  - `filter_gaps(df, gaps: list[dict], mode: str = "all", k: float = 1.5) -> list[dict]`: returns the **same dict objects** it keeps (V128-5 relies on identity). Raises `ValueError("unknown FVG mode ...")` on an unknown mode.
  - `find_fair_value_gaps(df, lookback=LOOKBACK_BARS, max_per_side=MAX_GAPS_PER_SIDE, mode="all", k=DEFAULT_DISPLACEMENT_ATR_K) -> list[tuple[float, str]]`. With `mode="all"` the output equals today's.
- `tests/market/fvg_frames.py` produces `bar_frame(bars)`, `gap_frame(middle, third, flat_bars=20)`, `witness_frame(n=260, seed=126)` and the candle constants below. V128-3 and V128-5 import them.

- [ ] **Step 0: Create the worktree** (skip if it exists)

Invoke the `worktree-lifecycle` skill, then:

```bash
git -C E:/Documents/Private/Projects/Discord-Bot worktree add .claude/worktrees/2026-10-02-v128-fvg-displacement-audit -b 2026-10-02-v128-fvg-displacement-audit main
```

All later commands in this plan run from that worktree.

- [ ] **Step 1: Invoke the `no-lookahead` skill.** The displacement rule decides what a bar knew.

- [ ] **Step 2: Write the frame helpers**

```python
# tests/market/fvg_frames.py
"""Hand-built OHLC frames for the v128 FVG tests. No test_ prefix: not collected.

Every hand-built frame is `flat_bars` identical candles (O=C=100, H=101, L=99:
true range 2.0, so ATR14 settles at exactly 2.0), then a middle candle `m`,
then a third candle `i = m + 1` that opens a gap against candle `m - 1`.
The ATR figures in the comments are Wilder's EWM: ATR[m] = 2.0 * 13/14 + TR[m]/14.
"""
import numpy as np
import pandas as pd

FLAT = (100.0, 101.0, 99.0, 100.0)            # Open, High, Low, Close

STRONG_BULL = (100.0, 104.2, 99.8, 104.0)     # TR 4.4 -> ATR14 2.1714; body 4.0; close at 95% of range
WEAK_BULL = (100.0, 101.6, 99.9, 101.5)       # TR 1.7 -> ATR14 1.9786; body 1.5 < 1.5 x 1.9786
MID_CLOSE_BULL = (97.0, 106.0, 96.9, 101.0)   # TR 9.1 -> ATR14 2.5071; body 4.0 >= 3.76, close at 45% of range
UP_CLOSE_BIG = (96.0, 100.2, 95.8, 100.0)     # TR 4.4 -> ATR14 2.1714; body 4.0, close at 95% of range
STRONG_BEAR = (100.0, 100.2, 95.8, 96.0)      # TR 4.4 -> ATR14 2.1714; body 4.0, close at 5% of range

BULL_THIRD = (104.0, 105.0, 101.5, 104.5)     # Low 101.5 > flat High 101.0: bullish gap 101.0..101.5, mid 101.25
BEAR_THIRD = (96.0, 98.5, 95.0, 96.5)         # High 98.5 < flat Low 99.0: bearish gap 98.5..99.0, mid 98.75


def bar_frame(bars) -> pd.DataFrame:
    index = pd.bdate_range("2024-01-01", periods=len(bars))
    frame = pd.DataFrame(list(bars), columns=["Open", "High", "Low", "Close"], index=index)
    frame["Volume"] = 1_000_000.0
    return frame


def gap_frame(middle, third, flat_bars: int = 20) -> pd.DataFrame:
    return bar_frame([FLAT] * flat_bars + [middle, third])


def witness_frame(n: int = 260, seed: int = 126) -> pd.DataFrame:
    """A seeded random walk with ~6% jump days, so it carries unfilled gaps of both kinds."""
    rng = np.random.default_rng(seed)
    steps = rng.normal(0.0, 0.012, n)
    jumps = np.where(rng.random(n) < 0.06, rng.choice([-0.04, 0.04], n), 0.0)
    close = 100.0 * np.exp(np.cumsum(steps + jumps))
    open_ = np.r_[close[0], close[:-1]]
    spread = np.abs(rng.normal(0.0, 0.006, n)) * close
    high = np.maximum(open_, close) + spread
    low = np.minimum(open_, close) - spread
    return bar_frame(zip(open_, high, low, close))
```

- [ ] **Step 3: Capture the characterisation witness on the UNCHANGED `fvg.py`**

```bash
python - <<'EOF'
import json, pathlib
from tests.market.fvg_frames import witness_frame
from swingbot.core.market.fvg import find_fair_value_gaps
gaps = find_fair_value_gaps(witness_frame())
assert gaps, "witness frame must carry at least one unfilled gap"
out = pathlib.Path("tests/fixtures/v128/fvg_all_witness.json")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps([[p, s] for p, s in gaps], indent=1), encoding="utf-8")
print(len(gaps), gaps)
EOF
git diff --quiet -- swingbot/core/market/fvg.py && echo "fvg.py untouched -- witness is pre-change"
```

Expected: a non-empty list is printed, followed by `fvg.py untouched -- witness is pre-change`. If the list is empty, change `seed` in `witness_frame` and recapture. Do not edit `fvg.py` first.

- [ ] **Step 4: Write the failing tests**

```python
# tests/market/test_fvg_displacement.py
"""v128: the causal displacement predicate and the FVG mode filter."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from swingbot.core.market import fvg
from swingbot.core.market.indicators import atr
from tests.market.fvg_frames import (BEAR_THIRD, BULL_THIRD, MID_CLOSE_BULL, STRONG_BEAR, STRONG_BULL,
                                     UP_CLOSE_BIG, WEAK_BULL, bar_frame, gap_frame, witness_frame)

WITNESS = Path(__file__).resolve().parents[1] / "fixtures" / "v128" / "fvg_all_witness.json"


def _only_gap(frame):
    gaps = fvg.find_fair_value_gaps_detailed(frame)
    assert len(gaps) == 1, gaps
    return gaps[0]


def test_strong_bullish_body_closing_in_the_top_third_is_displacement():
    frame = gap_frame(STRONG_BULL, BULL_THIRD)
    assert fvg.is_displacement_gap(frame, _only_gap(frame), 1.5) is True


def test_body_below_k_atr_is_not_displacement():
    frame = gap_frame(WEAK_BULL, BULL_THIRD)
    assert fvg.is_displacement_gap(frame, _only_gap(frame), 1.5) is False


def test_k_is_the_body_threshold():
    frame = gap_frame(STRONG_BULL, BULL_THIRD)
    gap = _only_gap(frame)
    assert fvg.is_displacement_gap(frame, gap, 1.0) is True
    assert fvg.is_displacement_gap(frame, gap, 2.0) is False       # 2.0 x 2.1714 = 4.34 > body 4.0


def test_close_outside_the_extreme_third_is_not_displacement():
    frame = gap_frame(MID_CLOSE_BULL, BULL_THIRD)
    assert fvg.is_displacement_gap(frame, _only_gap(frame), 1.5) is False


def test_bearish_mirror():
    frame = gap_frame(STRONG_BEAR, BEAR_THIRD)
    gap = _only_gap(frame)
    assert gap["direction"] == "bearish"
    assert fvg.is_displacement_gap(frame, gap, 1.5) is True


def test_bearish_gap_needs_the_close_in_the_bottom_third():
    frame = gap_frame(UP_CLOSE_BIG, BEAR_THIRD)
    gap = _only_gap(frame)
    assert gap["direction"] == "bearish"
    assert fvg.is_displacement_gap(frame, gap, 1.5) is False


@pytest.mark.parametrize("atr_value", [np.nan, 0.0, -1.0, np.inf])
def test_non_finite_or_non_positive_atr_is_not_displacement(atr_value):
    frame = gap_frame(STRONG_BULL, BULL_THIRD)
    series = pd.Series(atr_value, index=frame.index)
    assert fvg.is_displacement_gap(frame, _only_gap(frame), 1.5, atr_series=series) is False


def test_too_little_history_for_atr14_is_not_displacement():
    frame = gap_frame(STRONG_BULL, BULL_THIRD, flat_bars=3)      # ATR14 is still NaN at the middle candle
    assert fvg.is_displacement_gap(frame, _only_gap(frame), 1.5) is False


def test_appending_future_bars_never_changes_the_verdict():
    frame = gap_frame(STRONG_BULL, BULL_THIRD)
    gap = _only_gap(frame)
    violent = [(104.5, 130.0, 102.0, 128.0), (128.0, 129.0, 60.0, 61.0)] * 5
    extended = bar_frame(list(frame[["Open", "High", "Low", "Close"]].itertuples(index=False, name=None)) + violent)
    for k in (1.0, 1.5, 2.0):
        assert fvg.is_displacement_gap(extended, gap, k) == fvg.is_displacement_gap(frame, gap, k)
    assert fvg.is_displacement_gap(extended, gap, 1.5, atr_series=atr(extended, 14)) is True


def test_mode_all_matches_the_pre_change_witness():
    expected = [tuple(row) for row in json.loads(WITNESS.read_text(encoding="utf-8"))]
    assert fvg.find_fair_value_gaps(witness_frame()) == expected
    assert fvg.find_fair_value_gaps(witness_frame(), mode="all", k=2.0) == expected


def test_mode_off_returns_nothing():
    assert fvg.find_fair_value_gaps(witness_frame(), mode="off") == []


@pytest.mark.parametrize("k", [1.0, 1.5, 2.0])
def test_displacement_is_a_subset_of_all(k):
    everything = fvg.find_fair_value_gaps(witness_frame())
    kept = fvg.find_fair_value_gaps(witness_frame(), mode="displacement", k=k)
    assert all(item in everything for item in kept)


def test_displacement_filters_on_the_hand_built_frames():
    strong = fvg.find_fair_value_gaps(gap_frame(STRONG_BULL, BULL_THIRD), mode="displacement", k=1.5)
    weak = fvg.find_fair_value_gaps(gap_frame(WEAK_BULL, BULL_THIRD), mode="displacement", k=1.5)
    assert (strong, weak) == ([(101.25, "FVG (bullish)")], [])


def test_filter_gaps_keeps_the_same_dict_objects():
    frame = gap_frame(STRONG_BULL, BULL_THIRD)
    gaps = fvg.find_fair_value_gaps_detailed(frame)
    assert fvg.filter_gaps(frame, gaps, "displacement", 1.5)[0] is gaps[0]
    assert fvg.filter_gaps(frame, gaps, "all")[0] is gaps[0]


def test_unknown_mode_raises():
    with pytest.raises(ValueError, match="unknown FVG mode"):
        fvg.find_fair_value_gaps(witness_frame(), mode="sideways")


def test_detailed_output_is_unchanged_so_charts_keep_every_gap():
    assert len(fvg.find_fair_value_gaps_detailed(gap_frame(WEAK_BULL, BULL_THIRD))) == 1
```

- [ ] **Step 5: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/market/test_fvg_displacement.py`
Expected: FAIL. The new tests fail with `AttributeError: module 'swingbot.core.market.fvg' has no attribute 'is_displacement_gap'` and `TypeError: ... unexpected keyword argument 'mode'`. `test_mode_all_matches_the_pre_change_witness` fails only at its second assert (`mode=`).

- [ ] **Step 6: Implement**

In `swingbot/core/market/fvg.py`, replace the import line `import pandas as pd` with:

```python
import math

import pandas as pd

from swingbot.core.market.indicators import atr
```

After `MAX_GAPS_PER_SIDE = 3`, add:

```python
# v128 (docs/superpowers/specs/2026-10-02-v128-fvg-displacement-audit-design.md).
# Which unfilled gaps reach levels.py: every one ("all", the pre-v128
# behaviour), only displacement gaps, or none. The filter runs AFTER
# find_fair_value_gaps_detailed's freshest-3-per-side truncation, so
# "displacement" is always a subset of "all" -- it never reaches back for an
# older displacement gap. Charts call find_fair_value_gaps_detailed and are
# unaffected by the mode.
FVG_MODES = ("all", "displacement", "off")
DEFAULT_DISPLACEMENT_ATR_K = 1.5
DISPLACEMENT_ATR_PERIOD = 14


def _check_mode(mode: str) -> None:
    if mode not in FVG_MODES:
        raise ValueError(f"unknown FVG mode {mode!r}; expected one of {FVG_MODES}")


def _atr_at(df: pd.DataFrame, m: int, atr_series) -> float:
    """ATR14 at row m. Wilder's EWM is recursive, so the value at m reads rows <= m only."""
    series = atr(df.iloc[:m + 1], DISPLACEMENT_ATR_PERIOD) if atr_series is None else atr_series
    return float(series.iloc[m])


def _closes_in_gap_third(direction: str, close: float, high: float, low: float) -> bool:
    span = high - low
    if direction == "bullish":
        return close >= low + (2.0 / 3.0) * span
    return close <= low + (1.0 / 3.0) * span


def is_displacement_gap(df: pd.DataFrame, gap: dict, k: float, atr_series=None) -> bool:
    """True iff the gap's MIDDLE candle m = bar_index - 1 is a displacement candle:
    |Close[m] - Open[m]| >= k * ATR14[m], and the close sits in the gap-side third
    of the candle's range (top third for a bullish gap, bottom third for a
    bearish one). A non-finite or non-positive ATR14[m] is never displacement.

    Causal: reads row m and earlier only. The gap itself needs bar m + 1 closed,
    so this never reads a bar the gap's existence did not already need, and
    appending later bars cannot change the verdict. `atr_series`, when given,
    must be indicators.atr(df, 14) over the same frame (filter_gaps passes it
    to avoid one ATR per gap)."""
    m = int(gap["bar_index"]) - 1
    if m < 0 or m >= len(df):
        return False
    atr_m = _atr_at(df, m, atr_series)
    if not math.isfinite(atr_m) or atr_m <= 0:
        return False
    row = df.iloc[m]
    open_, high, low, close = (float(row[col]) for col in ("Open", "High", "Low", "Close"))
    if abs(close - open_) < k * atr_m:
        return False
    return _closes_in_gap_third(gap["direction"], close, high, low)


def filter_gaps(df: pd.DataFrame, gaps: list, mode: str = "all",
                k: float = DEFAULT_DISPLACEMENT_ATR_K) -> list:
    """The gaps `mode` keeps, as the same dict objects (never copies)."""
    _check_mode(mode)
    if mode == "all":
        return list(gaps)
    if mode == "off" or not gaps:
        return []
    atr_series = atr(df, DISPLACEMENT_ATR_PERIOD)
    return [gap for gap in gaps if is_displacement_gap(df, gap, k, atr_series)]
```

Replace the whole `find_fair_value_gaps` function with:

```python
def find_fair_value_gaps(df: pd.DataFrame, lookback: int = LOOKBACK_BARS,
                          max_per_side: int = MAX_GAPS_PER_SIDE, mode: str = "all",
                          k: float = DEFAULT_DISPLACEMENT_ATR_K) -> list:
    """
    Scans the last `lookback` bars for 3-candle Fair Value Gaps and
    returns the still-UNFILLED ones as (price, source_label) candidates
    in the exact shape every other levels.py method produces. Thin
    wrapper around find_fair_value_gaps_detailed() -- see that function
    for the full gap geometry (needed by trade_chart.py to draw the
    zone, not just its midpoint).

    `mode`/`k` (v128): "all" (default) returns every unfilled gap exactly
    as before; "displacement" keeps only is_displacement_gap(..., k) gaps;
    "off" returns []. See FVG_MODES.

    Never raises on data: too little data or a malformed frame just means
    no FVG candidates this round, same as every other method here failing
    silently. An unknown `mode` is a programming error and raises ValueError.
    """
    _check_mode(mode)
    gaps = filter_gaps(df, find_fair_value_gaps_detailed(df, lookback, max_per_side), mode, k)
    return [
        (g["mid"], "FVG (bullish)" if g["direction"] == "bullish" else "FVG (bearish)")
        for g in gaps if g["mid"] > 0
    ]
```

- [ ] **Step 7: Run the tests to verify they pass, then measure complexity**

Run: `python scripts/dev/testrun.py file tests/market/test_fvg_displacement.py`
Expected: PASS, `0 failed`.
Run: `python scripts/dev/testrun.py file tests/charts/test_chart_geometry.py`
Expected: PASS (charts still draw every gap).
Run: `python -m radon cc -s -n C swingbot/core/market/fvg.py`
Expected: no output.

- [ ] **Step 8: Commit**

```bash
git add swingbot/core/market/fvg.py tests/market/fvg_frames.py tests/market/test_fvg_displacement.py tests/fixtures/v128/fvg_all_witness.json
git commit -m "feat(v128): causal FVG displacement predicate and mode filter (default all, unchanged)"
```

### Task V128-2: The two knobs: config, `ScanParams`, reachability, `.env.example`

**Files:**
- Modify: `swingbot/config.py` (two `Field`s before `PYRAMIDING_ENABLED`; `_SEARCH_CLASSES["searchable"]`; `_MODE_VALUES`; new `_MODE_FALLBACK`, `_POSITIVE_FLOATS`, `_cast_mode`, `_cast_positive_float`; `_cast`; `import math`)
- Modify: `swingbot/scan_params.py` (two fields, `__post_init__` validation, `from_config`)
- Modify: `swingbot/core/backtesting/arms/reachability.py` (two `REGISTRY` entries)
- Modify: `.env.example` (two keys after `AVWAP_LEVELS_ENABLED=true`)
- Create: `tests/test_config_fvg_mode.py`

**Interfaces:**
- Consumes: `fvg.FVG_MODES` (V128-1), `knobs.parse_knob`, `reachability.Reach`/`REACHABLE`/`CS`.
- Produces: `config.FVG_LEVELS_MODE: str` (default `"all"`), `config.FVG_DISPLACEMENT_ATR_K: float` (default `1.5`), `ScanParams.fvg_levels_mode: str`, `ScanParams.fvg_displacement_atr_k: float`, `scan_params._FVG_MODES`. `ScanParams(...)` raises `ValueError` on an unknown mode, or on a `k` that is non-finite or ≤ 0. Both knobs are `REACHABLE`, `observed_by=CS`, `fixture_observable=False`.
- These must land together in one commit. `test_scan_params_coverage` (config ↔ `ScanParams`), `test_reachability`/`test_knob_observability` (searchable ↔ `REGISTRY`) and `test_env_example_sync` (`FIELDS` ↔ `.env.example`) each fail on any partial landing.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_config_fvg_mode.py
"""v128: FVG_LEVELS_MODE / FVG_DISPLACEMENT_ATR_K -- schema, validation, ScanParams, reachability."""
import dataclasses
import math

import pytest

from swingbot import config, scan_params
from swingbot.core.backtesting.arms import reachability as reach
from swingbot.core.backtesting.arms.knobs import parse_knob
from swingbot.core.market import fvg
from swingbot.scan_params import ScanParams


def _field(attr):
    return next(f for f in config.FIELDS if f.attr == attr)


def test_fvg_fields_exist_with_documented_defaults():
    mode, k = _field("FVG_LEVELS_MODE"), _field("FVG_DISPLACEMENT_ATR_K")
    assert (mode.type, mode.default, mode.search_class) == ("select", "all", "searchable")
    assert tuple(value for value, _ in mode.options) == fvg.FVG_MODES
    assert (k.type, k.default, k.search_class) == ("float", "1.5", "searchable")
    assert config._cast(mode, mode.default) == "all"
    assert config._cast(k, k.default) == 1.5


def test_unknown_mode_falls_back_to_all_never_off():
    field = _field("FVG_LEVELS_MODE")
    assert config._cast(field, "sideways") == "all"
    assert config._cast(field, "of") == "all"
    assert config._cast(field, "DISPLACEMENT") == "displacement"
    assert config._cast(field, "off") == "off"


def test_other_mode_fields_still_fall_back_to_off():
    assert config._cast(_field("PLAN_ENGINE_V2"), "banana") == "off"


@pytest.mark.parametrize("raw", ["0", "-1.5", "nan", "inf", "abc"])
def test_non_positive_or_non_numeric_k_is_a_parse_failure(raw):
    with pytest.raises(ValueError):
        config._cast(_field("FVG_DISPLACEMENT_ATR_K"), raw)


def test_env_with_bad_values_falls_back_to_the_defaults(monkeypatch):
    monkeypatch.setenv("FVG_DISPLACEMENT_ATR_K", "0")
    monkeypatch.setenv("FVG_LEVELS_MODE", "sideways")
    try:
        config._apply_env()
        assert config.FVG_DISPLACEMENT_ATR_K == 1.5
        assert config.FVG_LEVELS_MODE == "all"
    finally:
        monkeypatch.undo()
        config._apply_env()


@pytest.mark.parametrize("text", ["FVG_LEVELS_MODE=sideways", "FVG_DISPLACEMENT_ATR_K=0",
                                  "FVG_DISPLACEMENT_ATR_K=-1"])
def test_measure_arms_refuses_an_invalid_arm(text):
    with pytest.raises(ValueError):
        parse_knob(text)


def test_parse_knob_accepts_the_frozen_grid():
    assert parse_knob("FVG_LEVELS_MODE=off") == ("FVG_LEVELS_MODE", "off")
    assert parse_knob("FVG_LEVELS_MODE=displacement") == ("FVG_LEVELS_MODE", "displacement")
    for k in (1.0, 1.5, 2.0):
        assert parse_knob(f"FVG_DISPLACEMENT_ATR_K={k}") == ("FVG_DISPLACEMENT_ATR_K", k)


def test_scan_params_carry_the_two_fields():
    params = ScanParams.from_config()
    assert params.fvg_levels_mode == config.FVG_LEVELS_MODE
    assert params.fvg_displacement_atr_k == config.FVG_DISPLACEMENT_ATR_K
    assert scan_params._FVG_MODES == fvg.FVG_MODES


@pytest.mark.parametrize("changes", [{"fvg_levels_mode": "sideways"}, {"fvg_displacement_atr_k": 0.0},
                                     {"fvg_displacement_atr_k": -1.0},
                                     {"fvg_displacement_atr_k": math.nan}])
def test_scan_params_reject_an_invalid_fvg_value(changes):
    with pytest.raises(ValueError):
        dataclasses.replace(ScanParams.from_config(), **changes)


def test_both_knobs_are_reachable_through_both_engines():
    for attr in ("FVG_LEVELS_MODE", "FVG_DISPLACEMENT_ATR_K"):
        assert reach.classify(attr) == reach.REACHABLE
        assert reach.REGISTRY[attr].observed_by == reach.CS
        assert reach.REGISTRY[attr].fixture_observable is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/test_config_fvg_mode.py`
Expected: FAIL with `StopIteration` (no `FVG_LEVELS_MODE` field) and `AttributeError` on `scan_params._FVG_MODES`.

- [ ] **Step 3: Implement `config.py`**

Add `import math` after `import logging` (line 34). Insert immediately before `    Field("PYRAMIDING_ENABLED", "PYRAMIDING_ENABLED", "Universe & Scanning",`:

```python
    Field("FVG_LEVELS_MODE", "FVG_LEVELS_MODE", "Universe & Scanning",
          "Fair value gap level source mode",
          type="select", default="all", options=["all", "displacement", "off"],
          help="Which unfilled 3-candle fair value gaps (swingbot/core/market/fvg.py) reach the "
               "candidate level map -- and with it both the FVG confluence vote and the candidate "
               "entry/stop/target prices. all (default): every unfilled gap, unchanged from before "
               "v128. displacement: only gaps whose middle candle's body is at least "
               "FVG_DISPLACEMENT_ATR_K x ATR14 and closes in the gap-side third of its range. "
               "off: no FVG candidates. Charts draw every unfilled gap whatever this says. "
               "The default moves only if the v128 pre-registered one-shot VALIDATION passes both "
               "the v72 and v92 gates (docs/superpowers/results/2026-10-02-v128-fvg-preregistration.md). "
               "An unknown value falls back to all, never to off."),
    Field("FVG_DISPLACEMENT_ATR_K", "FVG_DISPLACEMENT_ATR_K", "Universe & Scanning",
          "FVG displacement body (x ATR14)",
          type="float", default="1.5", min=0.1, max=5.0, step=0.25,
          help="Read only when FVG_LEVELS_MODE=displacement: the middle candle's |close - open| must "
               "be at least this many ATR14. v128's grid is frozen at {1.0, 1.5, 2.0}. Must be a "
               "finite number > 0; anything else falls back to 1.5."),
```

In `_SEARCH_CLASSES["searchable"]`, change the last line `"FIB_TARGET_1_0_EXTENSION", "SHORT_UNIVERSE_RESEARCH_MODE",` to:

```python
        "FIB_TARGET_1_0_EXTENSION", "SHORT_UNIVERSE_RESEARCH_MODE",
        "FVG_LEVELS_MODE", "FVG_DISPLACEMENT_ATR_K",
```

Replace the `_MODE_VALUES` block and the whole `_cast` function with:

```python
# Lower-cased mode selects; an unknown value falls back to _MODE_FALLBACK's
# entry (default "off") with a warning.
_MODE_VALUES = {
    "PLAN_ENGINE_V2": ("off", "shadow", "on"),
    "STRATEGY_ALERTS_MODE": ("off", "shadow", "live"),
    "SHORT_UNIVERSE_RESEARCH_MODE": ("off", "broad", "isolated"),
    "FVG_LEVELS_MODE": ("all", "displacement", "off"),
}

# v128: "off" is a signal change for FVG_LEVELS_MODE (it removes a level
# source), so a typo must land on the pre-v128 behaviour instead.
_MODE_FALLBACK = {"FVG_LEVELS_MODE": "all"}

# Floats that must be finite and > 0. Anything else is a parse failure, so
# _apply_env falls back to the field default and knobs.parse_knob refuses the arm.
_POSITIVE_FLOATS = {"FVG_DISPLACEMENT_ATR_K"}


def _cast_mode(f: Field, raw: str) -> str:
    v = str(raw).lower()
    if v in _MODE_VALUES[f.attr]:
        return v
    fallback = _MODE_FALLBACK.get(f.attr, "off")
    log.warning("invalid %s=%r, falling back to %r", f.attr, raw, fallback)
    return fallback


def _cast_positive_float(raw: str) -> float:
    value = float(raw)
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"must be a finite number > 0, got {raw!r}")
    return value


def _cast(f: Field, raw: str):
    # A couple of "select" fields need a specific underlying type rather
    # than the raw string the <select> posts back -- handled by attr name
    # so it doesn't matter whether the field is rendered as select/text/etc.
    if f.attr == "LOG_LEVEL":
        return raw.upper()
    if f.attr in ("MIN_ALERT_CONFIDENCE_LEVEL", "SECONDARY_ALERT_MIN_CONFIDENCE"):
        return int(raw)
    if f.attr in _MODE_VALUES:
        return _cast_mode(f, raw)
    if f.attr in _POSITIVE_FLOATS:
        return _cast_positive_float(raw)
    caster = _CASTERS.get(f.type)
    return caster(raw) if caster else raw
```

- [ ] **Step 4: Implement `scan_params.py`**

Add `import math` after `from dataclasses import dataclass`. Below the imports add:

```python
#: Mirrors swingbot.core.market.fvg.FVG_MODES (pinned equal by
#: tests/test_config_fvg_mode.py); duplicated so this module stays import-light.
_FVG_MODES = ("all", "displacement", "off")


def _validate_fvg(mode, k) -> None:
    """A replace()d ScanParams must never carry an arm the config layer would refuse."""
    if mode not in _FVG_MODES:
        raise ValueError(f"fvg_levels_mode must be one of {_FVG_MODES}, got {mode!r}")
    if not isinstance(k, (int, float)) or not math.isfinite(k) or k <= 0:
        raise ValueError(f"fvg_displacement_atr_k must be a finite number > 0, got {k!r}")
```

After `short_universe_research_mode: str = "off"   # v118 research replay only` add:

```python
    fvg_levels_mode: str = "all"            # v128: all | displacement | off
    fvg_displacement_atr_k: float = 1.5     # v128: read only in displacement mode

    def __post_init__(self):
        _validate_fvg(self.fvg_levels_mode, self.fvg_displacement_atr_k)
```

In `from_config`, after `short_universe_research_mode=config.SHORT_UNIVERSE_RESEARCH_MODE,` add:

```python
            fvg_levels_mode=config.FVG_LEVELS_MODE,
            fvg_displacement_atr_k=config.FVG_DISPLACEMENT_ATR_K,
```

- [ ] **Step 5: Implement `reachability.py`**

After the `_TIGHTEN = ...` line add:

```python
_FVG = ("v128: level-map source read in levels.collect_candidate_levels, which both replay engines "
        "reach -- confluence through levels_asof/count_confirming_strategies, strategy through "
        "build_level_map (TP2) and apply_level_lifecycle. Not verified on the v74 fixture.")
```

Inside `REGISTRY`, after the `"TIGHTEN_ATR_MULT"` entry add:

```python
    "FVG_LEVELS_MODE": Reach(REACHABLE, _FVG, CS),
    "FVG_DISPLACEMENT_ATR_K": Reach(REACHABLE, _FVG + " Read only when FVG_LEVELS_MODE=displacement; "
                                    "a lone perturbation at the default mode is inert by design.", CS),
```

- [ ] **Step 6: Implement `.env.example`**

Insert after the line `AVWAP_LEVELS_ENABLED=true` (and its blank line):

```
# v128: which unfilled fair value gaps (swingbot/core/market/fvg.py) reach the
# level map -- the FVG confluence vote and the candidate prices.
# all | displacement | off. Default all (every unfilled gap, unchanged). The
# default moves only if the v128 pre-registered VALIDATION shot passes; see
# config.py's help text. An unknown value falls back to all.
FVG_LEVELS_MODE=all

# v128: displacement mode's middle-candle body threshold, in ATR14 multiples (> 0).
FVG_DISPLACEMENT_ATR_K=1.5
```

- [ ] **Step 7: Run the tests to verify they pass**

Run each:
- `python scripts/dev/testrun.py file tests/test_config_fvg_mode.py`
- `python scripts/dev/testrun.py file tests/test_scan_params_coverage.py`
- `python scripts/dev/testrun.py file tests/test_scan_params.py`
- `python scripts/dev/testrun.py file tests/backtesting/arms/test_reachability.py`
- `python scripts/dev/testrun.py file tests/test_env_example_sync.py`
- `python scripts/dev/testrun.py file tests/test_config_flags.py`
- `python scripts/dev/testrun.py file tests/admin/test_api_v1_system_settings.py`

Expected: every one PASS, `0 failed`.
Run: `python -m radon cc -s -n C swingbot/config.py swingbot/scan_params.py swingbot/core/backtesting/arms/reachability.py`
Expected: no line naming `_cast`, `_cast_mode`, `_cast_positive_float`, `_validate_fvg` or `__post_init__`. If radon lists a pre-existing function, check `git stash; python -m radon cc -s -n C swingbot/config.py; git stash pop` shows it with the same score: unchanged legacy is allowed, a worse one is not.

- [ ] **Step 8: Commit**

```bash
git add swingbot/config.py swingbot/scan_params.py swingbot/core/backtesting/arms/reachability.py .env.example tests/test_config_fvg_mode.py
git commit -m "feat(v128): FVG_LEVELS_MODE and FVG_DISPLACEMENT_ATR_K knobs -- validated, searchable, reachable"
```

### Task V128-3: Wire the mode into `collect_candidate_levels`; pin `/strategycharts`

**Files:**
- Create: `tests/fixtures/v128/levels_all_witness.json` (captured **before** editing `levels.py`)
- Create: `tests/market/test_levels_fvg_mode.py`
- Create: `tests/charts/test_strategy_charts_fvg_display.py`
- Modify: `swingbot/core/market/levels.py` (new `_fvg_candidates`; `params` resolved at the top of `collect_candidate_levels`; the FVG `try` block replaced)
- Modify: `swingbot/core/charts/trade_chart.py` (`_display_params()`; one call in `generate_all_strategy_charts`)

**Interfaces:**
- Consumes: `fvg.find_fair_value_gaps(df, mode=, k=)` (V128-1); `ScanParams.fvg_levels_mode`/`fvg_displacement_atr_k` (V128-2); `tests.market.fvg_frames` (V128-1).
- Produces: `levels._fvg_candidates(df, params) -> list[tuple[float, str]]`. It reads both fields **before** any `try`, returns `[]` for `off`, and otherwise returns `find_fair_value_gaps(df, mode=..., k=...)` with exceptions swallowed. Also `trade_chart._display_params() -> ScanParams` with `fvg_levels_mode="all"`. The candidate list order is unchanged: FVG candidates still follow the trendline block.

- [ ] **Step 1: Capture the level-map witness on the UNCHANGED `levels.py`**

```bash
python - <<'EOF'
import dataclasses, json, pathlib
from swingbot.core.market import levels
from swingbot.core.market.strategy_types import HORIZONS
from swingbot.scan_params import ScanParams
from tests.market.fvg_frames import witness_frame
params = dataclasses.replace(ScanParams.from_config(), avwap_levels_enabled=True,
                             volume_profile_nodes_enabled=False, fvg_levels_mode="all",
                             fvg_displacement_atr_k=1.5)
frame = witness_frame()
got = levels.collect_candidate_levels(frame, HORIZONS["3m"], float(frame["Close"].iloc[-1]), params=params)
assert any(s.startswith("FVG") for _, s in got), "witness must carry an FVG candidate"
out = pathlib.Path("tests/fixtures/v128/levels_all_witness.json")
out.write_text(json.dumps([[float(p), s] for p, s in got], indent=1), encoding="utf-8")
print(len(got), sum(s.startswith("FVG") for _, s in got))
EOF
git diff --quiet -- swingbot/core/market/levels.py && echo "levels.py untouched -- witness is pre-change"
```

Expected: two counts, the second ≥ 1, then `levels.py untouched -- witness is pre-change`.

- [ ] **Step 2: Write the failing tests**

```python
# tests/market/test_levels_fvg_mode.py
"""v128: the FVG mode reaches collect_candidate_levels and count_confirming_strategies."""
import dataclasses
import json
import types
from pathlib import Path

import pytest

from swingbot import config
from swingbot.core.market import fvg, levels
from swingbot.core.market.strategy_types import HORIZONS
from swingbot.scan_params import ScanParams
from tests.market.fvg_frames import BULL_THIRD, STRONG_BULL, WEAK_BULL, gap_frame, witness_frame

WITNESS = Path(__file__).resolve().parents[1] / "fixtures" / "v128" / "levels_all_witness.json"
H = HORIZONS["3m"]


def _params(**changes):
    pinned = {"avwap_levels_enabled": True, "volume_profile_nodes_enabled": False,
              "fvg_levels_mode": "all", "fvg_displacement_atr_k": 1.5}
    return dataclasses.replace(ScanParams.from_config(), **{**pinned, **changes})


def _collect(frame, params):
    return levels.collect_candidate_levels(frame, H, float(frame["Close"].iloc[-1]), params=params)


def _split(candidates):
    return ([c for c in candidates if c[1].startswith("FVG")],
            [c for c in candidates if not c[1].startswith("FVG")])


def _families(frame, params, target=101.25):
    price = float(frame["Close"].iloc[-1])
    candidates = levels.collect_candidate_levels(frame, H, price, params=params)
    return levels.count_confirming_strategies(frame, H, price, target, tolerance_pct=0.1,
                                              candidates=candidates)[1]


def test_default_mode_matches_the_pre_change_witness():
    expected = [tuple(row) for row in json.loads(WITNESS.read_text(encoding="utf-8"))]
    assert _collect(witness_frame(), _params()) == expected


def test_off_emits_no_fvg_candidate_and_leaves_every_other_source_alone():
    frame = witness_frame()
    off_fvg, off_rest = _split(_collect(frame, _params(fvg_levels_mode="off")))
    _, all_rest = _split(_collect(frame, _params()))
    assert off_fvg == [] and off_rest == all_rest


@pytest.mark.parametrize("k", [1.0, 1.5, 2.0])
def test_displacement_emits_exactly_the_filtered_gaps(k):
    frame = witness_frame()
    disp_fvg, disp_rest = _split(_collect(frame, _params(fvg_levels_mode="displacement",
                                                         fvg_displacement_atr_k=k)))
    _, all_rest = _split(_collect(frame, _params()))
    assert disp_fvg == fvg.find_fair_value_gaps(frame, mode="displacement", k=k)
    assert disp_rest == all_rest


def test_fvg_family_follows_the_mode():
    strong, weak = gap_frame(STRONG_BULL, BULL_THIRD), gap_frame(WEAK_BULL, BULL_THIRD)
    assert "FVG" in _families(strong, _params())
    assert "FVG" not in _families(strong, _params(fvg_levels_mode="off"))
    assert "FVG" in _families(strong, _params(fvg_levels_mode="displacement"))
    assert "FVG" in _families(weak, _params())
    assert "FVG" not in _families(weak, _params(fvg_levels_mode="displacement"))


def test_the_config_driven_replay_path_honours_the_mode(monkeypatch):
    """Replay passes no params: collect_candidate_levels builds them from config,
    which is exactly what measure_arms' apply_knobs mutates."""
    strong = gap_frame(STRONG_BULL, BULL_THIRD)
    price = float(strong["Close"].iloc[-1])
    monkeypatch.setattr(config, "FVG_LEVELS_MODE", "off")
    assert "FVG" not in levels.count_confirming_strategies(strong, H, price, 101.25, tolerance_pct=0.1)[1]
    monkeypatch.setattr(config, "FVG_LEVELS_MODE", "all")
    assert "FVG" in levels.count_confirming_strategies(strong, H, price, 101.25, tolerance_pct=0.1)[1]


def test_a_renamed_field_fails_loudly():
    fields = {k: v for k, v in dataclasses.asdict(_params()).items() if k != "fvg_levels_mode"}
    with pytest.raises(AttributeError):
        levels.collect_candidate_levels(witness_frame(), H, 100.0, params=types.SimpleNamespace(**fields))
```

```python
# tests/charts/test_strategy_charts_fvg_display.py
"""v128: /strategycharts is display, not signal -- it keeps every unfilled FVG whatever the mode."""
from swingbot import config
from swingbot.core.charts import trade_chart
from swingbot.core.market import levels
from swingbot.core.market.strategy_types import HORIZONS
from tests.market.fvg_frames import witness_frame


def test_strategy_charts_keep_every_gap_when_the_mode_is_off(monkeypatch, tmp_path):
    seen = {}

    def fake_collect(df, h, current_price, trendline_candidates=None, params=None):
        seen["params"] = params
        return []

    monkeypatch.setattr(config, "FVG_LEVELS_MODE", "off")
    monkeypatch.setattr(levels, "collect_candidate_levels", fake_collect)
    result = trade_chart.generate_all_strategy_charts("TEST", witness_frame(), "bullish", "3m",
                                                      str(tmp_path), HORIZONS["3m"])
    assert seen["params"].fvg_levels_mode == "all"
    assert set(result) == set(levels.ALL_STRATEGY_FAMILIES)


def test_display_params_override_only_the_fvg_mode(monkeypatch):
    monkeypatch.setattr(config, "FVG_LEVELS_MODE", "off")
    params = trade_chart._display_params()
    assert params.fvg_levels_mode == "all"
    assert params.avwap_levels_enabled == config.AVWAP_LEVELS_ENABLED
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/market/test_levels_fvg_mode.py`
Expected: FAIL. `test_off_...`, `test_displacement_...`, `test_fvg_family_follows_the_mode`, `test_the_config_driven_...` and `test_a_renamed_field_fails_loudly` fail. `test_default_mode_matches_the_pre_change_witness` PASSES (that is the characterisation).
Run: `python scripts/dev/testrun.py file tests/charts/test_strategy_charts_fvg_display.py`
Expected: FAIL with `AttributeError: ... has no attribute '_display_params'` and `seen["params"]` being `None`.

- [ ] **Step 4: Record `collect_candidate_levels`' complexity before editing**

Run: `python -m radon cc -s swingbot/core/market/levels.py | grep collect_candidate_levels`
Write down the letter and number (for example `F 178:0 collect_candidate_levels - D (27)`). Step 6 must show a number ≤ this one.

- [ ] **Step 5: Implement `levels.py`**

Above `def collect_candidate_levels(`, add:

```python
def _fvg_candidates(df: pd.DataFrame, params) -> list:
    """Fair Value Gap candidates under v128's FVG_LEVELS_MODE.

    Both ScanParams reads sit OUTSIDE the try, as AVWAP's flag check below
    does, so a renamed field fails loudly instead of silently dropping this
    source forever. "off" emits nothing: the FVG family then loses both its
    confluence vote and its candidate prices. Charts draw gaps from
    fvg.find_fair_value_gaps_detailed and never see this filter."""
    mode = params.fvg_levels_mode
    k = params.fvg_displacement_atr_k
    if mode == "off":
        return []
    try:
        return find_fair_value_gaps(df, mode=mode, k=k)
    except Exception:
        return []
```

In `collect_candidate_levels`, directly after `    candidates = []` and before `    close = df["Close"]`, insert:

```python
    if params is None:
        from swingbot.scan_params import ScanParams
        params = ScanParams.from_config()
```

Replace the FVG block:

```python
    try:
        # Fair Value Gaps (see fvg.py) -- unfilled 3-candle imbalance
        # zones, a widely-used price-action concept distinct from every
        # other source here (none of the others look at *gaps* between
        # candles). Only still-unfilled gaps count, so this is a live,
        # currently-relevant level, not a historical curiosity.
        candidates.extend(find_fair_value_gaps(df))
    except Exception:
        pass
```

with:

```python
    # Fair Value Gaps (see fvg.py) -- unfilled 3-candle imbalance zones, a
    # widely-used price-action concept distinct from every other source here
    # (none of the others look at *gaps* between candles). Only still-unfilled
    # gaps count. v128: which gaps count is params.fvg_levels_mode, read
    # outside any try -- see _fvg_candidates.
    candidates.extend(_fvg_candidates(df, params))
```

Delete the now-duplicate three lines that sit directly above `    if params.avwap_levels_enabled:`:

```python
    if params is None:
        from swingbot.scan_params import ScanParams
        params = ScanParams.from_config()
```

Keep the AVWAP comment block above them unchanged. Its sentence "The flag check sits OUTSIDE the try ..." still describes `if params.avwap_levels_enabled:`.

- [ ] **Step 6: Implement `trade_chart.py`**

Above `def generate_all_strategy_charts(`, add:

```python
def _display_params():
    """v128: /strategycharts is display, not signal -- it keeps every unfilled
    FVG whatever FVG_LEVELS_MODE says. Every other knob stays live config."""
    import dataclasses

    from swingbot.scan_params import ScanParams
    return dataclasses.replace(ScanParams.from_config(), fvg_levels_mode="all")
```

In `generate_all_strategy_charts`, change

```python
        all_candidates = levels.collect_candidate_levels(df, h, current_price)
```

to

```python
        all_candidates = levels.collect_candidate_levels(df, h, current_price, params=_display_params())
```

- [ ] **Step 7: Run the tests and complexity checks**

Run each:
- `python scripts/dev/testrun.py file tests/market/test_levels_fvg_mode.py`
- `python scripts/dev/testrun.py file tests/charts/test_strategy_charts_fvg_display.py`
- `python scripts/dev/testrun.py file tests/market/test_levels_params.py`
- `python scripts/dev/testrun.py file tests/market/test_levels_avwap.py`
- `python scripts/dev/testrun.py file tests/market/test_fvg_displacement.py`

Expected: every one PASS.
Run: `python scripts/dev/testrun.py fast`
Expected: `0 failed`, `0 xfailed`. `levels.py` feeds every scan and replay test, so this is the one task whose blast radius justifies `fast`.
Run: `python -m radon cc -s swingbot/core/market/levels.py | grep -E "collect_candidate_levels|_fvg_candidates"` and `python -m radon cc -s -n C swingbot/core/charts/trade_chart.py | grep -E "_display_params|generate_all_strategy_charts"`
Expected: `collect_candidate_levels` scores ≤ the Step 4 number (it lost one `try`). `_fvg_candidates` scores A or B. `_display_params` is absent from the `-n C` list, and `generate_all_strategy_charts` is either absent or has the score it had before.

- [ ] **Step 8: Commit**

```bash
git add swingbot/core/market/levels.py swingbot/core/charts/trade_chart.py tests/market/test_levels_fvg_mode.py tests/charts/test_strategy_charts_fvg_display.py tests/fixtures/v128/levels_all_witness.json
git commit -m "feat(v128): FVG mode reaches the level map outside the try; /strategycharts keeps every gap"
```
