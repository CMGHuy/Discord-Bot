# v182 — Part 4: the range-breakdown ideas and the outcome-blind count

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier.

**Spec:** [2026-10-21-v182-short-screen-range-breakdown-design.md](../specs/2026-10-21-v182-short-screen-range-breakdown-design.md) — Part C (the two breakdown ideas, the event count before the shot) and Part B check 5 (fill depth, outcome-blind).
**Index:** [2026-10-21-v182-short-screen-range-breakdown_0-index.md](2026-10-21-v182-short-screen-range-breakdown_0-index.md) — Goal, Global Constraints, Review Focus, Parallelisation and the task ledger live there and bind every task below.
**Worktree:** `.claude/worktrees/2026-10-21-v182-short-screen-range-breakdown` (created in V182-1). Every command below runs from that worktree's root.

**Tasks:** V182-13..V182-16. V182-13 may run beside V182-9..V182-12 (disjoint files, no contract). V182-14 needs V182-3 and V182-13; V182-15 needs V182-14 (shared `IDEA_MODULES` and registry test); V182-16 needs V182-11 and V182-15 (index § Parallelisation).

**Long byte-identity, every task (partner rule):** after each task's own narrow run, also run both golden regression files from V182-1 and expect them green:

```bash
python scripts/dev/testrun.py file tests/backtesting/screen/test_long_byte_identical.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_calibration_long_golden.py
```

Never edit the golden files to make a test pass. The two new ideas never enter the long golden: V182-1 captures the frozen `long_golden.LONG_IDEAS` (nine names), never `list(IDEAS)`.

**Contracts from earlier parts this part consumes** (index ledger):

- V182-3: `Idea(..., direction="short", entry="next_open" | "level", levels=callable | None, control=callable | None, family=tuple)`; `_load` reads `DIRECTION`, `ENTRY`, `levels`, `control_events`, `FAMILY` with `getattr` defaults.
- V182-9: `race.candidate_events(events, member, warm, cap, *, entry="next_open")` (level mode reads warm-up at t−1); `race.level_fills(df, event_pos, levels, atr, direction) -> tuple[np.ndarray, np.ndarray]` (fill price, depth in ATR14[t−1]); `race.non_overlapping(event_pos, exit_pos)` unchanged.
- V182-10: `null.draw_groups(df, event_pos, eligible, k, seed, *, atr, trend, direction="long", depth=None) -> NullGroups` with fields `event_pos, groups, fills, dropped_no_match, null_slots, null_unfilled, null_depths` — positions and fills only, no race.
- V182-11: `screen_idea.raw_levels(idea, df) -> np.ndarray | None` (None for a next-open idea); `_books` threads levels and depth for a level idea.

**First-break clause (spec corrected at 0f6a87f7):** `Close[t−1] ≥ S[t−1]`, where `S[t−1]` is the support computed for bar t−1 (min Low over t−31..t−2), i.e. `first_break = Close.shift(1) >= support(df).shift(1)`. The first wording compared with S over t−30..t−1, which includes bar t−1's own Low and so could never fail. V182-13 pins that a second consecutive breakdown bar does not fire.

---

# Phase C1 — the frozen range, the two ideas, the count before the shot

### Task V182-13: Range and trend helper, `rolling_min`

**Model:** opus — a frozen pre-registered definition under the no-lookahead rule: window offsets, NaN handling and the touch-span arithmetic decide what the one shot measures.

**Files:**
- Modify: `swingbot/core/backtesting/screen/indicators.py` (append after `rolling_max`, :56-59)
- Create: `swingbot/core/backtesting/screen/ideas/_range_breakdown.py`
- Test: `tests/backtesting/screen/test_range_breakdown_rules.py` (create; suite `backtesting-arms` already owns the directory)

**Interfaces:**
- Consumes: `indicators.atr(df, n=14)`, `indicators.sma(values, n)`, `indicators.rolling_max(values, n)` (all exist, `indicators.py:37-59`).
- Produces:
  - `indicators.rolling_min(values: pd.Series, n: int) -> pd.Series` — minimum over the last n bars, t included, NaN until n bars.
  - `_range_breakdown` constants: `WINDOW = 30`, `HEIGHT_ATR = 5.0`, `TOUCH_ATR = 0.25`, `TOUCH_SPAN = 5`, `SMA_LEN = 50`, `SMA_LAG = 10`, `WARMUP = 61`, `PARAMS` (dict below), `SOURCE`, `FAMILY = ("range_breakdown_close", "range_breakdown_stop")`.
  - Float series, NaN where undefined: `support(df)` (S for bar t = min Low over t−30..t−1), `resistance(df)` (R = max High over t−30..t−1), `prior_atr(df)` (ATR14[t−1]).
  - Bool series, never NaN, on `df.index`: `in_range(df)` (height + both touch clauses), `downtrend(df)`, `first_break(df)`, `setup(df)` (every clause except the trigger), `control_setup(df)` (setup without the range clauses: the trend-only control).
  - Test fixtures reused by V182-14/15: `test_range_breakdown_rules.breakdown_frame(*, event_close=97.0, event_low=None, event_open=None, edit=None, decline=60) -> pd.DataFrame`, `T = 90`, `_tall(o, h, l, c)`.
- Consumed by: V182-14 and V182-15 (`setup`, `control_setup`, `support`, `PARAMS`, `SOURCE`, `FAMILY`), V182-17 (the control, through the idea modules).

The leading underscore keeps `_range_breakdown` out of `IDEA_MODULES` by convention: it is a shared helper, not an idea. Nothing in it reads bar t; the trigger (which reads bar t) lives in each idea module.

- [ ] **Step 1: Write the failing `tests/backtesting/screen/test_range_breakdown_rules.py`**

```python
"""v182 range breakdown: the frozen range, trend and first-break clauses.

Fixture: a 60-bar decline 160 -> 101, a 30-bar range on bars 60..89
(Low 99, High 101, Close 100), the event bar 90, four bars at 97. True range
is exactly 2 on every bar before 90, so ATR14[89] = 2.0, the touch band is
0.5 and the height limit is 10. For t = 90: S = 99, R = 101.
"""
import numpy as np
import pandas as pd
import pytest

from swingbot.core.backtesting.screen import indicators
from swingbot.core.backtesting.screen.ideas import _range_breakdown as rb
from tests.backtesting.screen.helpers import assert_prefix_stable, frame, random_walk

T = 90


def breakdown_frame(*, event_close=97.0, event_low=None, event_open=None, edit=None,
                    decline=60):
    """The fixture above. ``edit(opens, highs, lows, closes)`` changes bars in
    place before the frame is built; ``decline`` shortens the prefix (the
    event bar is then ``decline + 30``)."""
    closes = np.r_[160.0 - np.arange(decline), np.full(30, 100.0), np.full(5, 97.0)]
    t = decline + 30
    closes[t] = event_close
    opens, highs, lows = closes.copy(), closes + 1.0, closes - 1.0
    if event_low is not None:
        lows[t] = event_low
    if event_open is not None:
        opens[t] = event_open
    if edit is not None:
        edit(opens, highs, lows, closes)
    return frame(closes, opens=opens, highs=highs, lows=lows)


def _setup_bars(df):
    return np.flatnonzero(rb.setup(df).to_numpy()).tolist()


def test_rolling_min_is_the_minimum_over_the_last_n_bars_t_included():
    out = indicators.rolling_min(pd.Series([5.0, 3.0, 4.0, 1.0, 2.0]), 3)
    assert out.iloc[:2].isna().all()
    assert out.iloc[2:].tolist() == [3.0, 1.0, 1.0]


def test_the_definition_is_frozen_at_the_spec_values():
    assert (rb.WINDOW, rb.HEIGHT_ATR, rb.TOUCH_ATR, rb.TOUCH_SPAN) == (30, 5.0, 0.25, 5)
    assert (rb.SMA_LEN, rb.SMA_LAG, rb.WARMUP) == (50, 10, 61)
    assert rb.PARAMS == {"window": 30, "height_atr": 5.0, "touch_atr": 0.25,
                         "touch_span": 5, "sma": 50, "sma_lag": 10, "warmup": 61}
    assert rb.FAMILY == ("range_breakdown_close", "range_breakdown_stop")
    assert rb.SOURCE == ('Schwab, "The Ins and Outs of a Swing Trade" (2025-03-07), '
                         "downswing breakout")


def test_levels_read_the_thirty_bars_before_t():
    df = breakdown_frame()
    assert rb.support(df).iloc[T] == 99.0
    assert rb.resistance(df).iloc[T] == 101.0
    assert rb.prior_atr(df).iloc[T] == 2.0
    inside = breakdown_frame(edit=lambda o, h, l, c: l.__setitem__(60, 98.0))
    outside = breakdown_frame(edit=lambda o, h, l, c: l.__setitem__(59, 50.0))
    assert rb.support(inside).iloc[T] == 98.0       # bar t-30 is in the window
    assert rb.support(outside).iloc[T] == 99.0      # bar t-31 is not


def test_the_fixture_sets_up_on_the_event_bar_only():
    assert _setup_bars(breakdown_frame()) == [T]


def _tall(o, h, l, c):
    h[70] = h[80] = 125.0          # two high touches 10 apart, height 26 > 5 x ATR


def _low_touches(a, b):
    def edit(o, h, l, c):
        l[60:90] = 99.75           # 0.75 above S: outside the 0.25 x ATR band
        l[a] = l[b] = 99.0
    return edit


def _high_touches(a, b):
    def edit(o, h, l, c):
        h[60:90] = 100.25
        h[a] = h[b] = 101.0
    return edit


def _one_low_touch(o, h, l, c):
    l[60:90] = 99.75
    l[75] = 99.0


@pytest.mark.parametrize("edit, expected", [
    (None, True),
    (_tall, False),                     # range too tall
    (_one_low_touch, False),            # one touch of S only
    (_low_touches(75, 79), False),      # touches of S four bars apart
    (_low_touches(75, 80), True),       # five bars apart
    (_high_touches(75, 79), False),     # touches of R four bars apart
    (_high_touches(75, 80), True),
])
def test_range_clauses(edit, expected):
    df = breakdown_frame(edit=edit)
    assert bool(rb.in_range(df).iloc[T]) is expected
    assert bool(rb.setup(df).iloc[T]) is expected


def test_a_tall_range_still_passes_the_trend_only_control():
    df = breakdown_frame(edit=_tall)
    assert not rb.setup(df).iloc[T]
    assert rb.control_setup(df).iloc[T]


def test_a_rising_prefix_is_not_a_downtrend():
    def rising(o, h, l, c):
        c[:60] = 41.0 + np.arange(60)
        o[:60], h[:60], l[:60] = c[:60], c[:60] + 1.0, c[:60] - 1.0
    df = breakdown_frame(edit=rising)
    assert not rb.downtrend(df).iloc[T]
    assert not rb.setup(df).iloc[T] and not rb.control_setup(df).iloc[T]


@pytest.mark.parametrize("closes, expected", [
    (np.r_[200.0 - np.arange(100), 99.0, 99.0], True),     # SMA50 falling, close below
    (np.r_[200.0 - np.arange(100), 200.0, 99.0], False),   # falling, close above
    (np.r_[100.0 + np.arange(100), 50.0, 50.0], False),    # rising, close below
])
def test_downtrend_needs_a_falling_sma50_and_the_prior_close_below_it(closes, expected):
    assert bool(rb.downtrend(frame(closes)).iloc[101]) is expected


@pytest.mark.parametrize("close89, low89, expected", [
    (99.0, 99.0, True),           # prior close exactly at its own support S[t-1] = 99
    (98.9375, 98.875, False),     # prior close already below S[t-1]
])
def test_first_break_compares_the_prior_close_with_its_own_support(close89, low89, expected):
    """Consistent bars only (Low <= Close): S[t-1] is the support of bar t-1's
    window (t-31..t-2), so bar t-1's own Low is not part of it."""
    def edit(o, h, l, c):
        c[89], o[89], l[89] = close89, close89, low89
    df = breakdown_frame(edit=edit)
    assert rb.support(df).shift(1).iloc[T] == 99.0
    assert bool(rb.first_break(df).iloc[T]) is expected
    assert bool(rb.setup(df).iloc[T]) is expected


def test_a_second_consecutive_breakdown_bar_does_not_fire():
    """Bar 90 closes below S = 99 (low 98.875); bar 91 closes lower still.
    Bar 91 meets every other clause (its window now holds 98.875 as S, the
    99 lows touch it), but its prior close was already below its own support,
    so only the first break sets up."""
    df = breakdown_frame(event_close=98.9375, event_low=98.875)
    assert rb.setup(df).iloc[T]
    nxt = T + 1
    assert rb.in_range(df).iloc[nxt] and rb.downtrend(df).iloc[nxt]
    assert df["Close"].iloc[nxt] < rb.support(df).iloc[nxt]       # a breakdown bar again
    assert not rb.first_break(df).iloc[nxt]
    assert not rb.setup(df).iloc[nxt] and not rb.control_setup(df).iloc[nxt]
    assert _setup_bars(df) == [T]


def test_warm_up_needs_61_bars_before_the_event():
    early = breakdown_frame(decline=30)      # event bar 60
    assert rb.in_range(early).iloc[60] and rb.downtrend(early).iloc[60]
    assert not rb.setup(early).iloc[60]
    assert _setup_bars(breakdown_frame(decline=31)) == [61]


@pytest.mark.parametrize("value", [0.0, -1.0, np.nan])
def test_a_zero_negative_or_nan_prior_atr_gives_no_setup(monkeypatch, value):
    df = breakdown_frame()
    monkeypatch.setattr(rb, "prior_atr", lambda frame_: pd.Series(value, index=frame_.index))
    assert not rb.setup(df).any()
    assert not rb.control_setup(df).any()


def test_every_clause_is_a_clean_bool_series():
    walk = random_walk(400)
    for fn in (rb.in_range, rb.downtrend, rb.first_break, rb.setup, rb.control_setup):
        out = fn(walk)
        assert out.dtype == bool and out.index.equals(walk.index), fn.__name__


def test_setup_at_t_never_reads_bar_t():
    df = breakdown_frame()
    wild = df.copy()
    wild.iloc[T] = [50.0, 300.0, 10.0, 20.0, 1e6]
    for fn in (rb.support, rb.resistance, rb.prior_atr):
        assert fn(wild).iloc[T] == fn(df).iloc[T]
    assert rb.setup(wild).iloc[T] and rb.control_setup(wild).iloc[T]


def test_setup_reads_no_later_bar():
    assert _setup_bars(breakdown_frame()) == [T]                   # non-vacuous
    assert_prefix_stable(rb.setup, breakdown_frame(), [60, 89, 90, 91, 94])
    walk = random_walk(3000)
    assert rb.setup(walk).any()
    assert_prefix_stable(rb.setup, walk, [100, 1500, 2999])
    assert_prefix_stable(rb.control_setup, walk, [100, 1500, 2999])
```

The fixture numbers were checked against a draft of Step 3's module (26 tests, all green).

- [ ] **Step 2: Run it to verify it fails**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_range_breakdown_rules.py`
Expected: FAIL — `ImportError: cannot import name '_range_breakdown'` (collection error).

- [ ] **Step 3: Implement**

Append to `swingbot/core/backtesting/screen/indicators.py`:

```python
def rolling_min(values: pd.Series, n: int) -> pd.Series:
    """Minimum over the last n bars, t included."""
    return values.rolling(n, min_periods=n).min()
```

Create `swingbot/core/backtesting/screen/ideas/_range_breakdown.py`:

```python
"""v182 range breakdown: the one frozen range and trend definition.

Shared by range_breakdown_close and range_breakdown_stop (spec Part C). The
numbers are the idea and are never tuned after the run. Every series here
describes bar t from bars <= t-1 only; the trigger, which reads bar t, lives
in each idea module.

- window: the 30 bars t-30..t-1; S = min Low, R = max High over it;
- a range, not a slide: R - S <= 5 x ATR14[t-1];
- touches: at least two window bars with Low <= S + 0.25 x ATR14[t-1], the
  earliest and latest at least 5 bars apart; the same for High >= R - 0.25 x
  ATR14[t-1];
- own downtrend: SMA50[t-1] < SMA50[t-11] and Close[t-1] < SMA50[t-1];
- first break: Close[t-1] >= S[t-1], the support of bar t-1's own window
  (t-31..t-2), so a breakdown sets up once, not on every following bar;
- ATR14[t-1] NaN or <= 0 means no event; warm-up: bar position t >= 61.

Not an idea module (no CAP, no events): the leading underscore keeps it out
of IDEA_MODULES.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

from swingbot.core.backtesting.screen import indicators

WINDOW = 30
HEIGHT_ATR = 5.0
TOUCH_ATR = 0.25
TOUCH_SPAN = 5
SMA_LEN = 50
SMA_LAG = 10
WARMUP = 61
PARAMS = {"window": WINDOW, "height_atr": HEIGHT_ATR, "touch_atr": TOUCH_ATR,
          "touch_span": TOUCH_SPAN, "sma": SMA_LEN, "sma_lag": SMA_LAG,
          "warmup": WARMUP}
SOURCE = ('Schwab, "The Ins and Outs of a Swing Trade" (2025-03-07), '
          "downswing breakout")
FAMILY = ("range_breakdown_close", "range_breakdown_stop")


def prior_atr(df: pd.DataFrame) -> pd.Series:
    """ATR14[t-1]: the ATR known before bar t opens."""
    return indicators.atr(df).shift(1)


def support(df: pd.DataFrame) -> pd.Series:
    """S for bar t: min Low over t-30..t-1."""
    return indicators.rolling_min(df["Low"].shift(1), WINDOW)


def resistance(df: pd.DataFrame) -> pd.Series:
    """R for bar t: max High over t-30..t-1."""
    return indicators.rolling_max(df["High"].shift(1), WINDOW)


def _spread(hit: np.ndarray) -> np.ndarray:
    """Per window row: at least two touches, the earliest and latest at least
    TOUCH_SPAN bars apart (two distinct bars follow from the span)."""
    first = hit.argmax(axis=1)
    last = hit.shape[1] - 1 - hit[:, ::-1].argmax(axis=1)
    return hit.any(axis=1) & (last - first >= TOUCH_SPAN)


def _touched(df: pd.DataFrame, column: str, low: pd.Series, high: pd.Series) -> pd.Series:
    """Bar t: the window t-30..t-1 of ``column`` has spread touches inside
    [low[t], high[t]]. A NaN bound is no touch."""
    values = df[column].to_numpy(dtype=float)
    out = np.zeros(len(values), dtype=bool)
    if len(values) > WINDOW:
        # Row r holds bars r..r+29: the window of bar t = r + 30.
        windows = sliding_window_view(values[:-1], WINDOW)
        lo = low.to_numpy(dtype=float)[WINDOW:, None]
        hi = high.to_numpy(dtype=float)[WINDOW:, None]
        with np.errstate(invalid="ignore"):
            out[WINDOW:] = _spread((windows >= lo) & (windows <= hi))
    return pd.Series(out, index=df.index)


def in_range(df: pd.DataFrame) -> pd.Series:
    """Height and both touch clauses."""
    s, r, atr = support(df), resistance(df), prior_atr(df)
    band = TOUCH_ATR * atr
    height = ((r - s) <= HEIGHT_ATR * atr).fillna(False)
    lows = _touched(df, "Low", s - np.inf, s + band)
    highs = _touched(df, "High", r - band, r + np.inf)
    return (height & lows & highs).fillna(False)


def downtrend(df: pd.DataFrame) -> pd.Series:
    """SMA50[t-1] < SMA50[t-11] and Close[t-1] < SMA50[t-1]."""
    sma = indicators.sma(df["Close"], SMA_LEN).shift(1)
    falling = (sma < sma.shift(SMA_LAG)).fillna(False)
    below = (df["Close"].shift(1) < sma).fillna(False)
    return falling & below


def first_break(df: pd.DataFrame) -> pd.Series:
    """Close[t-1] >= S[t-1]: the prior bar closed at or above its own
    range support (window t-31..t-2), so only the first breakdown bar sets up."""
    return (df["Close"].shift(1) >= support(df).shift(1)).fillna(False)


def _ready(df: pd.DataFrame) -> pd.Series:
    """ATR14[t-1] finite and > 0, and 61 completed bars before t."""
    atr_ok = (prior_atr(df) > 0).fillna(False)
    return atr_ok & pd.Series(np.arange(len(df)) >= WARMUP, index=df.index)


def control_setup(df: pd.DataFrame) -> pd.Series:
    """The trend-only control: trend and first-break clauses, no range
    clauses (spec Part C descriptive block; printed, never gating)."""
    return downtrend(df) & first_break(df) & _ready(df)


def setup(df: pd.DataFrame) -> pd.Series:
    """Every clause except the trigger on bar t."""
    return control_setup(df) & in_range(df)
```

The clauses call `prior_atr` and `support` through the module globals on purpose: the NaN/zero-ATR test monkeypatches `rb.prior_atr`, and every clause must see the patched value.

- [ ] **Step 4: Run the tests, the complexity gate and the goldens**

```bash
python scripts/dev/testrun.py file tests/backtesting/screen/test_range_breakdown_rules.py
python scripts/dev/testrun.py file tests/backtesting/screen/test_indicators.py
python scripts/dev/complexity_gate.py
python scripts/dev/testrun.py file tests/backtesting/screen/test_long_byte_identical.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_calibration_long_golden.py
```

Expected: `26 passed` for the new file; the other four green; the complexity gate reports no regression.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/screen/indicators.py swingbot/core/backtesting/screen/ideas/_range_breakdown.py tests/backtesting/screen/test_range_breakdown_rules.py
git commit -m "feat(v182): frozen range and trend helper for the breakdown ideas, rolling_min

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V182-14: Idea `range_breakdown_close`

**Model:** opus — registers a frozen one-shot idea: its trigger, constants and registry pins are the pre-registration, and a wrong one spends the shot on the wrong question.

**Files:**
- Create: `swingbot/core/backtesting/screen/ideas/range_breakdown_close.py`
- Modify: `swingbot/core/backtesting/screen/ideas/__init__.py` (`IDEA_MODULES`, :25-27)
- Test: `tests/backtesting/screen/test_idea_range_breakdown_close.py` (create)
- Test: `tests/backtesting/screen/test_ideas_registry.py` (five registry pins plus V182-3's direction/entry pin, edited in the same diff)

**Interfaces:**
- Consumes: `_range_breakdown.setup`, `control_setup`, `support`, `PARAMS`, `SOURCE`, `FAMILY` (V182-13); `breakdown_frame`, `T`, `_tall` from `tests/backtesting/screen/test_range_breakdown_rules.py` (V182-13); `Idea` fields `direction`, `entry`, `levels`, `control`, `family` and `_load`'s `getattr` reads (V182-3).
- Produces: module `range_breakdown_close` with `CAP = 20`, `RACE = "fixed"`, `DIRECTION = "short"` (no `ENTRY`: the default `next_open`; no `levels`), `PARAMS = {**_range_breakdown.PARAMS, "trigger": "close[t] < S"}`, `SUMMARY`, `SOURCE`, `FAMILY`, `events(df) -> pd.Series` (named `"range_breakdown_close"`), `control_events(df) -> pd.Series`; `IDEAS["range_breakdown_close"]` with `direction="short"`, `entry="next_open"`, `control=control_events`, `family=FAMILY`.
- Consumed by: V182-16 (`--idea range_breakdown_close --count-only`), V182-17 (`idea.control`, `idea.family`), V182-18/19 (the count and the shot).

Registering the idea makes it a `--idea` choice of `screen_idea.py`. Nothing runs it here: the count is V182-18, the shot V182-19.

- [ ] **Step 1: Write the failing `tests/backtesting/screen/test_idea_range_breakdown_close.py`**

```python
"""range_breakdown_close: a close below the 30-bar range's support, short, next open."""
import numpy as np
import pandas as pd
import pytest

from swingbot.core.backtesting.screen.ideas import _range_breakdown as rb
from swingbot.core.backtesting.screen.ideas import range_breakdown_close as idea
from tests.backtesting.screen.helpers import assert_prefix_stable, random_walk
from tests.backtesting.screen.test_range_breakdown_rules import T, _tall, breakdown_frame


def _positions(df, fn=idea.events):
    return np.flatnonzero(fn(df).to_numpy()).tolist()


def test_the_module_freezes_a_short_fixed_cap_20_next_open_idea():
    assert (idea.CAP, idea.RACE, idea.DIRECTION) == (20, "fixed", "short")
    assert getattr(idea, "ENTRY", "next_open") == "next_open"
    assert not hasattr(idea, "levels")
    assert idea.PARAMS == {**rb.PARAMS, "trigger": "close[t] < S"}
    assert idea.SOURCE == rb.SOURCE and idea.FAMILY == rb.FAMILY
    assert "close[t] < S" in idea.SUMMARY and "short" in idea.SUMMARY


def test_fires_on_the_close_below_support_only():
    assert _positions(breakdown_frame()) == [T]
    assert idea.events(breakdown_frame()).name == "range_breakdown_close"


@pytest.mark.parametrize("close, low, fires", [
    (98.875, 97.875, True),    # closed below S = 99
    (99.0, 98.0, False),       # closed at S: not below
    (99.5, 98.0, False),       # low broke S, the close did not
])
def test_the_close_must_end_below_support(close, low, fires):
    df = breakdown_frame(event_close=close, event_low=low)
    assert (T in _positions(df)) is fires


def test_events_are_the_setup_with_the_close_trigger():
    walk = random_walk(3000)
    expected = (rb.setup(walk) & (walk["Close"] < rb.support(walk))).fillna(False)
    pd.testing.assert_series_equal(idea.events(walk), expected, check_names=False)
    assert idea.events(walk).any()


def test_control_events_drop_the_range_clauses_only():
    tall = breakdown_frame(edit=_tall)
    assert _positions(tall) == []
    assert T in _positions(tall, idea.control_events)
    walk = random_walk(3000)
    expected = (rb.control_setup(walk) & (walk["Close"] < rb.support(walk))).fillna(False)
    pd.testing.assert_series_equal(idea.control_events(walk), expected, check_names=False)
    assert not (idea.events(walk) & ~idea.control_events(walk)).any()


def test_reads_no_later_bar():
    assert _positions(breakdown_frame()) == [T]                    # non-vacuous
    assert_prefix_stable(idea.events, breakdown_frame(), [60, 89, 90, 91, 94])
    walk = random_walk(3000)
    assert idea.events(walk).any()
    assert_prefix_stable(idea.events, walk, [100, 1500, 2999])
    assert_prefix_stable(idea.control_events, walk, [100, 1500, 2999])
```

Then edit `tests/backtesting/screen/test_ideas_registry.py` in the same diff (each pin gains the new name; nothing else in it moves):

- `test_registry_holds_the_first_batch_in_spec_order_then_later_ideas`: the tuple ends `"sweep_reclaim_bos", "range_breakdown_close")`.
- `test_time_caps_are_the_spec_values`: add `"range_breakdown_close": 20`.
- `test_frozen_parameter_sets`: append

```python
    assert dict(IDEAS["range_breakdown_close"].params) == {
        "window": 30, "height_atr": 5.0, "touch_atr": 0.25, "touch_span": 5,
        "sma": 50, "sma_lag": 10, "warmup": 61, "trigger": "close[t] < S"}
```

- `test_every_registered_idea_is_raced_under_one_pinned_shape`: add `"range_breakdown_close": "fixed"`.
- `test_only_the_two_intermarket_ideas_read_context_series`: add `"range_breakdown_close": ()`.
- `test_every_registered_idea_pins_its_direction_and_entry` (V182-3): add `"range_breakdown_close": "short"` to the direction dict and `"range_breakdown_close": "next_open"` to the entry dict, and replace its last assertion with:

```python
    breakdown = ("range_breakdown_close", "range_breakdown_stop")
    older = {n: i for n, i in IDEAS.items() if n not in breakdown}
    assert {n: (i.levels, i.control, i.family) for n, i in older.items()} == {
        n: (None, None, ()) for n in older}
    close = IDEAS["range_breakdown_close"]
    assert close.levels is None
    assert close.control is range_breakdown_close.control_events
    assert close.family == ("range_breakdown_close", "range_breakdown_stop")
```

  with `from swingbot.core.backtesting.screen.ideas import range_breakdown_close` added to the file's imports. (`breakdown` already names the stop idea so V182-15 only adds its own lines.)

- [ ] **Step 2: Run them to verify they fail**

```bash
python scripts/dev/testrun.py file tests/backtesting/screen/test_idea_range_breakdown_close.py
python scripts/dev/testrun.py file tests/backtesting/screen/test_ideas_registry.py
```

Expected: FAIL — `ImportError: cannot import name 'range_breakdown_close'` in both (collection errors).

- [ ] **Step 3: Implement**

Create `swingbot/core/backtesting/screen/ideas/range_breakdown_close.py`:

```python
"""Range breakdown, close-confirmed, short (Schwab 2025). Frozen 2026-10-21 (v182).

A stock in its own downtrend (SMA50 falling, the prior close below it) has
spent 30 bars in a defined range (two touches of each side at least 5 bars
apart, no taller than 5 x ATR14). Today closes below the range's support S.
The screen's race enters short at the next open. The range and trend
definition is shared with range_breakdown_stop (_range_breakdown.py); the two
ideas are nested (every close event is a stop event) and screened as one
family.
"""
from __future__ import annotations

import pandas as pd

from swingbot.core.backtesting.screen.ideas import _range_breakdown as rb

CAP = 20
RACE = "fixed"
DIRECTION = "short"
PARAMS = {**rb.PARAMS, "trigger": "close[t] < S"}
SUMMARY = ("30-bar range (R - S <= 5 ATR14[t-1], two touches of each side "
           ">= 5 bars apart) in a falling SMA50 with the prior close below it; "
           "close[t] < S (short, next open)")
SOURCE = rb.SOURCE
FAMILY = rb.FAMILY


def _trigger(df: pd.DataFrame) -> pd.Series:
    """Bar t closes below the support of the 30 bars before it."""
    return df["Close"] < rb.support(df)


def events(df: pd.DataFrame) -> pd.Series:
    """Event at the close of t: the frozen setup and a close below S."""
    return (rb.setup(df) & _trigger(df)).rename("range_breakdown_close")


def control_events(df: pd.DataFrame) -> pd.Series:
    """The trend-only control (spec Part C): same trigger and trend clauses,
    no range clauses. Printed by the results doc, never gating."""
    return (rb.control_setup(df) & _trigger(df)).rename("range_breakdown_close_control")
```

In `swingbot/core/backtesting/screen/ideas/__init__.py`, append `"range_breakdown_close"` to `IDEA_MODULES` after `"sweep_reclaim_bos"`.

- [ ] **Step 4: Run the tests, the complexity gate and the goldens**

```bash
python scripts/dev/testrun.py file tests/backtesting/screen/test_idea_range_breakdown_close.py
python scripts/dev/testrun.py file tests/backtesting/screen/test_ideas_registry.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_idea.py
python scripts/dev/complexity_gate.py
python scripts/dev/testrun.py file tests/backtesting/screen/test_long_byte_identical.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_calibration_long_golden.py
```

Expected: `8 passed` for the idea file; the rest green (`test_screen_idea.py` proves the new `--idea` choice breaks no existing CLI test).

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/screen/ideas/range_breakdown_close.py swingbot/core/backtesting/screen/ideas/__init__.py tests/backtesting/screen/test_idea_range_breakdown_close.py tests/backtesting/screen/test_ideas_registry.py
git commit -m "feat(v182): register range_breakdown_close (short, next open, cap 20)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V182-15: Idea `range_breakdown_stop`

**Model:** opus — the level-entry idea: what the order may know before bar t opens (S from bars ≤ t−1) and what the trigger may read on bar t (its Low only) are the no-lookahead boundary of the one shot.

**Files:**
- Create: `swingbot/core/backtesting/screen/ideas/range_breakdown_stop.py`
- Modify: `swingbot/core/backtesting/screen/ideas/__init__.py` (`IDEA_MODULES`)
- Test: `tests/backtesting/screen/test_idea_range_breakdown_stop.py` (create)
- Test: `tests/backtesting/screen/test_ideas_registry.py` (the same six pins as V182-14, one more name)

**Interfaces:**
- Consumes: V182-13 (`_range_breakdown`, `breakdown_frame`, `T`, `_tall`), V182-14 (`range_breakdown_close.events`, for the nesting test), V182-3 (`Idea(entry="level", levels=...)` validation: a level idea needs `levels`, fixed shape only).
- Produces: module `range_breakdown_stop` with `CAP = 20`, `RACE = "fixed"`, `DIRECTION = "short"`, `ENTRY = "level"`, `PARAMS = {**_range_breakdown.PARAMS, "trigger": "low[t] < S", "level": "S"}`, `SUMMARY`, `SOURCE`, `FAMILY`, `levels(df) -> pd.Series` (S on every bar, from bars ≤ t−1), `events(df) -> pd.Series` (named `"range_breakdown_stop"`), `control_events(df) -> pd.Series`; `IDEAS["range_breakdown_stop"]` with `entry="level"`, `levels=levels`.
- Consumed by: V182-11's `raw_levels(idea, df)` (reads `idea.levels`), V182-16 (`--count-only`, check 5), V182-17, V182-18/20.

The fill (`min(Open[t], S)`), the entry-bar stop rule and the 2 × slippage are the race's job (V182-9), not the idea's. The idea only says where the resting sell stop sits and which bars it fills on: `Low[t] < S`, strict, the same inequality the race fills on.

- [ ] **Step 1: Write the failing `tests/backtesting/screen/test_idea_range_breakdown_stop.py`**

```python
"""range_breakdown_stop: a resting sell stop at the 30-bar range's support, short, level entry."""
import numpy as np
import pandas as pd
import pytest

from swingbot.core.backtesting.screen.ideas import _range_breakdown as rb
from swingbot.core.backtesting.screen.ideas import range_breakdown_close as close_idea
from swingbot.core.backtesting.screen.ideas import range_breakdown_stop as idea
from tests.backtesting.screen.helpers import assert_prefix_stable, random_walk
from tests.backtesting.screen.test_range_breakdown_rules import T, _tall, breakdown_frame


def _positions(df, fn=idea.events):
    return np.flatnonzero(fn(df).to_numpy()).tolist()


def test_the_module_freezes_a_short_fixed_cap_20_level_idea():
    assert (idea.CAP, idea.RACE, idea.DIRECTION, idea.ENTRY) == (20, "fixed", "short", "level")
    assert idea.PARAMS == {**rb.PARAMS, "trigger": "low[t] < S", "level": "S"}
    assert idea.SOURCE == rb.SOURCE and idea.FAMILY == rb.FAMILY
    assert "low[t] < S" in idea.SUMMARY and "sell stop" in idea.SUMMARY


def test_fires_when_the_low_trades_through_support():
    assert _positions(breakdown_frame()) == [T]
    assert idea.events(breakdown_frame()).name == "range_breakdown_stop"


@pytest.mark.parametrize("low, fires", [
    (98.875, True),    # traded below S = 99: the sell stop fills
    (99.0, False),     # touched S only: Low[t] < level is strict
])
def test_the_low_must_trade_below_support(low, fires):
    df = breakdown_frame(event_close=100.0, event_low=low)
    assert (T in _positions(df)) is fires


def test_a_close_back_inside_the_range_still_fires():
    df = breakdown_frame(event_close=100.0, event_low=98.0, event_open=100.0)
    assert T in _positions(df)
    assert T not in _positions(df, close_idea.events)


def test_the_level_is_support_on_every_bar():
    df = breakdown_frame()
    pd.testing.assert_series_equal(idea.levels(df), rb.support(df), check_names=False)
    assert idea.levels(df).iloc[T] == 99.0


def test_the_order_is_placed_from_bars_before_t():
    df = breakdown_frame()
    wild = df.copy()
    wild.iloc[T] = [50.0, 300.0, 10.0, 20.0, 1e6]
    assert idea.levels(wild).iloc[T] == idea.levels(df).iloc[T] == 99.0


def test_the_trigger_reads_only_bar_ts_low():
    """Nothing beyond bar t's Open/Low decides the order: High and Close of
    bar t, and every later bar, can change without moving the event."""
    df = breakdown_frame(event_close=100.0, event_low=98.0)
    moved = df.copy()
    moved.iloc[T, moved.columns.get_loc("High")] = 250.0
    moved.iloc[T, moved.columns.get_loc("Close")] = 40.0
    moved.iloc[T + 1:, moved.columns.get_loc("Low")] = 1.0
    assert idea.events(moved).iloc[T] and idea.events(df).iloc[T]
    assert idea.levels(moved).iloc[T] == idea.levels(df).iloc[T]


def test_events_are_the_setup_with_the_low_trigger():
    walk = random_walk(3000)
    expected = (rb.setup(walk) & (walk["Low"] < rb.support(walk))).fillna(False)
    pd.testing.assert_series_equal(idea.events(walk), expected, check_names=False)


def test_every_close_event_is_a_stop_event():
    """The two ideas are nested (spec Part C): Close < S implies Low < S."""
    for seed in (1, 2, 7, 13):
        walk = random_walk(2700, seed=seed)
        assert not (close_idea.events(walk) & ~idea.events(walk)).any(), seed
    assert idea.events(random_walk(2700, seed=7)).sum() > close_idea.events(
        random_walk(2700, seed=7)).sum()


def test_control_events_drop_the_range_clauses_only():
    tall = breakdown_frame(edit=_tall)
    assert _positions(tall) == []
    assert T in _positions(tall, idea.control_events)
    walk = random_walk(3000)
    expected = (rb.control_setup(walk) & (walk["Low"] < rb.support(walk))).fillna(False)
    pd.testing.assert_series_equal(idea.control_events(walk), expected, check_names=False)


def test_reads_no_later_bar():
    assert _positions(breakdown_frame()) == [T]                    # non-vacuous
    assert_prefix_stable(idea.events, breakdown_frame(), [60, 89, 90, 91, 94])
    assert_prefix_stable(idea.levels, breakdown_frame(), [60, 89, 90, 91, 94])
    walk = random_walk(3000)
    assert idea.events(walk).any()
    for fn in (idea.events, idea.levels, idea.control_events):
        assert_prefix_stable(fn, walk, [100, 1500, 2999])
```

Then edit `tests/backtesting/screen/test_ideas_registry.py` in the same diff:

- `test_registry_holds_the_first_batch_in_spec_order_then_later_ideas`: the tuple ends `"range_breakdown_close", "range_breakdown_stop")`.
- `test_time_caps_are_the_spec_values`: add `"range_breakdown_stop": 20`.
- `test_frozen_parameter_sets`: append

```python
    assert dict(IDEAS["range_breakdown_stop"].params) == {
        "window": 30, "height_atr": 5.0, "touch_atr": 0.25, "touch_span": 5,
        "sma": 50, "sma_lag": 10, "warmup": 61, "trigger": "low[t] < S", "level": "S"}
```

- `test_every_registered_idea_is_raced_under_one_pinned_shape`: add `"range_breakdown_stop": "fixed"`.
- `test_only_the_two_intermarket_ideas_read_context_series`: add `"range_breakdown_stop": ()`.
- `test_every_registered_idea_pins_its_direction_and_entry`: add `"range_breakdown_stop": "short"` to the direction dict and `"range_breakdown_stop": "level"` to the entry dict, and append:

```python
    stop = IDEAS["range_breakdown_stop"]
    assert stop.levels is range_breakdown_stop.levels
    assert stop.control is range_breakdown_stop.control_events
    assert stop.family == close.family
```

  with `range_breakdown_stop` added to the import line V182-14 wrote.

- [ ] **Step 2: Run them to verify they fail**

```bash
python scripts/dev/testrun.py file tests/backtesting/screen/test_idea_range_breakdown_stop.py
python scripts/dev/testrun.py file tests/backtesting/screen/test_ideas_registry.py
```

Expected: FAIL — `ImportError: cannot import name 'range_breakdown_stop'` in both.

- [ ] **Step 3: Implement**

Create `swingbot/core/backtesting/screen/ideas/range_breakdown_stop.py`:

```python
"""Range breakdown, resting sell stop, short (Schwab 2025). Frozen 2026-10-21 (v182).

The same frozen range and downtrend as range_breakdown_close
(_range_breakdown.py). Before bar t opens, a sell stop rests at the range's
support S, known from bars <= t-1, for one bar. It fills when bar t trades
below S (Low[t] < S, strict; a bar that only touches S does not fill). The
screen races it in level mode (ENTRY = "level"): entry on bar t at
min(Open[t], S), risk 1.5 x ATR14[t-1], the worst-case entry-bar stop rule
and 2 x stop-market slippage (v182 Part B).
"""
from __future__ import annotations

import pandas as pd

from swingbot.core.backtesting.screen.ideas import _range_breakdown as rb

CAP = 20
RACE = "fixed"
DIRECTION = "short"
ENTRY = "level"
PARAMS = {**rb.PARAMS, "trigger": "low[t] < S", "level": "S"}
SUMMARY = ("30-bar range (R - S <= 5 ATR14[t-1], two touches of each side "
           ">= 5 bars apart) in a falling SMA50 with the prior close below it; "
           "sell stop at S fills when low[t] < S (short, level entry)")
SOURCE = rb.SOURCE
FAMILY = rb.FAMILY


def levels(df: pd.DataFrame) -> pd.Series:
    """The sell stop's level for bar t: S over t-30..t-1."""
    return rb.support(df).rename("range_breakdown_stop_level")


def _trigger(df: pd.DataFrame) -> pd.Series:
    """Bar t trades below the resting level."""
    return df["Low"] < levels(df)


def events(df: pd.DataFrame) -> pd.Series:
    """Event on bar t: the frozen setup and a fill of the sell stop."""
    return (rb.setup(df) & _trigger(df)).rename("range_breakdown_stop")


def control_events(df: pd.DataFrame) -> pd.Series:
    """The trend-only control (spec Part C): same trigger and trend clauses,
    no range clauses. Printed by the results doc, never gating."""
    return (rb.control_setup(df) & _trigger(df)).rename("range_breakdown_stop_control")
```

In `swingbot/core/backtesting/screen/ideas/__init__.py`, append `"range_breakdown_stop"` to `IDEA_MODULES` after `"range_breakdown_close"`.

- [ ] **Step 4: Run the tests, the complexity gate and the goldens**

```bash
python scripts/dev/testrun.py file tests/backtesting/screen/test_idea_range_breakdown_stop.py
python scripts/dev/testrun.py file tests/backtesting/screen/test_idea_range_breakdown_close.py
python scripts/dev/testrun.py file tests/backtesting/screen/test_ideas_registry.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_idea.py
python scripts/dev/complexity_gate.py
python scripts/dev/testrun.py file tests/backtesting/screen/test_long_byte_identical.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_calibration_long_golden.py
```

Expected: `12 passed` for the stop file; the rest green.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/screen/ideas/range_breakdown_stop.py swingbot/core/backtesting/screen/ideas/__init__.py tests/backtesting/screen/test_idea_range_breakdown_stop.py tests/backtesting/screen/test_ideas_registry.py
git commit -m "feat(v182): register range_breakdown_stop (short, level entry at S, cap 20)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V182-16: `--count-only`, check 5 and the guardrail flag

**Model:** opus — the count must reuse the real event, drop, non-overlap and null-draw code without racing anything, and the guardrail change touches the one-shot rule every screen run passes through.

**Files:**
- Create: `swingbot/core/backtesting/screen/descriptive.py`
- Create: `tests/backtesting/screen/test_descriptive.py`
- Modify: `scripts/backtest/screen_idea.py` (module docstring :1-18; `_books` :128-145 as V182-11 left it; `screen_ticker` :203-226 as V182-11 left it; `build_parser` :387-403; `main` :773-795; new functions after `screen_universe`)
- Modify: `tests/backtest_scripts/test_screen_idea.py` (append)
- Modify: `.claude/hooks/guardrails.py` (`_SCREEN_OPTIONS` :308-309, `_screen_option_values` :373-389, `_screen_flags` :392-407, `_screen_deny_reason` :496-522)
- Modify: `tests/hooks/test_guardrails.py` (two flag-dict pins :593-607; append)

**Interfaces:**
- Consumes: `race.candidate_events(events, member, warm, cap, *, entry="next_open")`, `race.level_fills(df, event_pos, levels, atr, direction) -> (fill, depth)` (V182-9); `race.non_overlapping(event_pos, exit_pos)` (unchanged); `null.draw_groups(df, event_pos, eligible, k, seed, *, atr, trend, direction="long", depth=None) -> NullGroups` (fields `event_pos`, `dropped_no_match`, `null_slots`, `null_unfilled`, `null_depths`) (V182-10); `screen_idea.raw_levels(idea, df) -> np.ndarray | None` (V182-11); `null.K`, `null.null_seed`, `verdict.MIN_N = 300`; `IDEAS["range_breakdown_close"]`, `IDEAS["range_breakdown_stop"]` (V182-14/15).
- Produces:
  - `descriptive.DEPTH_MEDIAN_TOL = 0.05`, `descriptive.NULL_UNFILLED_MAX = 0.20`.
  - `descriptive.depth_summary(values) -> dict` — keys `n`, `q1`, `median`, `q3`, `gap_share` (share of depths exactly 0.0, i.e. gap fills at the open); `n = 0` and the rest `None` for no values.
  - `descriptive.check_fill_depth(event_depths, null_depths, null_slots, null_unfilled) -> tuple[bool, list[str]]` — pass iff `|median(null) − median(event)| ≤ 0.05` and `null_unfilled ≤ 0.20 × null_slots`; one line per clause.
  - `screen_idea.ticker_context(idea, df, spans, context=None) -> dict` — the `ctx` dict `screen_ticker` builds, moved out verbatim (keys at least `raw`, `member`, `warm`, `atr`, `trend`).
  - `screen_idea._null_pool(idea, ctx, exclude=None) -> np.ndarray` — the null eligibility `_books` builds, moved out verbatim.
  - `screen_idea.count_ticker(idea, ticker, df, spans) -> dict` — keys `ticker`, `counters` (`Counter` over `COUNTER_ORDER`), `raw`, `events`, `event_depths`, `null_depths`, `null_slots`, `null_unfilled`.
  - `screen_idea.count_universe(idea, universe, cache_dir, *, start=WINDOW_START, end=WINDOW_END, out=print) -> dict` — the per-ticker dicts summed, plus `tickers`, `members`, `missing`, `skipped`.
  - `screen_idea.count_refusal(args, idea) -> str | None`, `screen_idea.run_count(args) -> int`, `screen_idea.render_counts(idea, counts, args) -> str`.
  - Parser: `--count-only`, mutually exclusive with `--dry-run`.
  - Guardrail: `_SCREEN_FLAG_OPTIONS = ("--dry-run", "--count-only")`; `_SCREEN_OPTIONS` gains `"--count-only"`; `_screen_flags(...)` returns `flags["count_only"]`; `_screen_deny_reason` allows any count-only segment.
- Consumed by: V182-17 (`descriptive.py` grows the overlap, regime and control maths), V182-18 (runs `--count-only` for both ideas and copies the output into the counts note).

**What the count is, and why it is outcome-blind (spec Part C, Part B check 5):** the same `raw_events` → `candidate_events` (member, warm-up, window drops) → `non_overlapping` → `draw_groups` (null match, and in level mode the null fill depths) chain the real run uses, with one change: non-overlap uses the race-free exit bound `exit_pos = event_pos + cap` (every trade lasts the full cap; the race's last bar is `event_pos + cap`). That books no more events than the real run's actual exits would, so a count ≥ 300 is conservative. Nothing races: `race.race`, `trail.race_trail`, `run_book`, `matched_null` and `_books` are never called; no R, no verdict, no file, no ledger read or write. `draw_groups` decides null positions and (level mode) whether bar p trades through its copied level — bar p's own Low, no exit and no R.

- [ ] **Step 1: Write the failing `tests/backtesting/screen/test_descriptive.py`**

```python
"""v182 descriptive maths: depth summary and check 5 (outcome-blind, never reads R)."""
from swingbot.core.backtesting.screen import descriptive


def test_the_check_5_limits_are_the_spec_values():
    assert descriptive.DEPTH_MEDIAN_TOL == 0.05
    assert descriptive.NULL_UNFILLED_MAX == 0.20


def test_depth_summary_gives_quartiles_median_and_the_gap_fill_share():
    assert descriptive.depth_summary([0.0, 0.0, 0.5, 1.0, 2.0]) == {
        "n": 5, "q1": 0.0, "median": 0.5, "q3": 1.0, "gap_share": 0.4}


def test_depth_summary_of_nothing_is_empty():
    assert descriptive.depth_summary([]) == {
        "n": 0, "q1": None, "median": None, "q3": None, "gap_share": None}


def test_check_5_passes_inside_both_limits_and_at_the_unfilled_limit():
    # medians 0.25 vs 0.2734375 (|d| = 0.0234375); 20 of 100 unfilled = 20 %
    ok, lines = descriptive.check_fill_depth(
        [0.0, 0.25, 0.5], [0.0, 0.25, 0.296875, 0.5], null_slots=100, null_unfilled=20)
    assert ok is True
    assert lines == [
        "median depth: events 0.250 ATR, null 0.273 ATR, |difference| 0.023 <= 0.05 -> pass",
        "null_unfilled: 20 of 100 null slots (20.0%) <= 20% -> pass"]


def test_check_5_fails_on_a_median_gap_above_the_tolerance():
    ok, lines = descriptive.check_fill_depth([0.25], [0.3125], null_slots=10, null_unfilled=0)
    assert ok is False
    assert lines[0] == ("median depth: events 0.250 ATR, null 0.312 ATR, "
                        "|difference| 0.062 > 0.05 -> FAIL")
    assert lines[1].endswith("-> pass")


def test_check_5_fails_when_more_than_a_fifth_of_null_slots_go_unfilled():
    ok, lines = descriptive.check_fill_depth([0.25], [0.25], null_slots=100, null_unfilled=21)
    assert ok is False
    assert lines[1] == "null_unfilled: 21 of 100 null slots (21.0%) > 20% -> FAIL"


def test_check_5_fails_with_no_event_depth_no_null_fill_or_no_slots():
    assert descriptive.check_fill_depth([], [0.1], 10, 0) == (
        False, ["median depth: no event depths -> FAIL",
                "null_unfilled: 0 of 10 null slots (0.0%) <= 20% -> pass"])
    ok, lines = descriptive.check_fill_depth([0.1], [], 10, 10)
    assert ok is False and lines[0] == "median depth: no filled null -> FAIL"
    ok, lines = descriptive.check_fill_depth([0.1], [0.1], 0, 0)
    assert ok is False and lines[1] == "null_unfilled: no null slots -> FAIL"
```

- [ ] **Step 2: Write the failing tests in `tests/backtest_scripts/test_screen_idea.py`**

Add `race` and `trail` to the existing screen import (`from swingbot.core.backtesting.screen import forward, null, race, trail, verdict`) and append:

```python
# --- v182: --count-only (outcome-blind count before the shot) -------------

CLOSE = IDEAS["range_breakdown_close"]
STOP = IDEAS["range_breakdown_stop"]


def _spy(calls, name, fn):
    def wrapped(*args, **kwargs):
        calls.setdefault(name, []).append((args, kwargs))
        return fn(*args, **kwargs)
    return wrapped


def _boom(*args, **kwargs):
    raise AssertionError("--count-only must never race")


def test_count_ticker_races_nothing_and_shares_the_real_drop_and_overlap_code(monkeypatch):
    calls = {}
    monkeypatch.setattr(race, "candidate_events", _spy(calls, "cand", race.candidate_events))
    monkeypatch.setattr(race, "non_overlapping", _spy(calls, "overlap", race.non_overlapping))
    monkeypatch.setattr(null, "draw_groups", _spy(calls, "draw", null.draw_groups))
    monkeypatch.setattr(screen_idea, "raw_events", _spy(calls, "raw", screen_idea.raw_events))
    for owner, name in ((race, "race"), (race, "run_book"), (trail, "race_trail"),
                        (null, "matched_null"), (screen_idea, "_books")):
        monkeypatch.setattr(owner, name, _boom)
    out = screen_idea.count_ticker(CLOSE, "AAA", random_walk(2700, seed=7), ALWAYS)
    assert out["raw"] > 0 and out["events"] > 0                 # non-vacuous
    assert len(calls["raw"]) == 1
    (_, cand_kwargs), = calls["cand"]
    assert cand_kwargs["entry"] == "next_open"
    (overlap_args, _), = calls["overlap"]
    np.testing.assert_array_equal(overlap_args[1], overlap_args[0] + CLOSE.time_cap_bars)
    (draw_args, draw_kwargs), = calls["draw"]
    assert draw_args[3] == null.K
    assert draw_args[4] == null.null_seed("range_breakdown_close", "AAA")
    assert draw_kwargs["direction"] == "short" and draw_kwargs["depth"] is None


def test_count_ticker_drop_counters_match_the_real_run():
    df = random_walk(2700, seed=3)
    spans = [("2012-01-01", "2016-12-31")]
    idea = IDEAS["turn_of_month"]
    real = screen_idea.screen_ticker(idea, "AAA", df, spans)
    out = screen_idea.count_ticker(idea, "AAA", df, spans)
    for key in ("dropped_nonmember", "dropped_warmup", "dropped_window"):
        assert out["counters"][key] == real.counters[key], key
    assert out["counters"]["dropped_nonmember"] > 0
    assert set(out["counters"]) == set(screen_idea.COUNTER_ORDER)
    # The full-cap bound books no more events than the real exits do.
    assert out["counters"]["skipped_overlap"] >= real.counters["skipped_overlap"]
    assert (out["events"] + out["counters"]["dropped_no_match"]
            <= len(real.events) + real.counters["dropped_no_match"])
    assert out["event_depths"] == [] and out["null_depths"] == []


def test_count_ticker_in_level_mode_reports_the_fill_depths():
    out = screen_idea.count_ticker(STOP, "AAA", random_walk(2700, seed=7), ALWAYS)
    assert out["events"] > 0
    assert len(out["event_depths"]) == out["events"]
    assert all(d >= 0.0 for d in out["event_depths"])
    assert out["null_slots"] > 0
    # V182-10: null_unfilled = slots left unfilled; one depth per filled slot.
    assert out["null_slots"] - out["null_unfilled"] == len(out["null_depths"])


def test_count_ticker_is_deterministic():
    df = random_walk(2700, seed=7)
    assert (screen_idea.count_ticker(STOP, "AAA", df, ALWAYS)
            == screen_idea.count_ticker(STOP, "AAA", df, ALWAYS))


def _counts(n, **extra):
    base = {"tickers": 2, "members": 3, "missing": 1, "skipped": Counter(),
            "counters": Counter({"dropped_warmup": 4}), "raw": n + 4, "events": n,
            "event_depths": [], "null_depths": [], "null_slots": 0, "null_unfilled": 0}
    base.update(extra)
    return base


def _count_args(idea):
    return screen_idea.build_parser().parse_args(["--idea", idea, "--count-only"])


def test_render_counts_gates_on_300_events():
    args = _count_args("range_breakdown_close")
    assert ("**Gate:** N = 300 ≥ 300: the one shot may run."
            in screen_idea.render_counts(CLOSE, _counts(300), args))
    assert ("**Gate:** N = 299 < 300: no run, no ledger row; report to the partner."
            in screen_idea.render_counts(CLOSE, _counts(299), args))


def test_render_counts_prints_check_5_for_a_level_idea_only():
    args = _count_args("range_breakdown_stop")
    assert "Check 5" not in screen_idea.render_counts(CLOSE, _counts(300), args)
    good = _counts(300, event_depths=[0.0, 0.25, 0.5],
                   null_depths=[0.0, 0.25, 0.296875, 0.5], null_slots=100, null_unfilled=20)
    text = screen_idea.render_counts(STOP, good, args)
    assert "## Check 5" in text and "**Check 5:** PASS" in text
    assert "| events | 3 | 0.125 | 0.250 | 0.375 | 33.3% |" in text
    bad = _counts(300, event_depths=[0.25], null_depths=[0.3125],
                  null_slots=100, null_unfilled=21)
    assert "**Check 5:** FAIL" in screen_idea.render_counts(STOP, bad, args)


def test_render_counts_names_no_outcome():
    text = screen_idea.render_counts(
        STOP, _counts(300, event_depths=[0.1], null_depths=[0.1], null_slots=5), _count_args(
            "range_breakdown_stop"))
    assert text.startswith("# v182 count: `range_breakdown_stop` (outcome-blind: no race, no R)")
    for word in ("ExpR", "R_event", "R_null", "SCREEN-PASS", "SCREEN-FAIL", "lower 95"):
        assert word not in text, word


def test_count_only_prints_the_counts_and_writes_nothing(tmp_path, capsys):
    cache, membership = _universe_fixture(tmp_path)
    assert screen_idea.main(_argv(tmp_path, cache, membership, "--count-only",
                                  idea="range_breakdown_stop")) == 0
    out = capsys.readouterr().out
    assert "# v182 count: `range_breakdown_stop`" in out
    for needle in ("| raw events |", "| dropped_warmup |", "| skipped_overlap (full-cap bound) |",
                   "| dropped_no_match |", "< 300: no run, no ledger row", "## Check 5"):
        assert needle in out, needle
    assert not (tmp_path / "ledger.jsonl").exists()
    assert not (tmp_path / "results").exists()


def test_count_only_runs_for_an_idea_already_in_the_ledger_and_changes_nothing(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    stats.append_ledger_row(
        {"id": "screen-range_breakdown_close", "date": "2026-10-09", "hypothesis": "x",
         "instrument": "screen-v1", "n": 1, "exp_r": 0.0, "p": 0.5,
         "verdict": "SCREEN-FAIL", "record": "docs/x.md"}, path=ledger)
    before = ledger.read_bytes()
    cache, membership = _universe_fixture(tmp_path)
    assert screen_idea.main(_argv(tmp_path, cache, membership, "--count-only",
                                  idea="range_breakdown_close")) == 0
    assert ledger.read_bytes() == before
    assert not (tmp_path / "results").exists()


@pytest.mark.parametrize("extra, idea, needle", [
    (("--end", "2020-01-02"), "range_breakdown_close", "never reads 2020+"),
    (("--start", "2012-01-01"), "range_breakdown_close", "pre-registered window"),
    (("--tickers", "AAA"), "range_breakdown_close", "--tickers belongs to a --dry-run"),
    ((), "dollar_drop", "without context series"),
])
def test_count_only_refusals(tmp_path, capsys, extra, idea, needle):
    cache, membership = _universe_fixture(tmp_path)
    assert screen_idea.main(_argv(tmp_path, cache, membership, "--count-only", *extra,
                                  idea=idea)) == 2
    assert needle in capsys.readouterr().err


def test_count_only_beside_dry_run_is_an_argparse_error(tmp_path):
    cache, membership = _universe_fixture(tmp_path)
    with pytest.raises(SystemExit):
        screen_idea.main(_argv(tmp_path, cache, membership, "--count-only", "--dry-run"))
```

- [ ] **Step 3: Write the failing guardrail tests in `tests/hooks/test_guardrails.py`**

In `test_screen_flags_read_every_checked_option` and `test_screen_flags_resolve_unique_abbreviations_like_argparse`, add `"count_only": False` to the expected dict. Append after the v155 `_rule_screen_rerun` tests:

```python
# --- v182: --count-only is a valueless, outcome-blind flag ------------------

def test_screen_flags_read_count_only_and_its_unique_abbreviation():
    for spelling in ("--count-only", "--cou"):
        flags = guardrails._screen_flags(["python", "screen_idea.py", "--idea", "x", spelling])
        assert flags["count_only"] is True and flags["dry_run"] is False, spelling
    assert guardrails._SCREEN_FLAG_OPTIONS == ("--dry-run", "--count-only")


def test_count_only_takes_no_value():
    flags = guardrails._screen_flags(["python", "screen_idea.py", "--count-only",
                                      "--idea", "x"])
    assert flags["count_only"] is True and flags["idea"] == "x"


def test_a_bare_c_is_ambiguous_between_cache_dir_and_count_only():
    flags = guardrails._screen_flags(["python", "screen_idea.py", "--idea", "x", "--c"])
    assert flags["count_only"] is False


def test_a_full_universe_count_is_allowed(screen_repo):
    assert _bash(f"{_SCREEN} --idea range_breakdown_stop --count-only") is None


def test_a_count_of_a_screened_idea_is_allowed(screen_repo):
    _screened(screen_repo, "range_breakdown_close")
    assert _bash(f"{_SCREEN} --idea range_breakdown_close --count-only") is None


def test_a_real_run_beside_a_count_is_still_denied(screen_repo):
    _screened(screen_repo)
    _screen_denial(f"{_SCREEN} --idea gap_volume --count-only && {_SCREEN} --idea gap_volume")
```

- [ ] **Step 4: Run them to verify they fail**

```bash
python scripts/dev/testrun.py file tests/backtesting/screen/test_descriptive.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_idea.py
python scripts/dev/testrun.py file tests/hooks/test_guardrails.py
```

Expected: FAIL — `ImportError: cannot import name 'descriptive'`; `AttributeError: module 'screen_idea' has no attribute 'count_ticker'` and argparse `unrecognized arguments: --count-only`; `KeyError: 'count_only'` and `AttributeError: ... '_SCREEN_FLAG_OPTIONS'` in the hook tests (the two edited dict pins fail on the missing key). `test_a_real_run_beside_a_count_is_still_denied` may already pass; that is expected.

- [ ] **Step 5: Implement `swingbot/core/backtesting/screen/descriptive.py`**

```python
"""v182 descriptive maths for short and level ideas: pure, never reads R.

Check 5 (spec Part B) is the only function here that decides anything, and it
decides only whether range_breakdown_stop may be run at all: it compares the
fill depths of the events with those of their matched null, outcome-blind,
inside --count-only. V182-17 adds the results-doc blocks (overlap, SPY
regime split, trend-only control), all printed and never gating.
"""
from __future__ import annotations

import numpy as np

#: |median null depth - median event depth| allowed, in ATR14[t-1] (check 5).
DEPTH_MEDIAN_TOL = 0.05
#: Share of null slots left unfilled allowed (check 5).
NULL_UNFILLED_MAX = 0.20

_EMPTY = {"n": 0, "q1": None, "median": None, "q3": None, "gap_share": None}


def depth_summary(values) -> dict:
    """Quartiles, median and the share of gap fills (depth exactly 0)."""
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        return dict(_EMPTY)
    q1, median, q3 = np.percentile(arr, [25, 50, 75])
    return {"n": int(arr.size), "q1": float(q1), "median": float(median),
            "q3": float(q3), "gap_share": float(np.mean(arr == 0.0))}


def _verdict(ok: bool) -> str:
    return "pass" if ok else "FAIL"


def _depth_clause(event_depths, null_depths) -> tuple[bool, str]:
    events, nulls = depth_summary(event_depths), depth_summary(null_depths)
    if events["n"] == 0:
        return False, "median depth: no event depths -> FAIL"
    if nulls["n"] == 0:
        return False, "median depth: no filled null -> FAIL"
    gap = abs(nulls["median"] - events["median"])
    ok = gap <= DEPTH_MEDIAN_TOL
    return ok, (f"median depth: events {events['median']:.3f} ATR, null "
                f"{nulls['median']:.3f} ATR, |difference| {gap:.3f} "
                f"{'<=' if ok else '>'} {DEPTH_MEDIAN_TOL} -> {_verdict(ok)}")


def _unfilled_clause(null_slots: int, null_unfilled: int) -> tuple[bool, str]:
    if null_slots <= 0:
        return False, "null_unfilled: no null slots -> FAIL"
    share = null_unfilled / null_slots
    ok = share <= NULL_UNFILLED_MAX
    return ok, (f"null_unfilled: {null_unfilled} of {null_slots} null slots "
                f"({100.0 * share:.1f}%) {'<=' if ok else '>'} "
                f"{100.0 * NULL_UNFILLED_MAX:.0f}% -> {_verdict(ok)}")


def check_fill_depth(event_depths, null_depths, null_slots: int,
                     null_unfilled: int) -> tuple[bool, list[str]]:
    """Check 5: the null's median fill depth within DEPTH_MEDIAN_TOL ATR of
    the events', and at most NULL_UNFILLED_MAX of the null slots unfilled."""
    depth_ok, depth_line = _depth_clause(event_depths, null_depths)
    fill_ok, fill_line = _unfilled_clause(null_slots, null_unfilled)
    return depth_ok and fill_ok, [depth_line, fill_line]
```

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_descriptive.py` — Expected: `7 passed`.

- [ ] **Step 6: Implement the count in `scripts/backtest/screen_idea.py`**

Read `_books` and `screen_ticker` as V182-11 left them first; both refactors below are moves, not rewrites.

1. **`ticker_context(idea, df, spans, context=None) -> dict`** (place it just above `screen_ticker`): move every statement of `screen_ticker` that builds `atr`, `sma200`, `member`, `warm` and `ctx` — including any key V182-11 added for level ideas — into it, returning `ctx`. `screen_ticker` then starts with `ctx = ticker_context(idea, df, spans, context)` and uses `ctx["atr"]`, `ctx["member"]`, `ctx["warm"]` wherever it used those locals (forward returns, `_rank_frame`'s `member & warm`). Docstring: `"""Per-ticker inputs every screen path shares: raw events, membership, warm-up, ATR14 and the null's trend state (v182: moved out of screen_ticker so --count-only reads the same ones)."""`
2. **`_null_pool(idea, ctx, exclude=None) -> np.ndarray`**: move the lines of `_books` that build `eligible` (the `null.eligible_mask(...)` call and the `exclude` step, exactly as V182-11 left them) into it; `_books` calls `eligible = _null_pool(idea, ctx, exclude)`.
3. Add after `screen_universe`:

```python
def _count_depths(idea: Idea, df: pd.DataFrame, ctx: dict, booked: np.ndarray):
    """Level ideas: each booked event's fill depth in ATR14[t-1], from the
    function the real run fills with (race.level_fills); None for next_open."""
    levels = raw_levels(idea, df)
    if levels is None:
        return None
    _, depth = race.level_fills(df, booked, levels, ctx["atr"], idea.direction)
    return np.asarray(depth, dtype=float)


def count_ticker(idea: Idea, ticker: str, df: pd.DataFrame, spans) -> dict:
    """v182 --count-only for one ticker: the real run's events, drops and
    null draw, with a race-free exit bound (every trade lasts the full cap).
    Nothing is raced; no R is computed."""
    ctx = ticker_context(idea, df, spans)
    cap = idea.time_cap_bars
    cand, counts = race.candidate_events(ctx["raw"], ctx["member"], ctx["warm"], cap,
                                         entry=idea.entry)
    keep = race.non_overlapping(cand, cand + cap)
    counts["skipped_overlap"] = int((~keep).sum())
    booked = cand[keep]
    depth = _count_depths(idea, df, ctx, booked)
    groups = null.draw_groups(df, booked, _null_pool(idea, ctx), null.K,
                              null.null_seed(idea.name, ticker), atr=ctx["atr"],
                              trend=ctx["trend"], direction=idea.direction, depth=depth)
    counts["dropped_no_match"] = groups.dropped_no_match
    matched = np.isin(booked, groups.event_pos)
    return {"ticker": ticker, "counters": Counter(counts),
            "raw": int(np.count_nonzero(ctx["raw"])), "events": int(matched.sum()),
            "event_depths": [] if depth is None else [float(d) for d in depth[matched]],
            "null_depths": [float(d) for d in groups.null_depths],
            "null_slots": int(groups.null_slots), "null_unfilled": int(groups.null_unfilled)}
```

   `Counter(counts)` keeps every `COUNTER_ORDER` key, zeros included (the test checks the key set).
4. **`count_universe(idea, universe, cache_dir, *, start=WINDOW_START, end=WINDOW_END, out=print) -> dict`**: the `screen_universe` loop over `universe.cached` (same `load_frame`, same `skipped["empty_frame"]`, same progress line and cadence), calling `count_ticker(idea, ticker, df, universe.intervals.get(ticker, []))` and folding each result into one dict with a helper `_add_count(total: dict, one: dict) -> None` (`tickers += 1`; `counters.update`; `raw`, `events`, `null_slots`, `null_unfilled` summed; `event_depths`, `null_depths` extended). The returned dict starts as `{"tickers": 0, "members": len(universe.members), "missing": len(universe.missing), "skipped": Counter(), "counters": Counter(), "raw": 0, "events": 0, "event_depths": [], "null_depths": [], "null_slots": 0, "null_unfilled": 0}`.
5. **`render_counts(idea, counts, args) -> str`**, built from three helpers so each stays small. Exact text (the tests pin the marked lines; `_cell(v)` prints `f"{v:.3f}"`, or `–` for `None`; the gap share prints `f"{100 * v:.1f}%"`):

```text
# v182 count: `<name>` (outcome-blind: no race, no R)

**Window:** <start>..<end> (events from 2011-01-01). **Universe:** <members> PIT S&P 500 members, <tickers> counted, <missing> missing from the cache, <sum skipped> empty frames.
**Idea:** <direction>, entry <entry>, <race_shape> race, cap <cap> bars.
**Command:** `python scripts/backtest/screen_idea.py --idea <name> --count-only`

| step | events |
|---|---:|
| raw events | <raw> |
| dropped_nonmember | <n> |
| dropped_warmup | <n> |
| dropped_window | <n> |
| skipped_overlap (full-cap bound) | <n> |
| dropped_no_match | <n> |
| **count N** | **<events>** |

Non-overlap here assumes every trade lasts the full <cap>-bar cap, so the real run books at least as many events before the null match.

**Gate:** N = <n> ≥ 300: the one shot may run.
   (or)  **Gate:** N = <n> < 300: no run, no ledger row; report to the partner.
```

   For `idea.entry == "level"` only, append:

```text

## Check 5 — fill depth (outcome-blind)

| depth (ATR14[t−1]) | n | q1 | median | q3 | gap fills |
|---|---:|---:|---:|---:|---:|
| events | <n> | <q1> | <median> | <q3> | <gap_share> |
| null fills | <n> | <q1> | <median> | <q3> | <gap_share> |

- <line 1 of check_fill_depth>
- <line 2>

**Check 5:** PASS -- <name> may run.
   (or)  **Check 5:** FAIL -- <name> is not run; tell the partner.
```

   The 300 is `verdict.MIN_N`; the event start is `EVENT_START`. Helpers: `_count_table(counts) -> list[str]`, `_count_gate(n) -> str`, `_check5_block(idea, counts) -> list[str]` (calls `descriptive.check_fill_depth` and `descriptive.depth_summary`); import `descriptive` beside `diagnostics`.
6. **`count_refusal(args, idea) -> str | None`** — checked before any data is read, never reads the ledger:
   - `args.end > WINDOW_END` → `f"window end {args.end} is after {WINDOW_END}; the screen never reads 2020+"`;
   - `(args.start, args.end) != (WINDOW_START, WINDOW_END)` → `f"--count-only counts the pre-registered window {WINDOW_START}..{WINDOW_END} only, not {args.start}..{args.end}"`;
   - `args.tickers` → `"--count-only counts the whole universe; --tickers belongs to a --dry-run smoke test"`;
   - `idea.context` → `f"--count-only counts ideas without context series; {idea.name} reads {', '.join(idea.context)}"`.
7. **`run_count(args) -> int`**: `idea = IDEAS[args.idea]`; `count_refusal`, then `load_universe(args.cache_dir, args.membership, args.start, args.end)` (a `ValueError` is a refusal); on refusal print `refused: <reason>` to stderr and return 2; else `print(render_counts(idea, count_universe(idea, universe, args.cache_dir, start=args.start, end=args.end), args))` and return 0.
8. **`build_parser`**: replace the `--dry-run` line with a mutually exclusive group holding `--dry-run` (same help) and `--count-only` (`action="store_true"`, help `"v182: count events, drops and full-cap non-overlap (and check 5 for a level idea); no race, no R, writes nothing"`).
9. **`main`**: right after `_utf8_stdout()`, `if args.count_only: return run_count(args)` — before the ledger is loaded.
10. Module docstring: append `--count-only (v182) prints the event count before the shot (the real events, drops and null draw, full-cap non-overlap) and, for a level idea, check 5; it races nothing, writes nothing and never reads the ledger.`

- [ ] **Step 7: Implement the guardrail flag in `.claude/hooks/guardrails.py`**

```python
#: Valueless screen flags (v182: --count-only beside --dry-run).
_SCREEN_FLAG_OPTIONS = ("--dry-run", "--count-only")
_SCREEN_OPTIONS = ("--idea", "--cache-dir", "--membership", "--start", "--end",
                   "--date", "--ledger", "--results-dir", "--tickers",
                   *_SCREEN_FLAG_OPTIONS)
```

- `_screen_option_values`: `if opt in _SCREEN_FLAG_OPTIONS or eq:` replaces `if opt == "--dry-run" or eq:`; docstring "value is None for a valueless flag (--dry-run, --count-only) and for an option with no value after it".
- `_screen_flags`: the initial dict gains `"count_only": False`; replace the `if opt == "--dry-run": flags["dry_run"] = True` branch with `if opt in _SCREEN_FLAG_OPTIONS: flags[opt[2:].replace("-", "_")] = True` (the `elif` chain after it is unchanged).
- `_screen_deny_reason`: first statement

```python
    if flags["count_only"]:
        return None   # v182: counts only -- no race, no R, writes nothing, any idea
```

  and add to its docstring: `A --count-only segment is allowed first: it races nothing and writes nothing (screen_idea.py refuses it beside --dry-run).`

The hook file is shared verbatim with Codex through `.codex/hooks.json`, so there is no mirror file to edit.

- [ ] **Step 8: Run every touched test file, the complexity gate and the goldens**

```bash
python scripts/dev/testrun.py file tests/backtesting/screen/test_descriptive.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_idea.py
python scripts/dev/testrun.py file tests/hooks/test_guardrails.py
python scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py
python scripts/dev/testrun.py file tests/backtesting/screen/test_null_level.py
python scripts/dev/complexity_gate.py
python scripts/dev/testrun.py file tests/backtesting/screen/test_long_byte_identical.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_calibration_long_golden.py
```

Expected: all green; the complexity gate reports no regression (`count_ticker`, `render_counts` and `_screen_flags` each stay well under 15). The long golden proves the `ticker_context` / `_null_pool` moves changed nothing.

Then one smoke on the real cache, outcome-blind and allowed by the hook (`--count-only` writes nothing): `python scripts/backtest/screen_idea.py --idea range_breakdown_stop --count-only --cache-dir E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext | tail -25` (the cache exists only in the main tree) — Expected: exit 0, the count table, the gate line and the check 5 block. Do **not** record or act on the numbers here; V182-18 runs both counts for the note once every code change is committed.

- [ ] **Step 9: Commit**

```bash
git add swingbot/core/backtesting/screen/descriptive.py tests/backtesting/screen/test_descriptive.py scripts/backtest/screen_idea.py tests/backtest_scripts/test_screen_idea.py .claude/hooks/guardrails.py tests/hooks/test_guardrails.py
git commit -m "feat(v182): --count-only event count with check 5, guardrail allows it

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

