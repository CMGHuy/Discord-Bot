# v140 Idea screen: Implementation Plan, part 2 — null, forward drift, the four triggers

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Header, Global Constraints, Review Focus, Frozen readings and Parallelisation live in [`_0-index`](2026-10-08-v140-idea-screen_0-index.md); every task here implicitly includes them. Work only in the worktree `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-08-v140-idea-screen`.

**Spec:** [`docs/superpowers/specs/2026-10-08-v140-idea-screen-design.md`](../../specs/implemented/2026-10-08-v140-idea-screen-design.md)

# Phase 2 — Group A (parallel after V140-3)

All six tasks below touch disjoint files and consume only V140-1..3. They may be dispatched together. None of them edits `ideas/__init__.py`.

### Task V140-4: Matched null baseline

**Files:**
- Create: `swingbot/core/backtesting/screen/null.py`
- Test: `tests/backtesting/screen/test_null.py`

**Interfaces:**
- Consumes: `race.race(df, event_pos, cap, *, atr=None, slippage_bps=None, commission=None) -> RaceResult`, `race.RaceResult.empty()` (V140-3); `pit_membership.is_member(date, spans)` semantics (existing, used by the test as the oracle).
- Produces:
  - Constants `K = 20`, `MIN_CANDIDATES = 5`, `SEED_BASE = 42`.
  - `null_seed(idea: str, ticker: str, base: int = SEED_BASE) -> list[int]` = `[base, zlib.crc32(idea.encode()), zlib.crc32(ticker.encode())]`.
  - `member_mask(index, spans) -> np.ndarray[bool]` — vectorised `is_member`; `spans=None` is all True, `[]` all False.
  - `trend_state(df, sma200) -> np.ndarray[bool]` — `close > SMA200`; NaN SMA is False.
  - `month_key(index) -> np.ndarray[int]` — `year * 12 + month`.
  - `eligible_mask(events, member, warm, cap) -> np.ndarray[bool]` — member, warm, race completes inside the frame, not an event bar.
  - `candidates(pos, eligible, months, trend) -> np.ndarray[int]`.
  - `NullDraw` — frozen dataclass: `event_pos: np.ndarray` (events that found ≥ 5 candidates, in input order), `groups: tuple[np.ndarray, ...]` (sorted drawn positions per kept event), `null_mean_r: np.ndarray` (net R mean per kept event), `null_race: RaceResult` (every null race, for the outcome mix), `dropped_no_match: int`.
  - `matched_null(df, event_pos, eligible, k, seed, *, cap, atr, trend, slippage_bps=None, commission=None) -> NullDraw`.

- [ ] **Step 1: Invoke `no-lookahead`, then write the failing tests**

`tests/backtesting/screen/test_null.py`:

```python
"""v140 matched null: same ticker, same month, same trend state, K = 20,
fewer than 5 candidates drops the event, never an event bar."""
import zlib

import numpy as np
import pandas as pd
import pytest

from swingbot.core.backtesting.screen import null
from swingbot.core.backtesting.screen import race as race_mod
from swingbot.core.marketdata.pit_membership import is_member
from tests.backtesting.screen.helpers import frame, random_walk

FEB_2019 = 2019 * 12 + 2


def _three_months():
    idx = pd.bdate_range("2019-01-01", "2019-03-29")
    return frame(np.full(len(idx), 100.0), index=idx)


def _atr(df):
    return pd.Series(2.0, index=df.index)


def _all(df):
    return np.ones(len(df), dtype=bool)


def _draw(df, event_pos, eligible, k, seed, trend=None):
    trend = _all(df) if trend is None else trend
    return null.matched_null(df, event_pos, eligible, k, seed, cap=4,
                             atr=_atr(df), trend=trend, slippage_bps=0.0,
                             commission=0.0)


def test_seed_is_deterministic_per_idea_and_ticker():
    assert null.null_seed("high52w", "AAPL") == [
        42, zlib.crc32(b"high52w"), zlib.crc32(b"AAPL")]
    assert null.null_seed("high52w", "AAPL") != null.null_seed("high52w", "MSFT")
    assert null.null_seed("high52w", "AAPL") != null.null_seed("gap_volume", "AAPL")


def test_month_key_and_trend_state():
    idx = pd.DatetimeIndex(["2019-01-31", "2019-02-01", "2019-02-04"])
    assert null.month_key(idx).tolist() == [2019 * 12 + 1, FEB_2019, FEB_2019]
    df = frame([1.0, 2.0, 3.0], index=idx)
    sma = pd.Series([np.nan, 1.5, 3.0], index=idx)
    assert null.trend_state(df, sma).tolist() == [False, True, False]


def test_member_mask_matches_is_member_bar_by_bar():
    idx = pd.bdate_range("2011-12-20", "2012-01-20")
    spans = [("2011-12-28", "2012-01-05"), ("2012-01-12", "9999-12-31")]
    expected = [is_member(d.strftime("%Y-%m-%d"), spans) for d in idx]
    assert null.member_mask(idx, spans).tolist() == expected
    assert null.member_mask(idx, None).all()
    assert not null.member_mask(idx, []).any()


def test_eligible_mask_needs_member_warm_complete_and_not_an_event():
    events = np.array([0, 1, 0, 0, 0, 0], dtype=bool)
    member = np.array([1, 1, 0, 1, 1, 1], dtype=bool)
    warm = np.array([1, 1, 1, 0, 1, 1], dtype=bool)
    out = null.eligible_mask(events, member, warm, cap=2)
    assert out.tolist() == [True, False, False, False, False, False]


def test_draws_match_month_and_trend_state():
    df = _three_months()
    trend = np.arange(len(df)) % 2 == 0
    events = np.zeros(len(df), dtype=bool)
    events[[4, 30]] = True
    eligible = null.eligible_mask(events, _all(df), _all(df), cap=4)
    draw = _draw(df, [4, 30], eligible, 20, [42, 1, 2], trend=trend)
    months = null.month_key(df.index)
    assert draw.event_pos.tolist() == [4, 30]
    for pos, group in zip(draw.event_pos, draw.groups):
        assert (months[group] == months[pos]).all()
        assert (trend[group] == trend[pos]).all()


def test_null_never_samples_an_event_bar():
    df = _three_months()
    events = np.zeros(len(df), dtype=bool)
    events[[2, 5, 6, 9, 12, 15]] = True
    eligible = null.eligible_mask(events, _all(df), _all(df), cap=4)
    assert not eligible[events].any()
    for seed in range(50):
        draw = _draw(df, [2, 9], eligible, 5, seed)
        drawn = np.concatenate(draw.groups)
        assert not np.isin(drawn, np.flatnonzero(events)).any()


def test_same_seed_gives_the_same_draw():
    df = _three_months()
    eligible = null.eligible_mask(np.zeros(len(df), dtype=bool), _all(df), _all(df), cap=4)
    a = _draw(df, [3, 30], eligible, 5, null.null_seed("x", "AAPL"))
    b = _draw(df, [3, 30], eligible, 5, null.null_seed("x", "AAPL"))
    assert all(np.array_equal(g, h) for g, h in zip(a.groups, b.groups))


def test_fewer_than_five_candidates_drops_the_event():
    df = _three_months()
    feb = np.flatnonzero(null.month_key(df.index) == FEB_2019)
    eligible = np.zeros(len(df), dtype=bool)
    eligible[feb[:4]] = True
    dropped = _draw(df, [feb[10]], eligible, 20, 1)
    assert dropped.dropped_no_match == 1
    assert dropped.event_pos.size == 0 and dropped.null_mean_r.size == 0
    eligible[feb[4]] = True
    kept = _draw(df, [feb[10]], eligible, 20, 1)
    assert kept.dropped_no_match == 0
    assert kept.event_pos.tolist() == [feb[10]]
    assert len(kept.groups[0]) == 5


def test_draw_size_is_k_or_every_candidate_when_fewer():
    df = _three_months()
    feb = np.flatnonzero(null.month_key(df.index) == FEB_2019)
    eligible = np.zeros(len(df), dtype=bool)
    eligible[feb[:12]] = True
    assert len(_draw(df, [feb[15]], eligible, 20, 1).groups[0]) == 12
    assert len(_draw(df, [feb[15]], eligible, 5, 1).groups[0]) == 5


def test_null_mean_is_the_mean_of_its_raced_bars():
    df = random_walk(70, start="2019-01-01")
    eligible = null.eligible_mask(np.zeros(len(df), dtype=bool), _all(df), _all(df), cap=4)
    draw = _draw(df, [5], eligible, 20, 3)
    expected = race_mod.race(df, draw.groups[0], 4, atr=_atr(df),
                             slippage_bps=0.0, commission=0.0).r.mean()
    assert draw.null_mean_r[0] == pytest.approx(expected)
    assert len(draw.null_race) == len(draw.groups[0])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_null.py`
Expected: FAIL — `ImportError: cannot import name 'null'`.

- [ ] **Step 3: Write `null.py`**

`swingbot/core/backtesting/screen/null.py`:

```python
"""Matched random baseline for the v140 screen (spec § The matched baseline).

Eligible bar: member at t, warm-up complete, race completes inside the
frame, t not an event bar (any raw event, kept or not). Per event: draw
min(K, candidates) eligible bars without replacement from the same ticker,
same YYYY-MM, same trend state (close > SMA200); fewer than 5 candidates
drops the event. Null bars are not subject to the one-open-race rule: they
are a counterfactual, not a book.
"""
from __future__ import annotations

import zlib
from dataclasses import dataclass

import numpy as np
import pandas as pd

from swingbot.core.backtesting.screen import race as race_mod

K = 20
MIN_CANDIDATES = 5
SEED_BASE = 42


def null_seed(idea: str, ticker: str, base: int = SEED_BASE) -> list:
    """Deterministic per (idea, ticker), derived from 42."""
    return [base, zlib.crc32(idea.encode()), zlib.crc32(ticker.encode())]


def member_mask(index, spans) -> np.ndarray:
    """``pit_membership.is_member`` for every bar: [start, end) ISO spans."""
    days = np.asarray(pd.DatetimeIndex(index).strftime("%Y-%m-%d"))
    if spans is None:
        return np.ones(len(days), dtype=bool)
    out = np.zeros(len(days), dtype=bool)
    for start, end in spans:
        out |= (days >= start) & (days < end)
    return out


def trend_state(df: pd.DataFrame, sma200) -> np.ndarray:
    return (df["Close"] > sma200).to_numpy(dtype=bool)


def month_key(index) -> np.ndarray:
    index = pd.DatetimeIndex(index)
    return np.asarray(index.year * 12 + index.month)


def eligible_mask(events, member, warm, cap: int) -> np.ndarray:
    events = np.asarray(events, dtype=bool)
    complete = np.arange(len(events)) + cap <= len(events) - 1
    return (np.asarray(member, dtype=bool) & np.asarray(warm, dtype=bool)
            & complete & ~events)


def candidates(pos: int, eligible, months, trend) -> np.ndarray:
    return np.flatnonzero(eligible & (months == months[pos]) & (trend == trend[pos]))


@dataclass(frozen=True, eq=False)
class NullDraw:
    event_pos: np.ndarray
    groups: tuple
    null_mean_r: np.ndarray
    null_race: race_mod.RaceResult
    dropped_no_match: int


def _empty(dropped: int) -> NullDraw:
    return NullDraw(np.array([], dtype=int), (), np.array([], dtype=float),
                    race_mod.RaceResult.empty(), dropped)


def matched_null(df, event_pos, eligible, k: int, seed, *, cap: int, atr,
                 trend, slippage_bps=None, commission=None) -> NullDraw:
    rng = np.random.default_rng(seed)
    months = month_key(df.index)
    kept, groups, dropped = [], [], 0
    for pos in np.asarray(event_pos, dtype=int):
        pool = candidates(pos, eligible, months, trend)
        if len(pool) < MIN_CANDIDATES:
            dropped += 1
            continue
        kept.append(pos)
        groups.append(np.sort(rng.choice(pool, size=min(k, len(pool)), replace=False)))
    if not kept:
        return _empty(dropped)
    raced = race_mod.race(df, np.concatenate(groups), cap, atr=atr,
                          slippage_bps=slippage_bps, commission=commission)
    bounds = np.cumsum([len(g) for g in groups])[:-1]
    means = np.array([part.mean() for part in np.split(raced.r, bounds)])
    return NullDraw(np.asarray(kept, dtype=int), tuple(groups), means, raced, dropped)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_null.py`
Expected: PASS (10 tests).

- [ ] **Step 5: Complexity check**

Run: `python -m radon cc -s -n C swingbot/core/backtesting/screen/null.py`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/backtesting/screen/null.py tests/backtesting/screen/test_null.py
git commit -m "feat(screen): matched null baseline, same ticker/month/trend (V140-4)"
```

### Task V140-5: Reported-only forward drift and rank correlation

**Files:**
- Create: `swingbot/core/backtesting/screen/forward.py`
- Test: `tests/backtesting/screen/test_forward.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (pandas, numpy only).
- Produces:
  - `HORIZONS = (5, 10, 20, 60)`, `MIN_RANK_N = 3`.
  - `forward_atr(df, atr, h) -> np.ndarray` — `(close[t+h] − close[t]) / ATR14[t]`, NaN where `t + h` is past the frame (frozen reading F10).
  - `excess_drift(fwd, event_pos, groups) -> list[float]` — per event, event forward value minus the mean of its finite null values; events with no finite value on either side are skipped.
  - `spearman(x, y) -> float | None` — average-rank Pearson; `None` under `MIN_RANK_N` points or a constant side. No scipy.
  - `yearly_rank_corr(years, indicator, fwd) -> dict[int, float | None]` — finite `fwd` only.

- [ ] **Step 1: Write the failing tests**

`tests/backtesting/screen/test_forward.py`:

```python
"""v140 forward drift and rank correlation: reported beside the verdict, never read by it."""
import numpy as np
import pandas as pd
import pytest

from swingbot.core.backtesting.screen import forward
from tests.backtesting.screen.helpers import frame


def test_horizons_are_the_spec_set():
    assert forward.HORIZONS == (5, 10, 20, 60)


def test_forward_atr_hand_computed():
    df = frame([100.0, 102.0, 104.0, 103.0])
    atr = pd.Series(2.0, index=df.index)
    out = forward.forward_atr(df, atr, 2)
    assert out[:2].tolist() == [2.0, 0.5]
    assert np.isnan(out[2:]).all()


def test_forward_atr_past_the_frame_is_all_nan():
    df = frame([100.0, 101.0])
    assert np.isnan(forward.forward_atr(df, pd.Series(1.0, index=df.index), 5)).all()


def test_excess_drift_is_event_minus_null_mean_and_skips_empty_pairs():
    fwd = np.array([1.0, 0.0, 2.0, np.nan, 4.0])
    out = forward.excess_drift(fwd, [0, 4], (np.array([1, 2]), np.array([3])))
    assert out == [pytest.approx(0.0)]


def test_spearman_known_answers():
    assert forward.spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    assert forward.spearman([1, 2, 3, 4], [40, 30, 20, 10]) == pytest.approx(-1.0)
    assert forward.spearman([0, 0, 1, 1], [1, 2, 3, 4]) == pytest.approx(0.894427, abs=1e-6)


def test_spearman_is_none_when_undefined():
    assert forward.spearman([1, 1, 1, 1], [1, 2, 3, 4]) is None
    assert forward.spearman([1, 2], [1, 2]) is None


def test_yearly_rank_corr_drops_nan_and_splits_by_year():
    years = np.array([2010] * 4 + [2011] * 4)
    indicator = np.array([0, 0, 1, 1, 1, 1, 0, 0])
    fwd = np.array([1.0, 2.0, 3.0, 4.0, 4.0, 3.0, 2.0, np.nan])
    out = forward.yearly_rank_corr(years, indicator, fwd)
    assert set(out) == {2010, 2011}
    assert out[2010] == pytest.approx(0.894427, abs=1e-6)
    assert out[2011] == pytest.approx(0.866025, abs=1e-6)
```

For 2011 the finite points are indicator `[1, 1, 0]` against fwd `[4, 3, 2]`: ranks `[2.5, 2.5, 1]` and `[3, 2, 1]`, centred `[0.5, 0.5, −1]` and `[1, 0, −1]`, correlation `1.5 / (sqrt(1.5) × sqrt(2)) = 0.866025`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_forward.py`
Expected: FAIL — `ImportError: cannot import name 'forward'`.

- [ ] **Step 3: Write `forward.py`**

`swingbot/core/backtesting/screen/forward.py`:

```python
"""Reported-only drift for the v140 screen (spec § forward.py).

Mean excess forward return in ATR units at h in HORIZONS, event minus its
matched null, and per-year Spearman rank correlation between the event
indicator and the h-bar forward return. Printed beside the verdict; the
verdict never reads it. numpy/pandas only (scipy is not a dependency).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

HORIZONS = (5, 10, 20, 60)
MIN_RANK_N = 3


def forward_atr(df: pd.DataFrame, atr, h: int) -> np.ndarray:
    """(close[t+h] - close[t]) / ATR14[t]; NaN where t+h is past the frame."""
    close = df["Close"].to_numpy(dtype=float)
    a = pd.Series(atr).to_numpy(dtype=float)
    out = np.full(len(close), np.nan)
    if h < len(close):
        with np.errstate(divide="ignore", invalid="ignore"):
            out[: len(close) - h] = (close[h:] - close[: len(close) - h]) / a[: len(close) - h]
    return out


def excess_drift(fwd, event_pos, groups) -> list:
    out = []
    for pos, group in zip(event_pos, groups):
        null = fwd[np.asarray(group, dtype=int)]
        null = null[np.isfinite(null)]
        if np.isfinite(fwd[pos]) and null.size:
            out.append(float(fwd[pos] - null.mean()))
    return out


def spearman(x, y) -> float | None:
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    if len(x) < MIN_RANK_N:
        return None
    rx = pd.Series(x).rank().to_numpy()
    ry = pd.Series(y).rank().to_numpy()
    if rx.std() == 0 or ry.std() == 0:
        return None
    return float(np.corrcoef(rx, ry)[0, 1])


def yearly_rank_corr(years, indicator, fwd) -> dict:
    years = np.asarray(years)
    indicator = np.asarray(indicator, dtype=float)
    fwd = np.asarray(fwd, dtype=float)
    ok = np.isfinite(fwd)
    return {int(y): spearman(indicator[ok & (years == y)], fwd[ok & (years == y)])
            for y in np.unique(years[ok])}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_forward.py`
Expected: PASS (7 tests).

- [ ] **Step 5: Complexity check**

Run: `python -m radon cc -s -n C swingbot/core/backtesting/screen/forward.py`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/backtesting/screen/forward.py tests/backtesting/screen/test_forward.py
git commit -m "feat(screen): reported-only forward drift and rank correlation (V140-5)"
```

### Task V140-6: `high52w` trigger

**Files:**
- Modify: `swingbot/core/backtesting/screen/ideas/high52w.py` (replace the `events` stub only; `CAP`, `PARAMS`, `SUMMARY`, `SOURCE` stay byte-identical)
- Test: `tests/backtesting/screen/test_idea_high52w.py`

**Interfaces:**
- Consumes: `indicators.rolling_max`, `indicators.sma` (V140-1); `PARAMS` (V140-2).
- Produces: `high52w.events(df) -> pd.Series[bool]` indexed like `df`, named `"high52w"`.

- [ ] **Step 1: Invoke `no-lookahead`, then write the failing tests**

`tests/backtesting/screen/test_idea_high52w.py`:

```python
"""v140 high52w: close >= 0.95 x 252-bar high, SMA50 > SMA200, first true
bar after >= 20 consecutive computable false bars (frozen reading F3)."""
import numpy as np

from swingbot.core.backtesting.screen.ideas import high52w
from tests.backtesting.screen.helpers import assert_prefix_stable, frame, random_walk


def _fixture(dip_bars=25):
    """Bars 0..329 rise 0.5 a bar (close 264.5, high 265.5 at 329), then a
    dip at 240 (< 0.95 x 265.5 = 252.2), then 260 (>= 252.2) to the end."""
    closes = np.r_[100 + 0.5 * np.arange(330), np.full(dip_bars, 240.0),
                   np.full(400 - 330 - dip_bars, 260.0)]
    return frame(closes)


def _event_positions(df):
    return np.flatnonzero(high52w.events(df).to_numpy()).tolist()


def test_fires_once_on_the_first_bar_back_near_the_high():
    assert _event_positions(_fixture()) == [355]


def test_does_not_fire_after_only_nineteen_false_bars():
    assert _event_positions(_fixture(dip_bars=19)) == []


def test_warm_up_bars_never_count_as_false():
    rise = frame(100 + 0.5 * np.arange(300))     # true from the first computable bar
    assert _event_positions(rise) == []


def test_series_shape():
    out = high52w.events(_fixture())
    assert out.dtype == bool and out.index.equals(_fixture().index)
    assert out.name == "high52w"


def test_reads_no_later_bar_on_the_fixture():
    assert_prefix_stable(high52w.events, _fixture(), [300, 340, 354, 355, 356, 399])


def test_reads_no_later_bar_on_a_random_walk():
    assert_prefix_stable(high52w.events, random_walk(700), [260, 400, 550, 699])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_idea_high52w.py`
Expected: FAIL — `NotImplementedError: V140-6 implements the high52w trigger`.

- [ ] **Step 3: Replace the stub**

In `swingbot/core/backtesting/screen/ideas/high52w.py`, change the docstring's last sentence to `Trigger frozen 2026-10-08 (v140).`, add `from swingbot.core.backtesting.screen import indicators` below `import pandas as pd`, and replace `events` with:

```python
def events(df: pd.DataFrame) -> pd.Series:
    """Event at the close of t. The quiet run counts only bars where the
    condition is computable (frozen reading F3)."""
    p = PARAMS
    close = df["Close"]
    top = indicators.rolling_max(df["High"], p["lookback"])
    fast = indicators.sma(close, p["fast_sma"])
    slow = indicators.sma(close, p["slow_sma"])
    known = top.notna() & fast.notna() & slow.notna()
    cond = known & (close >= p["near_high"] * top) & (fast > slow)
    quiet = (known & ~cond).astype(int).rolling(
        p["quiet_bars"], min_periods=p["quiet_bars"]).sum().shift(1)
    return (cond & (quiet == p["quiet_bars"])).rename("high52w")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_idea_high52w.py`
Expected: PASS (6 tests). Also re-run `python scripts/dev/testrun.py file tests/backtesting/screen/test_ideas_registry.py` — PASS (constants unchanged).

- [ ] **Step 5: Complexity check and commit**

Run: `python -m radon cc -s -n C swingbot/core/backtesting/screen/ideas/high52w.py` — no output.

```bash
git add swingbot/core/backtesting/screen/ideas/high52w.py tests/backtesting/screen/test_idea_high52w.py
git commit -m "feat(screen): high52w trigger, George & Hwang 52-week high (V140-6)"
```

### Task V140-7: `uptrend_pullback` trigger

**Files:**
- Modify: `swingbot/core/backtesting/screen/ideas/uptrend_pullback.py` (replace the `events` stub only)
- Test: `tests/backtesting/screen/test_idea_uptrend_pullback.py`

**Interfaces:**
- Consumes: `indicators.sma`, `indicators.rsi` (V140-1); `PARAMS` (V140-2).
- Produces: `uptrend_pullback.events(df) -> pd.Series[bool]` named `"uptrend_pullback"`.

- [ ] **Step 1: Invoke `no-lookahead`, then write the failing tests**

`tests/backtesting/screen/test_idea_uptrend_pullback.py`:

```python
"""v140 uptrend_pullback: close > SMA200 and Wilder RSI(2) < 10."""
import numpy as np

from swingbot.core.backtesting.screen.ideas import uptrend_pullback
from tests.backtesting.screen.helpers import assert_prefix_stable, frame, random_walk


def _fixture():
    """Rise 0.5 a bar to 223.5 at bar 247, two -2 bars (RSI2 20.0 then 7.69),
    then +0.5 bars again. RSI2 at 250 is 29.4."""
    closes = np.r_[100 + 0.5 * np.arange(248), 221.5, 219.5,
                   220 + 0.5 * np.arange(10)]
    return frame(closes)


def test_fires_on_the_second_down_bar_only():
    out = uptrend_pullback.events(_fixture())
    assert np.flatnonzero(out.to_numpy()).tolist() == [249]
    assert out.name == "uptrend_pullback"


def test_never_fires_below_the_200_bar_average():
    falling = frame(300 - 0.5 * np.arange(260))   # RSI2 is 0, close < SMA200
    assert not uptrend_pullback.events(falling).any()


def test_reads_no_later_bar_on_the_fixture():
    assert_prefix_stable(uptrend_pullback.events, _fixture(), [200, 247, 248, 249, 250, 259])


def test_reads_no_later_bar_on_a_random_walk():
    assert_prefix_stable(uptrend_pullback.events, random_walk(500), [210, 300, 499])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_idea_uptrend_pullback.py`
Expected: FAIL — `NotImplementedError`.

- [ ] **Step 3: Replace the stub**

In `swingbot/core/backtesting/screen/ideas/uptrend_pullback.py`, change the docstring's last sentence to `Trigger frozen 2026-10-08 (v140).`, add `from swingbot.core.backtesting.screen import indicators`, and replace `events` with:

```python
def events(df: pd.DataFrame) -> pd.Series:
    """Event at the close of t: an oversold bar inside a long-term uptrend."""
    close = df["Close"]
    trend = indicators.sma(close, PARAMS["trend_sma"])
    osc = indicators.rsi(close, PARAMS["rsi_n"])
    return ((close > trend) & (osc < PARAMS["rsi_below"])).rename("uptrend_pullback")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_idea_uptrend_pullback.py`
Expected: PASS (4 tests).

- [ ] **Step 5: Complexity check and commit**

Run: `python -m radon cc -s -n C swingbot/core/backtesting/screen/ideas/uptrend_pullback.py` — no output.

```bash
git add swingbot/core/backtesting/screen/ideas/uptrend_pullback.py tests/backtesting/screen/test_idea_uptrend_pullback.py
git commit -m "feat(screen): uptrend RSI(2) pullback trigger, Connors & Alvarez (V140-7)"
```

### Task V140-8: `gap_volume` trigger

**Files:**
- Modify: `swingbot/core/backtesting/screen/ideas/gap_volume.py` (replace the `events` stub only)
- Test: `tests/backtesting/screen/test_idea_gap_volume.py`

**Interfaces:**
- Consumes: `indicators.atr` (V140-1); `PARAMS` (V140-2).
- Produces: `gap_volume.events(df) -> pd.Series[bool]` named `"gap_volume"`.

- [ ] **Step 1: Invoke `no-lookahead`, then write the failing tests**

`tests/backtesting/screen/test_idea_gap_volume.py`:

```python
"""v140 gap_volume: open >= prior close + 1.0 x prior ATR14, volume >= 2 x
the 50-bar mean ending the prior bar, close >= open."""
import numpy as np
import pytest

from swingbot.core.backtesting.screen.ideas import gap_volume
from tests.backtesting.screen.helpers import assert_prefix_stable, frame, random_walk


def _fixture(open70=103.0, vol70=3e6):
    """80 flat bars (O = C = 100, H 101, L 99, volume 1e6: ATR14 = 2).
    Bar 70 gaps and holds on volume. Bar 75 gaps on volume but closes below
    its open. Bar 78 gaps and holds on too little volume."""
    n = 80
    o, h = np.full(n, 100.0), np.full(n, 101.0)
    l, c, v = np.full(n, 99.0), np.full(n, 100.0), np.full(n, 1e6)
    for i, bar in {70: (open70, 105.0, 101.5, 104.0, vol70),
                   75: (110.0, 111.0, 107.0, 108.0, 4e6),
                   78: (110.0, 112.0, 109.0, 111.0, 1.5e6)}.items():
        o[i], h[i], l[i], c[i], v[i] = bar
    return frame(c, opens=o, highs=h, lows=l, volumes=v)


def _positions(df):
    return np.flatnonzero(gap_volume.events(df).to_numpy()).tolist()


def test_fires_only_on_the_gap_that_holds_on_volume():
    assert _positions(_fixture()) == [70]
    assert gap_volume.events(_fixture()).name == "gap_volume"


@pytest.mark.parametrize("open70, vol70, expected", [
    (102.01, 3e6, [70]),      # open just above prior close + 1.0 x ATR (100 + 2)
    (101.99, 3e6, []),        # just below (ATR is a float: no exact-equality probe)
    (103.0, 2e6, [70]),       # volume exactly 2 x the 50-bar mean (1e6): inclusive
    (103.0, 1.99e6, []),
])
def test_thresholds_sit_where_the_spec_puts_them(open70, vol70, expected):
    assert _positions(_fixture(open70, vol70)) == expected


def test_reads_no_later_bar_on_the_fixture():
    assert_prefix_stable(gap_volume.events, _fixture(), [60, 69, 70, 71, 75, 79])


def test_reads_no_later_bar_on_a_random_walk():
    assert_prefix_stable(gap_volume.events, random_walk(400), [60, 200, 399])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_idea_gap_volume.py`
Expected: FAIL — `NotImplementedError`.

- [ ] **Step 3: Replace the stub**

In `swingbot/core/backtesting/screen/ideas/gap_volume.py`, change the docstring's last sentence to `Trigger frozen 2026-10-08 (v140).`, add `from swingbot.core.backtesting.screen import indicators`, and replace `events` with:

```python
def events(df: pd.DataFrame) -> pd.Series:
    """Event at the close of t: today's open gapped a full ATR above
    yesterday's close on double volume, and the gap held into the close."""
    p = PARAMS
    prev_close = df["Close"].shift(1)
    prev_atr = indicators.atr(df, p["atr_n"]).shift(1)
    prev_volume = df["Volume"].rolling(
        p["volume_window"], min_periods=p["volume_window"]).mean().shift(1)
    gap = df["Open"] >= prev_close + p["gap_atr"] * prev_atr
    loud = df["Volume"] >= p["volume_mult"] * prev_volume
    held = df["Close"] >= df["Open"]
    return (gap & loud & held).rename("gap_volume")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_idea_gap_volume.py`
Expected: PASS (7 tests).

- [ ] **Step 5: Complexity check and commit**

Run: `python -m radon cc -s -n C swingbot/core/backtesting/screen/ideas/gap_volume.py` — no output.

```bash
git add swingbot/core/backtesting/screen/ideas/gap_volume.py tests/backtesting/screen/test_idea_gap_volume.py
git commit -m "feat(screen): gap + volume continuation trigger (V140-8)"
```

### Task V140-9: `turn_of_month` trigger

**Files:**
- Modify: `swingbot/core/backtesting/screen/ideas/turn_of_month.py` (replace the `events` stub only)
- Test: `tests/backtesting/screen/test_idea_turn_of_month.py`

**Interfaces:**
- Consumes: `PARAMS` (V140-2). No indicators.
- Produces: `turn_of_month.events(df) -> pd.Series[bool]` named `"turn_of_month"`, reading only `df.index` (frozen reading F1).

- [ ] **Step 1: Invoke `no-lookahead`, then write the failing tests**

`tests/backtesting/screen/test_idea_turn_of_month.py`:

```python
"""v140 turn_of_month: t is the last trading day of its calendar month, from
the ticker's own bar dates (frozen reading F1)."""
import numpy as np
import pandas as pd

from swingbot.core.backtesting.screen.ideas import turn_of_month
from tests.backtesting.screen.helpers import assert_prefix_stable, frame, random_walk


def _on(dates):
    return turn_of_month.events(frame(np.full(len(dates), 100.0), index=dates)).tolist()


def test_last_bar_of_each_month_from_the_bar_dates():
    dates = ["2019-01-29", "2019-01-30", "2019-01-31", "2019-02-01",
             "2019-02-27", "2019-02-28", "2019-03-01"]
    assert _on(dates) == [False, False, True, False, False, True, False]


def test_a_holiday_month_end_uses_the_last_bar_actually_traded():
    # Good Friday 2018-03-30: the last March session was Thursday the 29th.
    assert _on(["2018-03-28", "2018-03-29", "2018-04-02", "2018-04-03"]) == [
        False, True, False, False]


def test_the_final_bar_of_a_frame_is_never_an_event():
    assert _on(["2019-01-31"]) == [False]
    empty = frame(np.array([], dtype=float), index=pd.DatetimeIndex([]))
    assert turn_of_month.events(empty).tolist() == []


def test_turn_of_month_reads_no_prices():
    a = random_walk(300)
    b = a.copy()
    b[:] = np.random.default_rng(1).uniform(1.0, 500.0, size=b.shape)
    assert turn_of_month.events(a).equals(turn_of_month.events(b))
    assert turn_of_month.events(a).name == "turn_of_month"


def test_reads_no_later_bar_except_the_truncated_frames_last_date():
    assert_prefix_stable(turn_of_month.events, random_walk(300),
                         [20, 21, 22, 150, 299], skip_last=True)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_idea_turn_of_month.py`
Expected: FAIL — `NotImplementedError`.

- [ ] **Step 3: Replace the stub**

In `swingbot/core/backtesting/screen/ideas/turn_of_month.py`, change the docstring's last sentence to `Trigger frozen 2026-10-08 (v140).`, add `import numpy as np` above `import pandas as pd`, and replace `events` with:

```python
def events(df: pd.DataFrame) -> pd.Series:
    """Event at the close of t when the next bar's DATE is in a new month.

    Reads the index only, never a price: the exchange calendar is public in
    advance. The frame's final bar has no next date and is False (reading F1).
    """
    index = pd.DatetimeIndex(df.index)
    months = np.asarray(index.year * 12 + index.month)
    last = np.zeros(len(months), dtype=bool)
    last[:-1] = months[1:] != months[:-1]
    return pd.Series(last, index=df.index, name="turn_of_month")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_idea_turn_of_month.py`
Expected: PASS (5 tests).

- [ ] **Step 5: Complexity check and commit**

Run: `python -m radon cc -s -n C swingbot/core/backtesting/screen/ideas/turn_of_month.py` — no output.

```bash
git add swingbot/core/backtesting/screen/ideas/turn_of_month.py tests/backtesting/screen/test_idea_turn_of_month.py
git commit -m "feat(screen): turn-of-month trigger from the ticker's bar dates (V140-9)"
```
