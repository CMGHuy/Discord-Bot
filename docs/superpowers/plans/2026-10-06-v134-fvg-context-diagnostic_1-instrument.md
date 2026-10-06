# v134 FVG context diagnostic, Part 1: gate and dependency-free instrument (V134-1 .. V134-5)

> Header, "Dependencies: what is blocked on what", Global Constraints, the frozen readings (F1–F15), the spec gaps (G1–G3), the file map and `## Parallelisation` live in `2026-10-06-v134-fvg-context-diagnostic_0-index.md`. Every task here implicitly includes them. Work in the worktree `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-06-v134-fvg-context-diagnostic`; all paths below are relative to it.

# Phase 0 — Precondition gate

### Task V134-1: Hard precondition gate (v128, v130) and the worktree

**Files:**
- None created in the repo. This task creates the worktree and records which dependencies exist.

**Interfaces:**
- Consumes: nothing.
- Produces: the worktree, and one of three states that every later task obeys: `ALL PRESENT` (the whole plan may run), `PARTIAL` (only V134-2 .. V134-6 may run) or `BLOCKED` (stop and ask the partner).

**Blocked on:** nothing. This is the gate.

- [ ] **Step 1: Create the worktree** (skip if it exists)

Invoke the `worktree-lifecycle` skill, then:

```bash
git -C E:/Documents/Private/Projects/Discord-Bot worktree add .claude/worktrees/2026-10-06-v134-fvg-context-diagnostic -b 2026-10-06-v134-fvg-context-diagnostic main
```

All later commands in this plan run from that worktree.

- [ ] **Step 2: Check both dependencies** (run from the worktree root; re-run this step before V134-7 and again before V134-12)

```bash
python - <<'EOF'
import importlib, inspect, sys
sys.path.insert(0, "scripts/backtest")


def params(obj):
    return list(inspect.signature(obj).parameters)


def check_v128_code():
    from swingbot.core.market import fvg
    assert params(fvg.is_displacement_gap) == ["df", "gap", "k", "atr_series"], params(fvg.is_displacement_gap)
    fa = importlib.import_module("fvg_attribution")
    assert params(fa.record_ticker) == ["ticker", "df", "horizons", "signal_window"], params(fa.record_ticker)
    assert params(fa._recording) == ["log", "level_bars"], params(fa._recording)
    assert params(fa._provenance_row) == ["ticker", "df", "record", "level_bars", "memo"], params(fa._provenance_row)
    assert fa.VOTE_TOLERANCE_PCT == 5.0, fa.VOTE_TOLERANCE_PCT
    source = inspect.getsource(fa._recording)
    assert '"signal_index"' in source and '"take_profit"' in source, "recorder log lost signal_index/take_profit"
    from swingbot import config
    assert hasattr(config, "FVG_LEVELS_MODE")
    importlib.import_module("tests.market.fvg_frames")


def check_v130_code():
    from swingbot.core.market import structure
    assert params(structure.major_structure_features) == ["df", "direction"], params(structure.major_structure_features)
    wanted = {"struct_event_last", "struct_event_bars_ago", "structure_aligned_major"}
    assert wanted <= set(structure.MAJOR_KEYS), structure.MAJOR_KEYS
    assert "major_structure_features" in inspect.getsource(importlib.import_module("swingbot.core.edge.context"))
    fixtures = importlib.import_module("tests.market.structure_tier_fixtures")
    assert hasattr(fixtures, "DOWN") and hasattr(fixtures, "tier_frame")


for name, check in (("v128 code", check_v128_code), ("v130 code", check_v130_code)):
    try:
        check()
        print(f"{name}: PRESENT")
    except Exception as exc:
        print(f"{name}: MISSING -- {type(exc).__name__}: {exc}")
EOF
grep -c "(v128)" docs/claude/backtest-methodology.md
ls docs/superpowers/plans/no-lift/ docs/superpowers/plans/implemented/ | grep -E "v128|v130"
```

Expected when everything has landed: `v128 code: PRESENT`, `v130 code: PRESENT`, a count of `1` or more (v128's row in § "Closed pre-registrations — do not re-run these"), and both plans listed under `implemented/`.

- [ ] **Step 3: Decide the state and stop accordingly**

| What Step 2 printed | State | What may run |
|---|---|---|
| Both `PRESENT`, the v128 row exists | `ALL PRESENT` | The whole plan |
| Either `MISSING`, or the v128 row count is `0`, and neither plan is under `no-lift/` | `PARTIAL` | V134-2 .. V134-6 only. **Stop after V134-6.** Report which dependency is missing and wait |
| `v130` is listed under `plans/no-lift/` | `BLOCKED` | Nothing past V134-6. v130 closed without merging, so `major_structure_features` will never reach `main` (index, G3). Report `BLOCKED: v130 closed no-lift; the structure claim has no instrument on main. Read it from v130's unmerged branch, drop the claim, or stop?` and wait for the partner |
| A `MISSING` line names a wrong signature (an `AssertionError` showing a parameter list) | `BLOCKED` | Nothing that uses that symbol. The dependency landed with a different interface. Report the printed parameter list. Do not adapt the call on your own |

Never work around a missing symbol: no stub, no copy of v128's or v130's code, no local re-implementation.

- [ ] **Step 4: Record the state**

Put the state and the two `PRESENT`/`MISSING` lines, verbatim, in this task's hand-back to the controller. Nothing is committed by this task.

# Phase 1 — The instrument, dependency-free part

### Task V134-2: Gap enumeration and first touch

**Files:**
- Create: `swingbot/core/market/fvg_context.py`
- Create: `tests/market/fvg_context_frames.py` (shared hand-built frames; no `test_` prefix, so pytest does not collect it)
- Test: `tests/market/test_fvg_context_gaps.py`

**Interfaces:**
- Consumes: `fvg.find_fair_value_gaps_detailed(df)` (tests only, as the contrast).
- Produces (`swingbot.core.market.fvg_context`):
  - Constants `TOUCH_HORIZON_BARS = 60`, `OUTCOME_HORIZON_BARS = 20`, `STOP_ATR_BUFFER = 0.25`, `TARGET_R = 1.5`, `ATR_PERIOD = 14`, `CONFLUENCE_HORIZON = "4w"`, `DISPLACEMENT_K = 1.5`, `STRUCTURE_EVENT_MAX_AGE = 1`.
  - `all_gaps(df) -> list[dict]`: every gap at formation, oldest first, each `{"bottom", "top", "mid", "bar_index", "direction"}` exactly as `fvg.py` shapes it.
  - `first_touch(df, gap) -> dict`: `{"status": "touch" | "gapped_through" | "untouched" | "pending", "bar_index": int | None}`. `bar_index` is set for `touch` and `gapped_through` only.
- Produces (`tests/market/fvg_context_frames.py`): `FLAT`, `MIDDLE`, `THIRD`, `ABOVE`, `TOUCH`, `FLAT_BARS = 20`, `GAP_I = 21`, `BOTTOM = 101.0`, `TOP = 101.5`, `MID = 101.25`, `bar_frame(bars, start="2021-01-04")`, `gap_frame(after=(), middle=MIDDLE, third=THIRD)`, `mirror(frame)`, `extend(frame, bars)`. Every later test file imports these.

**Blocked on:** nothing.

- [ ] **Step 1: Invoke the `no-lookahead` skill.** First touch decides the last bar the live bot treats the gap as a level.

- [ ] **Step 2: Write the frame helpers**

```python
# tests/market/fvg_context_frames.py
"""Hand-built OHLC frames for the v134 FVG-context tests. No test_ prefix: not collected.

Standalone on purpose: it does not import v128's tests/market/fvg_frames.py, so
the dependency-free v134 tasks never wait on v128.

BASE is 20 flat candles, a middle candle (row 20) and a third candle (row 21).
Every one has a true range of exactly 2.0, so ATR14 is 2.0 on every row and
each number in the tests can be checked by hand:

    bullish gap at GAP_I = 21: bottom 101.0 (flat High), top 101.5 (third Low), mid 101.25
    size = 0.5 / 2.0 = 0.25 ATR
"""
import pandas as pd

FLAT = (100.0, 101.0, 99.0, 100.0)        # Open, High, Low, Close
MIDDLE = (100.0, 102.0, 100.0, 102.0)     # spans the zone 101.0..101.5 -> origin intrabar
THIRD = (102.0, 103.5, 101.5, 103.0)      # Low 101.5 > flat High 101.0
ABOVE = (103.0, 104.0, 102.0, 103.0)      # stays above the zone (Low 102.0 > 101.5); true range 2.0
TOUCH = (103.0, 103.25, 101.25, 102.0)    # Low 101.25 <= 101.5 and High >= 101.0; closes above; true range 2.0
FLAT_BARS = 20
GAP_I = FLAT_BARS + 1
BOTTOM, TOP, MID = 101.0, 101.5, 101.25


def bar_frame(bars, start="2021-01-04") -> pd.DataFrame:
    rows = list(bars)
    frame = pd.DataFrame(rows, columns=["Open", "High", "Low", "Close"],
                         index=pd.bdate_range(start, periods=len(rows)))
    frame["Volume"] = 1_000_000.0
    return frame


def gap_frame(after=(), middle=MIDDLE, third=THIRD) -> pd.DataFrame:
    """BASE (rows 0..21) followed by the bars in ``after`` (rows 22, 23, ...)."""
    return bar_frame([FLAT] * FLAT_BARS + [middle, third] + list(after))


def mirror(frame: pd.DataFrame) -> pd.DataFrame:
    """Reflect every price through 100: the bullish gap 101.0..101.5 becomes the
    bearish gap 98.5..99.0 at the same row, and every true range is unchanged."""
    out = frame.copy()
    out["Open"], out["Close"] = 200.0 - frame["Open"], 200.0 - frame["Close"]
    out["High"], out["Low"] = 200.0 - frame["Low"], 200.0 - frame["High"]
    return out


def extend(frame: pd.DataFrame, bars) -> pd.DataFrame:
    """``frame`` with more bars appended (the causality tests)."""
    rows = list(frame[["Open", "High", "Low", "Close"]].itertuples(index=False, name=None))
    return bar_frame(rows + list(bars), start=str(frame.index[0].date()))
```

- [ ] **Step 3: Write the failing tests**

```python
# tests/market/test_fvg_context_gaps.py
"""v134: gap enumeration at formation, and the first touch."""
import pytest

from swingbot.core.market import fvg
from swingbot.core.market import fvg_context as fc
from tests.market.fvg_context_frames import (ABOVE, BOTTOM, FLAT, GAP_I, MID, TOP, TOUCH, bar_frame, extend,
                                             gap_frame, mirror)

JUMP = (100.0, 100.5, 98.0, 99.0)          # Low 98.0 <= 101.5 but High 100.5 < 101.0: never trades in the zone


def _only(frame):
    gaps = fc.all_gaps(frame)
    assert len(gaps) == 1, gaps
    return gaps[0]


def _base(frame):
    return next(g for g in fc.all_gaps(frame) if g["bar_index"] == GAP_I)


def test_a_bullish_gap_is_enumerated_in_fvg_shape():
    assert _only(gap_frame()) == {"bottom": BOTTOM, "top": TOP, "mid": MID, "bar_index": GAP_I,
                                  "direction": "bullish"}


def test_the_bearish_mirror():
    assert _only(mirror(gap_frame())) == {"bottom": 98.5, "top": 99.0, "mid": 98.75, "bar_index": GAP_I,
                                          "direction": "bearish"}


def test_no_gap_when_the_first_and_third_candles_overlap():
    overlapping = (102.0, 103.5, 101.0, 103.0)             # Low 101.0 is not above the flat High 101.0
    assert fc.all_gaps(gap_frame(third=overlapping)) == []
    assert fc.all_gaps(bar_frame([FLAT] * 2)) == []


def test_a_filled_gap_is_still_enumerated():
    frame = gap_frame([TOUCH])
    assert fvg.find_fair_value_gaps_detailed(frame) == []  # the live scan drops it once touched
    assert _only(frame)["bar_index"] == GAP_I


def test_more_gaps_than_the_live_freshest_three_per_side():
    stairs = bar_frame([(100.0 + 2 * k, 101.0 + 2 * k, 99.5 + 2 * k, 100.5 + 2 * k) for k in range(10)])
    gaps = fc.all_gaps(stairs)
    assert [g["bar_index"] for g in gaps] == list(range(2, 10))
    assert {g["direction"] for g in gaps} == {"bullish"}
    assert len(fvg.find_fair_value_gaps_detailed(stairs)) == 3


def test_first_touch_on_the_first_bar_that_overlaps_the_zone():
    frame = gap_frame([ABOVE, ABOVE, TOUCH])
    assert fc.first_touch(frame, _base(frame)) == {"status": "touch", "bar_index": GAP_I + 3}


def test_a_low_exactly_at_the_top_is_a_touch():
    kiss = (103.0, 103.5, 101.5, 103.0)
    frame = gap_frame([kiss])
    assert fc.first_touch(frame, _base(frame)) == {"status": "touch", "bar_index": GAP_I + 1}


def test_a_bar_that_jumps_the_whole_zone_is_gapped_through():
    frame = gap_frame([ABOVE, JUMP, TOUCH])
    assert fc.first_touch(frame, _base(frame)) == {"status": "gapped_through", "bar_index": GAP_I + 2}


def test_a_touch_on_bar_61_is_untouched():
    frame = gap_frame([ABOVE] * fc.TOUCH_HORIZON_BARS + [TOUCH])
    assert fc.first_touch(frame, _base(frame)) == {"status": "untouched", "bar_index": None}


def test_a_touch_on_bar_60_still_counts():
    frame = gap_frame([ABOVE] * (fc.TOUCH_HORIZON_BARS - 1) + [TOUCH])
    assert fc.first_touch(frame, _base(frame)) == {"status": "touch", "bar_index": GAP_I + fc.TOUCH_HORIZON_BARS}


def test_a_frame_that_ends_inside_the_60_bars_is_pending_not_untouched():
    frame = gap_frame([ABOVE] * (fc.TOUCH_HORIZON_BARS - 1))
    assert fc.first_touch(frame, _base(frame)) == {"status": "pending", "bar_index": None}
    assert fc.first_touch(gap_frame(), _base(gap_frame()))["status"] == "pending"


@pytest.mark.parametrize("after,status", [([ABOVE, TOUCH], "touch"), ([ABOVE, JUMP], "gapped_through"),
                                          ([ABOVE] * 60, "untouched")])
def test_first_touch_mirrors_for_a_bearish_gap(after, status):
    frame = gap_frame(after)
    bullish = fc.first_touch(frame, _base(frame))
    bearish = fc.first_touch(mirror(frame), _base(mirror(frame)))
    assert bullish == bearish and bullish["status"] == status


def test_appending_bars_never_moves_a_touch_that_already_happened():
    frame = gap_frame([ABOVE, TOUCH])
    gap = _base(frame)
    violent = [(102.0, 130.0, 60.0, 61.0), (61.0, 140.0, 50.0, 120.0)] * 5
    assert fc.first_touch(extend(frame, violent), gap) == fc.first_touch(frame, gap)
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/market/test_fvg_context_gaps.py`
Expected: FAIL at collection with `ImportError: cannot import name 'fvg_context' from 'swingbot.core.market'`.

- [ ] **Step 5: Implement**

Create `swingbot/core/market/fvg_context.py`:

```python
"""v134: causal context tags and a frozen first-touch outcome for fair value gaps.

Measurement instrument only. No live path imports this module: it changes no
vote, level, plan, alert or chart. Spec:
docs/superpowers/specs/2026-10-06-v134-fvg-context-diagnostic-design.md

NO-LOOKAHEAD. A formation tag reads rows <= i (the gap's third candle) and a
touch tag reads rows <= tau (the first-touch bar). Each function slices that
prefix first and reads nothing else, so appending later bars cannot change a
tag. `gap_outcome` is the one function that reads forward, by definition: it
scores bars tau+1..tau+20. Its entry, stop and target are fixed at tau.

Bullish is described; bearish mirrors every comparison.
"""
from __future__ import annotations

import pandas as pd

# Frozen (partner-approved 2026-10-06). Not config knobs and not searched: a
# follow-on that wants to move one pre-registers its own grid.
TOUCH_HORIZON_BARS = 60      # no first touch within this many bars -> "untouched"
OUTCOME_HORIZON_BARS = 20    # bars after the touch that may hit the stop or target
STOP_ATR_BUFFER = 0.25       # stop sits this many ATR14[tau] beyond the far edge
TARGET_R = 1.5               # floor of the live risk-reward band: break-even hold rate 40%
ATR_PERIOD = 14
CONFLUENCE_HORIZON = "4w"    # its swing length matches OUTCOME_HORIZON_BARS; descriptive default
DISPLACEMENT_K = 1.5
STRUCTURE_EVENT_MAX_AGE = 1  # the event fired on the middle candle or on the third


def _gap(bottom: float, top: float, i: int, direction: str) -> dict:
    return {"bottom": float(bottom), "top": float(top), "mid": float((bottom + top) / 2),
            "bar_index": i, "direction": direction}


def all_gaps(df: pd.DataFrame) -> list:
    """Every 3-candle gap in ``df`` at formation, oldest first, in fvg.py's dict
    shape (``bar_index`` is the third candle). Unlike
    ``find_fair_value_gaps_detailed`` it keeps filled gaps and has no
    freshest-3-per-side cut."""
    high, low = df["High"].to_numpy(float), df["Low"].to_numpy(float)
    gaps = []
    for i in range(2, len(df)):
        if low[i] > high[i - 2]:
            gaps.append(_gap(high[i - 2], low[i], i, "bullish"))
        elif high[i] < low[i - 2]:
            gaps.append(_gap(high[i], low[i - 2], i, "bearish"))
    return gaps


def first_touch(df: pd.DataFrame, gap: dict) -> dict:
    """``{"status", "bar_index"}`` for the first bar after formation that reaches
    the zone's near edge, within TOUCH_HORIZON_BARS.

    touch           the bar overlaps the zone (fvg.py's own fill test)
    gapped_through  the bar jumped the whole zone without trading in it
    untouched       TOUCH_HORIZON_BARS bars passed and none reached the zone
    pending         the frame ends before that is known
    """
    i = int(gap["bar_index"])
    high, low = df["High"].to_numpy(float), df["Low"].to_numpy(float)
    bullish = gap["direction"] == "bullish"
    end = min(len(df), i + 1 + TOUCH_HORIZON_BARS)
    for t in range(i + 1, end):
        reached = low[t] <= gap["top"] if bullish else high[t] >= gap["bottom"]
        if not reached:
            continue
        overlaps = high[t] >= gap["bottom"] if bullish else low[t] <= gap["top"]
        return {"status": "touch" if overlaps else "gapped_through", "bar_index": t}
    seen = end - (i + 1)
    return {"status": "untouched" if seen >= TOUCH_HORIZON_BARS else "pending", "bar_index": None}
```

- [ ] **Step 6: Run the tests to verify they pass, then measure complexity**

Run: `python scripts/dev/testrun.py file tests/market/test_fvg_context_gaps.py`
Expected: PASS, `0 failed`.
Run: `python -m radon cc -s -n C swingbot/core/market/fvg_context.py`
Expected: no output.

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/market/fvg_context.py tests/market/fvg_context_frames.py tests/market/test_fvg_context_gaps.py
git commit -m "feat(v134): fvg_context -- enumerate every gap at formation and find its first touch"
```

### Task V134-3: Origin, size, approach and touch_close tags

**Files:**
- Modify: `swingbot/core/market/fvg_context.py`
- Test: `tests/market/test_fvg_context_tags.py`

**Interfaces:**
- Consumes: `all_gaps`, `first_touch` (V134-2); `indicators.atr(df, 14)`; `structure.true_range(df) -> pd.Series`; `structure.MIN_LEG_THIRD = 2`.
- Produces:
  - `formation_tags(df, gap) -> dict` with `"origin"` (`"intrabar" | "partial" | "true_gap"`) and `"size_atr"` (`float` rounded to 6, or `None` when ATR14 at `i` is not a finite positive number). V134-7 and V134-8 add the `"displacement"` and `"structure"` keys; do not assert the exact key set in this task's tests.
  - `touch_tags(df, gap, touch) -> dict` with `"approach"` (`"slowing" | "not_slowing" | "short"`), `"approach_ratio"` (`float` rounded to 6, or `None`) and `"touch_close"` (`"above" | "inside" | "below"`). V134-4 adds the confluence keys. `touch` is `first_touch`'s dict; only its `"bar_index"` is read.
  - Private helper `_atr_at(df, pos) -> float | None`, reused by V134-5.

**Blocked on:** nothing. Frozen readings F2, F3, F4 and F6 apply.

- [ ] **Step 1: Invoke the `no-lookahead` skill.** Each tag states the bar it is known at.

- [ ] **Step 2: Write the failing tests**

```python
# tests/market/test_fvg_context_tags.py
"""v134: the origin, size, approach and touch_close tags."""
import pytest

from swingbot.core.market import fvg_context as fc
from tests.market.fvg_context_frames import ABOVE, FLAT, GAP_I, TOUCH, bar_frame, extend, gap_frame, mirror

TRUE_GAP_THIRD = (103.0, 104.5, 101.5, 104.0)     # after a FLAT middle (High 101.0): the zone was never traded
PARTIAL_MIDDLE = (100.0, 101.25, 99.25, 101.0)    # reaches 0.25 into the 0.5-wide zone
# Return legs of six bars (rows 22..27); the last bar is the first touch.
SLOWING = [(103.0, 107.0, 103.0, 106.5), (106.5, 107.0, 103.0, 104.0),      # true range 4, 4
           (104.0, 105.0, 103.0, 104.0), (104.0, 105.0, 103.0, 104.0),      # 2, 2
           (104.0, 104.5, 103.5, 104.0), (104.0, 104.0, 101.0, 101.2)]      # 1, 3 -> (1+3)/(4+4) = 0.5
SPEEDING = [(103.0, 103.5, 102.5, 103.0)] * 4 + [                          # true range 1, 1, 1, 1
    (103.0, 105.0, 102.0, 102.5), (102.5, 103.5, 100.5, 100.8)]             # 3, 3 -> (3+3)/(1+1) = 3.0
STEADY = [ABOVE] * 5 + [TOUCH]                                              # true range 2 on all six -> 1.0
VIOLENT = [(102.0, 130.0, 60.0, 61.0), (61.0, 140.0, 50.0, 120.0)] * 5


def _gap(frame):
    return next(g for g in fc.all_gaps(frame) if g["bar_index"] == GAP_I)


def _touch_tags(frame):
    gap = _gap(frame)
    touch = fc.first_touch(frame, gap)
    assert touch["status"] == "touch", touch
    return fc.touch_tags(frame, gap, touch)


@pytest.mark.parametrize("flip", [False, True])
def test_origin_is_intrabar_when_the_middle_candle_spans_the_zone(flip):
    frame = mirror(gap_frame()) if flip else gap_frame()
    assert fc.formation_tags(frame, _gap(frame))["origin"] == "intrabar"


@pytest.mark.parametrize("flip", [False, True])
def test_origin_is_true_gap_when_the_middle_candle_never_traded_in_the_zone(flip):
    frame = gap_frame(middle=FLAT, third=TRUE_GAP_THIRD)
    frame = mirror(frame) if flip else frame
    assert fc.formation_tags(frame, _gap(frame))["origin"] == "true_gap"


@pytest.mark.parametrize("flip", [False, True])
def test_origin_is_partial_in_between(flip):
    frame = gap_frame(middle=PARTIAL_MIDDLE)
    frame = mirror(frame) if flip else frame
    assert fc.formation_tags(frame, _gap(frame))["origin"] == "partial"


@pytest.mark.parametrize("flip", [False, True])
def test_size_is_the_zone_width_in_atr14_at_the_third_candle(flip):
    frame = mirror(gap_frame()) if flip else gap_frame()
    assert fc.formation_tags(frame, _gap(frame))["size_atr"] == pytest.approx(0.25)     # 0.5 / ATR14 2.0


def test_size_is_none_before_atr14_exists():
    frame = bar_frame([FLAT] * 5 + [(100.0, 102.0, 100.0, 102.0), (102.0, 103.5, 101.5, 103.0)])
    gap = fc.all_gaps(frame)[0]
    assert fc.formation_tags(frame, gap)["size_atr"] is None
    assert fc.formation_tags(frame, gap)["origin"] == "intrabar"


@pytest.mark.parametrize("leg,bucket,ratio", [(SLOWING, "slowing", 0.5), (SPEEDING, "not_slowing", 3.0),
                                              (STEADY, "not_slowing", 1.0)])
@pytest.mark.parametrize("flip", [False, True])
def test_approach_compares_the_last_third_of_the_return_leg_with_the_first(leg, bucket, ratio, flip):
    frame = mirror(gap_frame(leg)) if flip else gap_frame(leg)
    tags = _touch_tags(frame)
    assert (tags["approach"], tags["approach_ratio"]) == (bucket, pytest.approx(ratio))


@pytest.mark.parametrize("bars", [1, 5])
def test_approach_is_short_below_six_bars(bars):
    tags = _touch_tags(gap_frame([ABOVE] * (bars - 1) + [TOUCH]))
    assert (tags["approach"], tags["approach_ratio"]) == ("short", None)


def test_approach_uses_whole_thirds_and_ignores_the_remainder():
    seven = SLOWING[:4] + [(104.0, 105.0, 103.0, 104.0)] + SLOWING[4:]      # 7 // 3 = 2 bars per third
    tags = _touch_tags(gap_frame(seven))
    assert (tags["approach"], tags["approach_ratio"]) == ("slowing", pytest.approx(0.5))


@pytest.mark.parametrize("leg,where", [(STEADY, "above"), (SLOWING, "inside"), (SPEEDING, "below")])
def test_touch_close_is_where_the_touch_bar_closed(leg, where):
    assert _touch_tags(gap_frame(leg))["touch_close"] == where


@pytest.mark.parametrize("leg,where", [(STEADY, "below"), (SLOWING, "inside"), (SPEEDING, "above")])
def test_touch_close_is_geometric_so_a_bearish_gap_reads_the_other_way_up(leg, where):
    assert _touch_tags(mirror(gap_frame(leg)))["touch_close"] == where


@pytest.mark.parametrize("flip", [False, True])
def test_appending_bars_changes_no_formation_tag(flip):
    frame = mirror(gap_frame()) if flip else gap_frame()
    gap = _gap(frame)
    assert fc.formation_tags(extend(frame, VIOLENT), gap) == fc.formation_tags(frame, gap)


@pytest.mark.parametrize("flip", [False, True])
def test_appending_bars_changes_no_touch_tag(flip):
    frame = mirror(gap_frame(SLOWING)) if flip else gap_frame(SLOWING)
    gap = _gap(frame)
    touch = fc.first_touch(frame, gap)
    assert fc.touch_tags(extend(frame, VIOLENT), gap, touch) == fc.touch_tags(frame, gap, touch)
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/market/test_fvg_context_tags.py`
Expected: FAIL with `AttributeError: module 'swingbot.core.market.fvg_context' has no attribute 'formation_tags'` (and `'touch_tags'`).

- [ ] **Step 4: Implement**

In `swingbot/core/market/fvg_context.py`, replace the import block (`from __future__` through `import pandas as pd`) with:

```python
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from swingbot.core.market import structure
from swingbot.core.market.indicators import atr
```

Append at the end of the file:

```python
def _atr_at(df: pd.DataFrame, pos: int) -> float | None:
    """ATR14 at row ``pos``, reading rows <= pos only. None unless finite and positive."""
    value = float(atr(df.iloc[:pos + 1], ATR_PERIOD).iloc[-1])
    return value if math.isfinite(value) and value > 0 else None


def _origin(window: pd.DataFrame, gap: dict) -> str:
    """How much of the zone the middle candle traded in: all of it (intrabar),
    some of it (partial) or none (true_gap, an overnight or earnings gap)."""
    m = int(gap["bar_index"]) - 1
    overlap = min(float(window["High"].iloc[m]), gap["top"]) - max(float(window["Low"].iloc[m]), gap["bottom"])
    if overlap <= 0:
        return "true_gap"
    return "intrabar" if overlap >= gap["top"] - gap["bottom"] else "partial"


def formation_tags(df: pd.DataFrame, gap: dict) -> dict:
    """Tags known at the close of the gap's third candle ``i``. Reads rows <= i."""
    i = int(gap["bar_index"])
    window = df.iloc[:i + 1]
    atr_i = _atr_at(window, i)
    return {"origin": _origin(window, gap),
            "size_atr": None if atr_i is None else round((gap["top"] - gap["bottom"]) / atr_i, 6)}


def _approach_ratio(window: pd.DataFrame, i: int, tau: int) -> float | None:
    """Mean true range of the last third of bars i+1..tau over the first third.
    None below MIN_LEG_THIRD bars per third, or when the first third has no range."""
    leg = structure.true_range(window).to_numpy(float)[i + 1:tau + 1]
    third = len(leg) // 3
    if third < structure.MIN_LEG_THIRD:
        return None
    first = float(np.mean(leg[:third]))
    if not first > 0:
        return None
    ratio = float(np.mean(leg[-third:])) / first
    return ratio if math.isfinite(ratio) else None


def _approach_bucket(ratio: float | None) -> str:
    if ratio is None:
        return "short"
    return "slowing" if ratio < 1 else "not_slowing"


def _touch_close(close: float, gap: dict) -> str:
    """Where the bar closed against the zone, geometrically (not mirrored)."""
    if close > gap["top"]:
        return "above"
    return "below" if close < gap["bottom"] else "inside"


def touch_tags(df: pd.DataFrame, gap: dict, touch: dict) -> dict:
    """Tags known at the close of bar ``touch["bar_index"]`` (tau). Reads rows <= tau."""
    i, tau = int(gap["bar_index"]), int(touch["bar_index"])
    window = df.iloc[:tau + 1]
    ratio = _approach_ratio(window, i, tau)
    return {"approach": _approach_bucket(ratio), "approach_ratio": None if ratio is None else round(ratio, 6),
            "touch_close": _touch_close(float(window["Close"].iloc[-1]), gap)}
```

`structure._range_decay` is deliberately not called: it takes impulse-leg pivot indices and rounds through `_num`. The return leg `i+1 … τ` is sliced here.

- [ ] **Step 5: Run the tests to verify they pass, then measure complexity**

Run: `python scripts/dev/testrun.py file tests/market/test_fvg_context_tags.py`
Expected: PASS, `0 failed`.
Run: `python scripts/dev/testrun.py file tests/market/test_fvg_context_gaps.py`
Expected: PASS (V134-2 is unchanged).
Run: `python -m radon cc -s -n C swingbot/core/market/fvg_context.py`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/market/fvg_context.py tests/market/test_fvg_context_tags.py
git commit -m "feat(v134): fvg_context -- origin, size, approach and touch_close tags"
```

### Task V134-4: Confluence tag

**Files:**
- Modify: `swingbot/core/market/fvg_context.py`
- Test: `tests/market/test_fvg_context_confluence.py`

**Interfaces:**
- Consumes: `levels.collect_candidate_levels(df, h, current_price, trendline_candidates=None, params=None) -> list[tuple[float, str]]`; `levels.count_confirming_strategies(df, h, current_price, target_price, tolerance_pct, candidates=None) -> tuple[int, list[str]]` (it folds labels to families with `strategy_family`); `levels.CLUSTER_TOLERANCE_PCT = 1.5`; `strategy_types.HORIZONS["4w"]`.
- Produces: `touch_tags` gains `"confluence"` (`"0" | "1-2" | "3+"`) and `"confluence_families"` (`int`: distinct non-FVG families within 1.5% of the gap's `mid`). Its full key set is now `confluence, confluence_families, approach, approach_ratio, touch_close`.

**Blocked on:** nothing. Frozen readings F5 and F12 apply.

- [ ] **Step 1: Invoke the `no-lookahead` skill.** The level collector must see the prefix ending at the touch bar and nothing after it.

- [ ] **Step 2: Write the failing tests**

```python
# tests/market/test_fvg_context_confluence.py
"""v134: the confluence tag -- distinct non-FVG families near the gap's mid at first touch."""
import numpy as np

from swingbot.core.market import fvg_context as fc
from swingbot.core.market import levels
from swingbot.core.market.strategy_types import HORIZONS
from tests.conftest import make_ohlcv
from tests.market.fvg_context_frames import ABOVE, GAP_I, MID, TOUCH, gap_frame, mirror

NEAR = MID * (1 + levels.CLUSTER_TOLERANCE_PCT / 100)        # 102.76875: the last price still inside
FAR = 103.0                                                  # 1.73% from the mid 101.25


def _tags(monkeypatch, candidates, frame=None):
    frame = gap_frame([ABOVE, TOUCH]) if frame is None else frame
    seen = {}

    def fake(df, h, current_price, trendline_candidates=None, params=None):
        seen.update(bars=len(df), horizon=h, price=current_price)
        return list(candidates)

    monkeypatch.setattr(levels, "collect_candidate_levels", fake)
    gap = next(g for g in fc.all_gaps(frame) if g["bar_index"] == GAP_I)
    touch = fc.first_touch(frame, gap)
    return fc.touch_tags(frame, gap, touch), seen, touch


def test_no_family_near_the_mid_is_bucket_0(monkeypatch):
    tags, _, _ = _tags(monkeypatch, [(FAR, "EMA20"), (90.0, "VWAP")])
    assert (tags["confluence"], tags["confluence_families"]) == ("0", 0)


def test_the_gaps_own_family_never_counts(monkeypatch):
    tags, _, _ = _tags(monkeypatch, [(MID, "FVG (bullish)"), (101.0, "FVG (bearish)")])
    assert (tags["confluence"], tags["confluence_families"]) == ("0", 0)


def test_several_candidates_of_one_family_count_once(monkeypatch):
    tags, _, _ = _tags(monkeypatch, [(101.0, "EMA20"), (101.4, "EMA50"), (101.2, "Fib 61.8%"),
                                     (101.3, "Swing high"), (MID, "FVG (bullish)")])
    assert (tags["confluence"], tags["confluence_families"]) == ("1-2", 2)       # EMA, Fibonacci


def test_three_families_is_bucket_3_plus(monkeypatch):
    tags, _, _ = _tags(monkeypatch, [(101.0, "EMA20"), (NEAR, "VWAP"), (100.0, "Pivot low"), (FAR, "Donchian high")])
    assert (tags["confluence"], tags["confluence_families"]) == ("3+", 3)


def test_the_tolerance_is_cluster_tolerance_pct_of_the_mid(monkeypatch):
    inside, _, _ = _tags(monkeypatch, [(NEAR, "VWAP")])
    outside, _, _ = _tags(monkeypatch, [(NEAR + 0.01, "VWAP")])
    assert (inside["confluence"], outside["confluence"]) == ("1-2", "0")


def test_levels_are_collected_on_the_prefix_ending_at_the_touch_bar_on_the_4w_horizon(monkeypatch):
    frame = gap_frame([ABOVE, TOUCH, ABOVE, ABOVE, ABOVE])
    _, seen, touch = _tags(monkeypatch, [], frame)
    assert seen == {"bars": touch["bar_index"] + 1, "horizon": HORIZONS["4w"], "price": 102.0}


def test_the_bearish_mirror_counts_the_same_way(monkeypatch):
    tags, seen, _ = _tags(monkeypatch, [(98.75, "EMA20"), (99.0, "VWAP"), (98.0, "Rolling support")],
                          mirror(gap_frame([ABOVE, TOUCH])))
    assert (tags["confluence"], seen["price"]) == ("3+", 98.0)


def test_the_real_collector_reads_nothing_after_the_touch_bar():
    """No monkeypatch: the live level collector on a 300-bar frame, cut at the touch and uncut."""
    closes = 100.0 + 8.0 * np.sin(np.arange(300) / 9.0) + np.arange(300) * 0.05
    frame = make_ohlcv(closes, spread_pct=1.0)
    scored = 0
    for gap in fc.all_gaps(frame):
        touch = fc.first_touch(frame, gap)
        if touch["status"] != "touch" or gap["bar_index"] < 120:
            continue
        cut = frame.iloc[:touch["bar_index"] + 1]
        assert fc.touch_tags(frame, gap, touch) == fc.touch_tags(cut, gap, touch)
        assert fc.touch_tags(frame, gap, touch)["confluence"] in ("0", "1-2", "3+")
        scored += 1
    assert scored >= 3, "the synthetic frame must carry touched gaps or this test proves nothing"
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/market/test_fvg_context_confluence.py`
Expected: FAIL with `KeyError: 'confluence'` (and, in the horizon test, `seen == {}`).

- [ ] **Step 4: Implement**

In `swingbot/core/market/fvg_context.py`, replace the two `swingbot` import lines with:

```python
from swingbot.core.market import levels, structure
from swingbot.core.market.indicators import atr
from swingbot.core.market.strategy_types import HORIZONS
```

Insert directly above `def _touch_close`:

```python
def _confluence_families(window: pd.DataFrame, gap: dict) -> int:
    """Distinct non-FVG families with a candidate within CLUSTER_TOLERANCE_PCT of the gap's mid."""
    horizon = HORIZONS[CONFLUENCE_HORIZON]
    close = float(window["Close"].iloc[-1])
    candidates = levels.collect_candidate_levels(window, horizon, close)
    _, families = levels.count_confirming_strategies(window, horizon, close, gap["mid"],
                                                     levels.CLUSTER_TOLERANCE_PCT, candidates=candidates)
    return sum(1 for family in families if family != "FVG")


def _confluence_bucket(families: int) -> str:
    if families == 0:
        return "0"
    return "1-2" if families <= 2 else "3+"
```

Replace the whole `touch_tags` function with:

```python
def touch_tags(df: pd.DataFrame, gap: dict, touch: dict) -> dict:
    """Tags known at the close of bar ``touch["bar_index"]`` (tau). Reads rows <= tau."""
    i, tau = int(gap["bar_index"]), int(touch["bar_index"])
    window = df.iloc[:tau + 1]
    ratio = _approach_ratio(window, i, tau)
    families = _confluence_families(window, gap)
    return {"confluence": _confluence_bucket(families), "confluence_families": families,
            "approach": _approach_bucket(ratio), "approach_ratio": None if ratio is None else round(ratio, 6),
            "touch_close": _touch_close(float(window["Close"].iloc[-1]), gap)}
```

`count_confirming_strategies` is called with `candidates=` so it never collects a second time, and it is the function whose family mapping the spec names.

- [ ] **Step 5: Run the tests to verify they pass, then measure complexity**

Run: `python scripts/dev/testrun.py file tests/market/test_fvg_context_confluence.py`
Expected: PASS, `0 failed`. The last test runs the live collector and takes a few seconds.
Run: `python scripts/dev/testrun.py file tests/market/test_fvg_context_tags.py`
Expected: PASS (the tag tests now also run the live collector on their small frames).
Run: `python -m radon cc -s -n C swingbot/core/market/fvg_context.py`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/market/fvg_context.py tests/market/test_fvg_context_confluence.py
git commit -m "feat(v134): fvg_context -- confluence tag from non-FVG families near the gap's mid"
```

### Task V134-5: The frozen first-touch outcome

**Files:**
- Modify: `swingbot/core/market/fvg_context.py`
- Test: `tests/market/test_fvg_context_outcome.py`

**Interfaces:**
- Consumes: `_atr_at(df, pos)` (V134-3); `STOP_ATR_BUFFER`, `TARGET_R`, `OUTCOME_HORIZON_BARS` (V134-2).
- Produces: `gap_outcome(df, gap, touch) -> dict` with exactly the keys `status, entry, stop, target, r, exit_index`. `status` is one of `failed_on_touch` (only `stop` is set), `win` (`r = 1.5`), `loss` (`r = -1.0`), `timeout` (`r` is the mark at `Close[τ+20]` in R, rounded to 6), `pending` (the frame ends before the outcome is known; `r` is `None`) or `no_atr` (ATR14 at `τ` is not a finite positive number; every other key is `None`).

**Blocked on:** nothing. Frozen readings F1 and F2 apply.

- [ ] **Step 1: Invoke the `no-lookahead` skill.** This is the one function that reads forward, by definition. Its entry, stop and target must still be fixed at `τ`.

- [ ] **Step 2: Write the failing tests**

```python
# tests/market/test_fvg_context_outcome.py
"""v134: the frozen first-touch outcome.

On BASE + TOUCH (touch at row 22, ATR14 exactly 2.0, Close 102.0):
    stop   = 101.0 - 0.25 * 2.0 = 100.5
    risk   = 102.0 - 100.5      = 1.5
    target = 102.0 + 1.5 * 1.5  = 104.25
"""
import pytest

from swingbot.core.market import fvg_context as fc
from tests.market.fvg_context_frames import FLAT, GAP_I, TOUCH, bar_frame, extend, gap_frame, mirror

TAU = GAP_I + 1
QUIET = (102.0, 103.0, 101.0, 102.6)          # reaches neither 100.5 nor 104.25
WIN = (102.5, 104.5, 102.0, 104.0)            # High 104.5 >= 104.25
LOSS = (102.0, 102.5, 100.4, 100.8)           # Low 100.4 <= 100.5
BOTH = (102.0, 104.5, 100.0, 101.0)           # reaches the stop and the target in one bar
DEEP_TOUCH = (103.0, 103.0, 100.0, 100.4)     # true range 3.0 -> ATR14 2.0714; stop 100.4821; closes below it


def _outcome(after, flip=False, touch_bar=TOUCH):
    frame = gap_frame([touch_bar] + list(after))
    frame = mirror(frame) if flip else frame
    gap = next(g for g in fc.all_gaps(frame) if g["bar_index"] == GAP_I)
    touch = fc.first_touch(frame, gap)
    assert touch == {"status": "touch", "bar_index": TAU}
    return fc.gap_outcome(frame, gap, touch)


def test_levels_are_fixed_at_the_touch_bar():
    out = _outcome([QUIET])
    assert (out["entry"], out["stop"], out["target"]) == pytest.approx((102.0, 100.5, 104.25))


def test_bearish_levels_mirror():
    out = _outcome([QUIET], flip=True)
    assert (out["entry"], out["stop"], out["target"]) == pytest.approx((98.0, 99.5, 95.75))


@pytest.mark.parametrize("flip", [False, True])
def test_win_at_the_first_bar_that_reaches_the_target(flip):
    out = _outcome([QUIET, WIN, LOSS], flip)
    assert (out["status"], out["r"], out["exit_index"]) == ("win", 1.5, TAU + 2)


@pytest.mark.parametrize("flip", [False, True])
def test_loss_at_the_first_bar_that_reaches_the_stop(flip):
    out = _outcome([QUIET, LOSS, WIN], flip)
    assert (out["status"], out["r"], out["exit_index"]) == ("loss", -1.0, TAU + 2)


@pytest.mark.parametrize("flip", [False, True])
def test_the_stop_wins_a_bar_that_reaches_both(flip):
    out = _outcome([BOTH], flip)
    assert (out["status"], out["r"], out["exit_index"]) == ("loss", -1.0, TAU + 1)


@pytest.mark.parametrize("flip", [False, True])
def test_timeout_is_marked_at_the_close_twenty_bars_after_the_touch(flip):
    out = _outcome([QUIET] * 20 + [WIN], flip)                     # the win on bar 21 is too late
    assert (out["status"], out["exit_index"]) == ("timeout", TAU + 20)
    assert out["r"] == pytest.approx(0.4)                          # (102.6 - 102.0) / 1.5


@pytest.mark.parametrize("flip", [False, True])
def test_a_hit_on_bar_twenty_still_counts(flip):
    assert _outcome([QUIET] * 19 + [WIN], flip)["status"] == "win"


@pytest.mark.parametrize("flip", [False, True])
def test_pending_when_the_frame_ends_before_the_outcome_is_known(flip):
    out = _outcome([QUIET] * 19, flip)
    assert (out["status"], out["r"], out["exit_index"]) == ("pending", None, None)
    assert out["entry"] == pytest.approx(98.0 if flip else 102.0)


@pytest.mark.parametrize("flip", [False, True])
def test_failed_on_touch_when_the_touch_bar_closes_at_or_beyond_the_stop(flip):
    out = _outcome([WIN], flip, touch_bar=DEEP_TOUCH)
    assert (out["status"], out["entry"], out["target"], out["r"]) == ("failed_on_touch", None, None, None)
    assert out["stop"] == pytest.approx(99.517857 if flip else 100.482143, abs=1e-6)


def test_no_atr_when_atr14_does_not_exist_at_the_touch_bar():
    frame = bar_frame([FLAT] * 5 + [(100.0, 102.0, 100.0, 102.0), (102.0, 103.5, 101.5, 103.0), TOUCH, WIN])
    gap = fc.all_gaps(frame)[0]
    assert fc.gap_outcome(frame, gap, fc.first_touch(frame, gap))["status"] == "no_atr"


def test_every_status_returns_the_same_keys():
    keys = {"status", "entry", "stop", "target", "r", "exit_index"}
    for after, touch_bar in (([WIN], TOUCH), ([LOSS], TOUCH), ([QUIET] * 20, TOUCH), ([QUIET], TOUCH),
                             ([WIN], DEEP_TOUCH)):
        assert set(_outcome(after, touch_bar=touch_bar)) == keys


@pytest.mark.parametrize("flip", [False, True])
def test_appending_bars_never_moves_the_entry_stop_or_target(flip):
    short = _outcome([QUIET], flip)
    violent = [(102.0, 130.0, 60.0, 61.0), (61.0, 140.0, 50.0, 120.0)] * 12
    frame = gap_frame([TOUCH, QUIET])
    frame = mirror(frame) if flip else frame
    gap = next(g for g in fc.all_gaps(frame) if g["bar_index"] == GAP_I)
    longer = fc.gap_outcome(extend(frame, violent), gap, {"status": "touch", "bar_index": TAU})
    assert [longer[k] for k in ("entry", "stop", "target")] == [short[k] for k in ("entry", "stop", "target")]
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/market/test_fvg_context_outcome.py`
Expected: FAIL with `AttributeError: module 'swingbot.core.market.fvg_context' has no attribute 'gap_outcome'`.

- [ ] **Step 4: Implement**

Append at the end of `swingbot/core/market/fvg_context.py`:

```python
def _result(status: str, entry=None, stop=None, target=None, r=None, exit_index=None) -> dict:
    return {"status": status, "entry": entry, "stop": stop, "target": target, "r": r, "exit_index": exit_index}


def _first_exit(df: pd.DataFrame, tau: int, stop: float, target: float, bullish: bool) -> tuple:
    """("loss" | "win", bar) at the first stop or target bar in tau+1..tau+20;
    the stop wins a bar that reaches both. (None, None) when neither is reached."""
    high, low = df["High"].to_numpy(float), df["Low"].to_numpy(float)
    for t in range(tau + 1, min(len(df), tau + 1 + OUTCOME_HORIZON_BARS)):
        if (low[t] <= stop) if bullish else (high[t] >= stop):
            return "loss", t
        if (high[t] >= target) if bullish else (low[t] <= target):
            return "win", t
    return None, None


def gap_outcome(df: pd.DataFrame, gap: dict, touch: dict) -> dict:
    """The frozen outcome of entering at the touch bar's close.

    ``status`` is failed_on_touch (the touch bar closed at or beyond the stop: no
    entry), win (+1.5R), loss (-1R), timeout (marked at Close[tau+20]), pending
    (the frame ends first) or no_atr (ATR14[tau] is not a positive number).
    Entry, stop and target read rows <= tau only.
    """
    tau = int(touch["bar_index"])
    atr_tau = _atr_at(df, tau)
    if atr_tau is None:
        return _result("no_atr")
    bullish = gap["direction"] == "bullish"
    entry = float(df["Close"].iloc[tau])
    stop = gap["bottom"] - STOP_ATR_BUFFER * atr_tau if bullish else gap["top"] + STOP_ATR_BUFFER * atr_tau
    risk = entry - stop if bullish else stop - entry
    if risk <= 0:
        return _result("failed_on_touch", stop=stop)
    target = entry + TARGET_R * risk if bullish else entry - TARGET_R * risk
    status, bar = _first_exit(df, tau, stop, target, bullish)
    if status is not None:
        return _result(status, entry, stop, target, TARGET_R if status == "win" else -1.0, bar)
    last = tau + OUTCOME_HORIZON_BARS
    if last >= len(df):
        return _result("pending", entry, stop, target)
    move = float(df["Close"].iloc[last]) - entry
    return _result("timeout", entry, stop, target, round((move if bullish else -move) / risk, 6), last)
```

- [ ] **Step 5: Run the tests to verify they pass, then measure complexity**

Run: `python scripts/dev/testrun.py file tests/market/test_fvg_context_outcome.py`
Expected: PASS, `0 failed`.
Run: `python -m radon cc -s -n C swingbot/core/market/fvg_context.py`
Expected: no output (`gap_outcome` is `B (10)`).

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/market/fvg_context.py tests/market/test_fvg_context_outcome.py
git commit -m "feat(v134): fvg_context -- frozen first-touch outcome (0.25 ATR stop, 1.5R target, 20 bars)"
```
