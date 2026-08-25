# Level Touch Strength Implementation Plan

> **CLOSED 2026-08-22, no-go — NOT merged to `main`.** Tasks 1–5's code was
> implemented and tested on worktree branch
> `worktree-2026-08-16-v36-level-touch-strength` (worktree/branch removed
> 2026-08-25; commits preserved at tag `no-lift/2026-08-16-v36-level-touch-strength`)
> only; Tasks 6/7 stopped
> short of VALIDATION. See
> `docs/superpowers/results/2026-08-22-level-touch-strength-train.md`:
> the confidence factor measured net negative on TRAIN, the selection
> tiebreak measured a no-op (no qualifying ties in the TRAIN sample), and
> the one-shot VALIDATION was deliberately not spent on a config with no
> measured lift. Since the feature showed no benefit, the branch was left
> unmerged rather than landed inert on `main` — the code exists only on
> that branch/worktree for future reference or salvage, should someone
> revisit the underlying idea (see "If this is revisited" in the results
> doc). This plan lives under `plans/no-lift/` rather than
> `plans/implemented/` specifically because nothing it built reached
> `main`.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

Version: ui 1.7.0 · bot 1.1.4
Bump: bot minor
Edge: none (no lift measured on TRAIN — see closing note above)

**Goal:** Grade every candidate level by how convincingly price has respected it
historically and how recently, then use that grade in target selection and
confidence scoring.

**Architecture:** The per-bar wick-vs-body classifier already exists
(`pattern_quality_at_level`). What is missing is history: finding *which* bars
touched a level, aggregating across them with recency decay, and attaching the
result to `Level`. A per-(ticker, price-band, date) cache keeps scan duration
inside budget.

**Tech Stack:** Python 3.11+, pandas/numpy, pytest. No new dependencies.

## What already exists

`edge/factors.py:193` — `pattern_quality_at_level(df, idx, level, direction) -> int`:

> "0-10 quality of the level-touch bar. Rewards conviction closes,
> participation (volume), and an actual rejection wick THROUGH the level — the
> difference between a bounce and a drift."

Its body (`:217-224`) already implements the exact three-way distinction the
spec designed:

```python
pierced   = bar["Low"] <= level if bull else bar["High"] >= level
reclaimed = bar["Close"] > level if bull else bar["Close"] < level
if pierced and reclaimed:          # REJECTION -- the level held
    ...
# pierced and NOT reclaimed        -- a BREAK, scores no wick bonus
```

with the comment: *"piercing and CLOSING through is a break, not a rejection,
and must not score like a bounce."*

**So the classifier is done.** This plan does not rewrite it. Three things are
genuinely missing:

1. **Touch discovery** — nothing finds which bars touched a level.
   `engine.py:_build_quality_inputs` says so explicitly: *"candle_quality needs
   a specific touch-bar+level the scan loop doesn't track per plan"*, and leaves
   it out rather than fabricating it.
2. **Aggregation with recency decay** — the classifier grades one bar.
3. **A field on `Level`** — it is `price` + `sources` only (`levels.py:106`).

`pattern_quality_at_level` is direction-aware and scores 0–10 with no negative
band, so a **break scores low, not negative**. Task 2 supplies the negative
signal at the aggregate level rather than editing a function other code uses.

## Global Constraints

- **No new market data.** Daily bars already fetched.
- **No polarity-flip detection** in v1.
- **Clustering is untouched.** Grading happens on `Level` objects after
  `_cluster_levels`.
- **Method count is unaffected.** Touch strength grades a level's *quality*,
  never how many methods found it — it must not become a backdoor into v32's
  honesty cap.
- **A level with no touch history scores NEUTRAL, not bad.** Otherwise the
  system structurally prefers old levels, which is not the same as good ones.
- **Ships default-OFF** behind `LEVEL_TOUCH_STRENGTH`.
- **Scan duration must stay inside `SCAN_INTERVAL_MINUTES`** — a hard
  acceptance criterion alongside win rate.
- **DEPENDS ON v32 and v31.**

## v31 has landed — Task 4's blocker is cleared

`docs/superpowers/plans/implemented/2026-08-16-v31-structural-targets.md`
merged to `main` on 2026-08-17 (`ef15927`), reworking
`select_structural_target()`, the function Task 4 modifies. That symbol now
exists (`swingbot/core/planning/plan_engine.py`).

Task 4 still begins by re-reading the selector as v31 actually left it before
touching it — its real signature and candidate-source plumbing may not match
what was assumed when this spec was written.

## v32 has also landed, but not as this plan assumed

`docs/superpowers/plans/implemented/2026-08-16-v32-unified-confidence-score.md`
merged to `main` on 2026-08-17. The registry (`FactorContext`/`FACTORS`/
`run_factors`) and the explicit `honesty_cap()` this plan's "must not become
a backdoor into v32's honesty cap" constraint refers to are both real, live
code. But `UNIFIED_CONFIDENCE` stays default-off: v32's TRAIN measurement
found no factor with real positive win-rate lift, so `FACTORS` ships with
only one inert factor, and the one-shot VALIDATION run then FAILed. Task 5
(`factor_level_strength` in v32's `FACTORS`) can still register into the
registry mechanically, but doing so has no live effect until a future spec
re-measures the whole merged set against real TRAIN evidence -- there is no
"v32 point budget" this factor draws from today. Full result:
`docs/superpowers/plans/implemented/v32-train-preregistration.md`.

## File Structure

| File | Responsibility |
|---|---|
| `swingbot/core/market/level_strength.py` | **NEW.** `find_touches()`, `grade_level()`, decay. Pure. |
| `swingbot/core/market/levels.py` | `Level.strength` field; grading after clustering. |
| `swingbot/core/market/strategy_types.py` | `touch_decay_halflife` per horizon. |
| `swingbot/core/scanning/factors.py` | `factor_level_strength` in v32's `FACTORS`. |
| `swingbot/config.py` | `LEVEL_TOUCH_STRENGTH`. |
| `tests/market/test_level_strength.py` | **NEW.** |

---

# Phase 1 — Touch discovery and grading

### Task 1: Find the bars that touched a level

**Files:**
- Create: `swingbot/core/market/level_strength.py`
- Test: `tests/market/test_level_strength.py`

**Interfaces:**
- Produces: `find_touches(df, level, tolerance_pct=0.5) -> list[int]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/market/test_level_strength.py
import pandas as pd
import pytest

from swingbot.core.market.level_strength import find_touches


def _bars(rows):
    """rows: list of (low, high, close)."""
    return pd.DataFrame({
        "Open": [r[2] for r in rows],
        "Low": [r[0] for r in rows],
        "High": [r[1] for r in rows],
        "Close": [r[2] for r in rows],
        "Volume": [1_000_000] * len(rows),
    })


def test_bar_entering_the_band_is_a_touch():
    df = _bars([(99.6, 101.0, 100.5), (105.0, 106.0, 105.5)])
    assert find_touches(df, level=100.0, tolerance_pct=0.5) == [0]


def test_bar_outside_the_band_is_not_a_touch():
    df = _bars([(105.0, 106.0, 105.5)])
    assert find_touches(df, level=100.0, tolerance_pct=0.5) == []


def test_band_is_a_percentage_of_the_level_not_absolute():
    """0.5% of 100 is 0.50; 0.5% of 1000 is 5.00. A fixed absolute band would
    make every level on a high-priced ticker untouchable."""
    df = _bars([(995.0, 1002.0, 1000.0)])
    assert find_touches(df, level=1000.0, tolerance_pct=0.5) == [0]


def test_multiple_touches_are_all_returned_in_order():
    df = _bars([(99.8, 100.2, 100.0), (110.0, 111.0, 110.5), (99.9, 100.4, 100.1)])
    assert find_touches(df, level=100.0, tolerance_pct=0.5) == [0, 2]


def test_zero_or_negative_level_returns_no_touches():
    assert find_touches(_bars([(99.8, 100.2, 100.0)]), level=0.0) == []


def test_empty_frame_returns_no_touches():
    assert find_touches(_bars([]), level=100.0) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/market/test_level_strength.py`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# swingbot/core/market/level_strength.py
"""How convincingly price has respected a level, and how recently (v36).

The per-bar classifier already exists as
edge.factors.pattern_quality_at_level -- it distinguishes a rejection (pierced
the level and closed back beyond it) from a break (closed through). This module
supplies what was missing: which bars touched the level at all, and how to
aggregate many touches into one grade that decays with age.

Pure functions, no config reads, so the backtest can call them directly.
"""
from __future__ import annotations

import pandas as pd

DEFAULT_TOLERANCE_PCT = 0.5


def find_touches(df: pd.DataFrame, level: float,
                 tolerance_pct: float = DEFAULT_TOLERANCE_PCT) -> list[int]:
    """Indices of bars whose range entered the band around `level`.

    The band is a PERCENTAGE of the level, not an absolute amount: a fixed
    band would be meaningless across a watchlist holding both a $20 and a
    $2000 ticker.
    """
    if df is None or len(df) == 0 or level <= 0:
        return []
    half = level * tolerance_pct / 100.0
    lo, hi = level - half, level + half
    lows = df["Low"].values
    highs = df["High"].values
    return [i for i in range(len(df)) if lows[i] <= hi and highs[i] >= lo]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/market/test_level_strength.py`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/market/level_strength.py tests/market/test_level_strength.py
git commit -m "feat(v36): find the bars that touched a level"
```

---

### Task 2: Grade a level from its touches, with recency decay

**Files:**
- Modify: `swingbot/core/market/level_strength.py`
- Modify: `swingbot/core/market/strategy_types.py` (all 10 horizons)
- Test: `tests/market/test_level_strength.py`

**Interfaces:**
- Consumes: `find_touches` (Task 1), `pattern_quality_at_level`
  (`edge/factors.py:193`).
- Produces: `grade_level(df, level, direction, halflife_bars) -> dict` returning
  `{"score": float, "touches": int, "rejections": int, "breaks": int,
  "available": bool}`; `HORIZONS[key]["touch_decay_halflife"]`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/market/test_level_strength.py
from swingbot.core.market.level_strength import grade_level


def test_untouched_level_is_neutral_and_flagged_unavailable():
    """A freshly-formed level has no history. It must score NEUTRAL, not bad --
    otherwise the system structurally prefers old levels over good ones."""
    df = _bars([(200.0, 201.0, 200.5)] * 50)
    g = grade_level(df, level=100.0, direction="bullish", halflife_bars=60)
    assert g["available"] is False
    assert g["touches"] == 0
    assert g["score"] == pytest.approx(0.5)


def test_repeated_rejections_score_high():
    """Wick below the level, close back above = the level held."""
    rows = [(99.0, 101.0, 100.8)] * 3 + [(105.0, 106.0, 105.5)] * 20
    g = grade_level(_bars(rows), level=100.0, direction="bullish", halflife_bars=60)
    assert g["rejections"] == 3
    assert g["breaks"] == 0
    assert g["score"] > 0.6


def test_breaks_score_low():
    """Closing THROUGH the level is a failure, and must not score like a
    bounce -- a bare proximity count would rate a destroyed level as
    well-tested."""
    rows = [(98.0, 101.0, 98.5)] * 3 + [(90.0, 91.0, 90.5)] * 20
    g = grade_level(_bars(rows), level=100.0, direction="bullish", halflife_bars=60)
    assert g["breaks"] == 3
    assert g["score"] < 0.4


def test_recent_touches_outweigh_old_ones():
    """Same touch, different age. A rejection three weeks ago is stronger
    evidence than one eight months ago."""
    recent = _bars([(105.0, 106.0, 105.5)] * 40 + [(99.0, 101.0, 100.8)] * 3)
    old = _bars([(99.0, 101.0, 100.8)] * 3 + [(105.0, 106.0, 105.5)] * 40)
    g_recent = grade_level(recent, 100.0, "bullish", halflife_bars=20)
    g_old = grade_level(old, 100.0, "bullish", halflife_bars=20)
    assert g_recent["score"] > g_old["score"]


def test_score_is_bounded_to_unit_interval():
    rows = [(99.0, 101.0, 100.8)] * 40
    g = grade_level(_bars(rows), 100.0, "bullish", halflife_bars=60)
    assert 0.0 <= g["score"] <= 1.0


def test_every_horizon_defines_a_touch_decay_halflife():
    from swingbot.core.market.strategy_types import HORIZONS
    for key, settings in HORIZONS.items():
        assert "touch_decay_halflife" in settings, f"{key} missing halflife"


def test_halflives_increase_with_horizon_length():
    from swingbot.core.market.strategy_types import HORIZONS
    values = [HORIZONS[k]["touch_decay_halflife"] for k in HORIZONS]
    assert values == sorted(values)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/market/test_level_strength.py`
Expected: FAIL — `ImportError: cannot import name 'grade_level'`

- [ ] **Step 3: Add per-horizon half-lives**

```python
# swingbot/core/market/strategy_types.py -- one line per HORIZONS entry
"2w": {..., "touch_decay_halflife": 10},
"4w": {..., "touch_decay_halflife": 21},
"2m": {..., "touch_decay_halflife": 42},
"3m": {..., "touch_decay_halflife": 63},
"4m": {..., "touch_decay_halflife": 84},
"5m": {..., "touch_decay_halflife": 105},
"6m": {..., "touch_decay_halflife": 126},
"7m": {..., "touch_decay_halflife": 147},
"8m": {..., "touch_decay_halflife": 168},
"9m": {..., "touch_decay_halflife": 189},
```

- [ ] **Step 4: Write the implementation**

```python
# append to swingbot/core/market/level_strength.py
NEUTRAL_SCORE = 0.5


def grade_level(df: pd.DataFrame, level: float, direction: str,
                halflife_bars: int,
                tolerance_pct: float = DEFAULT_TOLERANCE_PCT) -> dict:
    """Aggregate every touch of `level` into one 0..1 grade.

    Rejections push the grade up, breaks push it down, and both decay with
    age on `halflife_bars`. A level with no touches returns NEUTRAL_SCORE and
    available=False -- absence of evidence is not evidence of weakness, and
    scoring it low would make the system prefer merely OLD levels.
    """
    from swingbot.core.edge.factors import pattern_quality_at_level

    touches = find_touches(df, level, tolerance_pct)
    if not touches:
        return {"score": NEUTRAL_SCORE, "touches": 0, "rejections": 0,
                "breaks": 0, "available": False}

    last = len(df) - 1
    bull = direction == "bullish"
    weighted, total_weight = 0.0, 0.0
    rejections = breaks = 0

    for idx in touches:
        bar = df.iloc[idx]
        pierced = bar["Low"] <= level if bull else bar["High"] >= level
        reclaimed = bar["Close"] > level if bull else bar["Close"] < level
        weight = 0.5 ** ((last - idx) / max(1, halflife_bars))

        if pierced and reclaimed:
            rejections += 1
            # pattern_quality_at_level scores 0-10 with no negative band, so
            # it grades HOW WELL the level held; the break case supplies the
            # negative signal below rather than editing a shared function.
            quality = pattern_quality_at_level(df, idx, level, direction) / 10.0
            weighted += weight * quality
        elif pierced and not reclaimed:
            breaks += 1
            weighted += weight * 0.0
        else:
            weighted += weight * NEUTRAL_SCORE
        total_weight += weight

    score = weighted / total_weight if total_weight else NEUTRAL_SCORE
    return {"score": max(0.0, min(1.0, score)), "touches": len(touches),
            "rejections": rejections, "breaks": breaks, "available": True}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/market/test_level_strength.py`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/market/level_strength.py swingbot/core/market/strategy_types.py tests/market/test_level_strength.py
git commit -m "feat(v36): grade a level from decayed rejection/break history"
```

---

# Phase 2 — Attach to levels, with a cache

### Task 3: `Level.strength`, computed once per bar per level

**Files:**
- Modify: `swingbot/core/market/levels.py:105-109`
- Modify: `swingbot/config.py`
- Test: `tests/market/test_levels_strength.py`

**Interfaces:**
- Consumes: `grade_level` (Task 2).
- Produces: `Level.strength: dict | None`.

Cost is per level per scan, and a clustered map has many levels. The grade only
changes when a new daily bar arrives, so it is cached on
`(ticker, rounded level price, last bar date)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/market/test_levels_strength.py
from swingbot import config
from swingbot.core.market.levels import Level


def test_level_has_a_strength_field_defaulting_to_none():
    assert Level(price=100.0, sources=["EMA"]).strength is None


def test_strength_populated_when_flag_on(monkeypatch):
    monkeypatch.setattr(config, "LEVEL_TOUCH_STRENGTH", True)
    levels = _build_level_map(_frame_with_repeated_bounce_at(100.0))
    graded = [lv for lv in levels if abs(lv.price - 100.0) < 1.0]
    assert graded and graded[0].strength["available"] is True


def test_strength_absent_when_flag_off(monkeypatch):
    monkeypatch.setattr(config, "LEVEL_TOUCH_STRENGTH", False)
    levels = _build_level_map(_frame_with_repeated_bounce_at(100.0))
    assert all(lv.strength is None for lv in levels)


def test_grade_is_cached_per_bar(monkeypatch):
    """Second scan on the same final bar must not recompute -- this is the
    difference between fitting in SCAN_INTERVAL_MINUTES and not."""
    calls = []
    monkeypatch.setattr("swingbot.core.market.levels.grade_level",
                        lambda *a, **k: calls.append(1) or
                        {"score": 0.5, "touches": 0, "rejections": 0,
                         "breaks": 0, "available": False})
    monkeypatch.setattr(config, "LEVEL_TOUCH_STRENGTH", True)
    df = _frame_with_repeated_bounce_at(100.0)
    _build_level_map(df, ticker="AAPL")
    first = len(calls)
    _build_level_map(df, ticker="AAPL")
    assert len(calls) == first, "second identical scan should hit the cache"


def test_method_count_is_unaffected_by_strength():
    """Touch strength grades level QUALITY. It must never add a source, or it
    becomes a backdoor into v32's honesty cap."""
    lv = Level(price=100.0, sources=["EMA", "VWAP"])
    before = len(lv.sources)
    lv.strength = {"score": 0.9, "touches": 5, "rejections": 5,
                   "breaks": 0, "available": True}
    assert len(lv.sources) == before
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/market/test_levels_strength.py`
Expected: FAIL — `Level` has no `strength`

- [ ] **Step 3: Add the config flag**

```python
# swingbot/config.py
    Field("LEVEL_TOUCH_STRENGTH", "LEVEL_TOUCH_STRENGTH", "Universe & Scanning",
          "Level touch-strength grading",
          type="checkbox", default="false",
          help="Grade each support/resistance level by how convincingly price has "
               "respected it historically (rejections vs breaks, decayed by age), "
               "and prefer better-tested levels as targets. Enable only after "
               "VALIDATION."),
```

- [ ] **Step 4: Add the field and the cached grading pass**

```python
# swingbot/core/market/levels.py
@dataclass
class Level:
    price: float
    sources: list
    strength: dict | None = None   # v36; None = not graded
```

After `_cluster_levels`, when `config.LEVEL_TOUCH_STRENGTH` is on, grade each
level via a module-level cache keyed
`(ticker, round(level.price, 2), str(df.index[-1].date()), horizon_key)`.
Bound the cache (e.g. `functools.lru_cache`-style or an explicit dict capped at
a few thousand entries) so a long-running bot does not grow it without limit.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/market/test_levels_strength.py`
Expected: PASS

- [ ] **Step 6: Measure scan duration before and after**

Run a full watchlist scan with the flag off, then on; record wall-clock time for
both. **If the flag-on scan does not fit inside `SCAN_INTERVAL_MINUTES`, stop
and fix the cache before continuing** — this is an acceptance criterion, not a
nice-to-have.

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/market/levels.py swingbot/config.py tests/market/test_levels_strength.py
git commit -m "feat(v36): Level.strength with a per-bar cache"
```

---

# Phase 3 — Use the grade

### Task 4: Prefer better-tested levels in target selection

> **BLOCKED ON v31.** Do not start until
> `2026-08-16-v31-structural-targets.md` has landed and moved to
> `plans/implemented/`.

**Files:**
- Modify: whichever module v31 left `select_structural_target()` in
- Test: `tests/market/test_target_selection_strength.py`

- [ ] **Step 1: Re-read the selector as v31 actually left it**

Run: `git grep -n "def select_structural_target" -A 40 -- 'swingbot/**/*.py'`

Record its real signature. **Do not assume the shape this plan guessed** — v31
was in flight when this plan was written.

- [ ] **Step 2: Write the failing test**

```python
# tests/market/test_target_selection_strength.py
def test_better_tested_level_wins_between_two_equal_candidates(monkeypatch):
    """Two candidates at the same distance with the same method count: the one
    price has actually respected should win."""
    monkeypatch.setattr(config, "LEVEL_TOUCH_STRENGTH", True)
    weak = Level(price=110.0, sources=["EMA"],
                 strength={"score": 0.2, "touches": 4, "rejections": 0,
                           "breaks": 4, "available": True})
    strong = Level(price=110.2, sources=["EMA"],
                   strength={"score": 0.9, "touches": 4, "rejections": 4,
                             "breaks": 0, "available": True})
    assert _select_target([weak, strong], entry=100.0).price == 110.2


def test_ungraded_level_is_not_penalised_against_a_graded_one(monkeypatch):
    """available=False is neutral, not weak. A brand-new level must still be
    selectable on its other merits."""
    monkeypatch.setattr(config, "LEVEL_TOUCH_STRENGTH", True)
    ungraded = Level(price=110.0, sources=["EMA", "VWAP", "Fibonacci"],
                     strength={"score": 0.5, "touches": 0, "rejections": 0,
                               "breaks": 0, "available": False})
    graded = Level(price=110.2, sources=["EMA"],
                   strength={"score": 0.6, "touches": 2, "rejections": 1,
                             "breaks": 1, "available": True})
    assert _select_target([ungraded, graded], entry=100.0).price == 110.0


def test_selection_unchanged_when_flag_off(monkeypatch):
    monkeypatch.setattr(config, "LEVEL_TOUCH_STRENGTH", False)
    weak = Level(price=110.0, sources=["EMA"],
                 strength={"score": 0.1, "touches": 4, "rejections": 0,
                           "breaks": 4, "available": True})
    strong = Level(price=110.2, sources=["EMA"],
                   strength={"score": 0.9, "touches": 4, "rejections": 4,
                             "breaks": 0, "available": True})
    assert _select_target([weak, strong], entry=100.0).price == 110.0
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/market/test_target_selection_strength.py`

- [ ] **Step 4: Add strength as a tiebreaker, not an override**

Method count and distance remain the primary criteria; strength breaks ties
among otherwise-comparable candidates. A level with `available=False`
contributes its neutral 0.5 and is neither rewarded nor punished.

- [ ] **Step 5: Run tests and the fast tier**

Run: `python scripts/dev/testrun.py fast`
Expected: `0 failed`, `0 xfailed`

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat(v36): prefer better-tested levels when selecting a target"
```

---

### Task 5: Touch strength as a v32 confidence factor

**Files:**
- Modify: `swingbot/core/scanning/factors.py`
- Test: `tests/scanning/test_factors.py`

**Interfaces:**
- Consumes: v32's `FactorResult`/`FactorContext`; `Level.strength` (Task 3).
- Produces: `factor_level_strength`, registered in `FACTORS`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/scanning/test_factors.py
from swingbot.core.scanning.factors import factor_level_strength


def test_level_strength_scores_high_for_a_well_respected_level():
    ctx = _ctx(target_strength={"score": 0.9, "touches": 5, "rejections": 5,
                                "breaks": 0, "available": True})
    r = factor_level_strength(ctx)
    assert r.points == 10
    assert "5 rejection" in r.line


def test_level_strength_scores_zero_for_a_repeatedly_broken_level():
    ctx = _ctx(target_strength={"score": 0.05, "touches": 4, "rejections": 0,
                                "breaks": 4, "available": True})
    assert factor_level_strength(ctx).points == 0


def test_ungraded_level_returns_none_not_zero():
    ctx = _ctx(target_strength={"score": 0.5, "touches": 0, "rejections": 0,
                                "breaks": 0, "available": False})
    assert factor_level_strength(ctx) is None


def test_absent_strength_returns_none():
    assert factor_level_strength(_ctx()) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scanning/test_factors.py`

- [ ] **Step 3: Write the implementation**

Add `target_strength: dict | None = None` to `FactorContext`, then:

```python
# append to swingbot/core/scanning/factors.py
_LEVEL_STRENGTH_MAX = 10   # provisional; re-derived in Task 6


def factor_level_strength(ctx: FactorContext) -> FactorResult | None:
    """How convincingly price has respected the target level before.
    An ungraded level returns None -- omitted from the breakdown rather than
    scored zero, so a brand-new level is not reported as a weak one."""
    s = ctx.target_strength
    if not s or not s.get("available"):
        return None
    points = int(round(s["score"] * _LEVEL_STRENGTH_MAX))
    return FactorResult(
        "Level touch strength", points,
        f"{s['rejections']} rejection(s) vs {s['breaks']} break(s) "
        f"across {s['touches']} touch(es) (+{points})")
```

Register in `FACTORS` and populate `target_strength` where `engine.py` builds
the `FactorContext`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scanning/test_factors.py`

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/scanning/factors.py swingbot/core/scanning/engine.py tests/scanning/test_factors.py
git commit -m "feat(v36): level touch strength as a confidence factor"
```

---

# Phase 4 — Measure and ship

### Task 6: TRAIN — selection and confidence measured separately

**Files:**
- Create: `docs/superpowers/plans/v36-train-preregistration.md`
- Modify: `swingbot/core/scanning/factors.py` (points only)

- [ ] **Step 1: Run four TRAIN arms**

Selection and confidence can disagree; one aggregate number would hide it.

| Arm | Selection uses strength | Confidence factor on |
|---|---|---|
| A (baseline) | no | no |
| B | yes | no |
| C | no | yes |
| D | yes | yes |

Dispatch via `backtest-runner`.

- [ ] **Step 2: Tune only tolerance and half-life**

Wick/body/tolerance rules have many tunable edges and a full grid would find
something that works on TRAIN and nowhere else. The classification rule is
**fixed** by Task 2. Sweep only `tolerance_pct` ∈ {0.3, 0.5, 0.75, 1.0} and a
half-life multiplier ∈ {0.5x, 1x, 2x} of the per-horizon defaults.

- [ ] **Step 3: Confirm the scan-duration budget still holds**

Re-measure with the winning tolerance — a wider band means more touches per
level and more classifier calls.

- [ ] **Step 4: Re-derive the factor's point value**

Replace `_LEVEL_STRENGTH_MAX = 10` with what TRAIN supports, on v32 Task 9's
normalized scale. If arm C shows no lift, ship selection only and drop the
factor.

- [ ] **Step 5: Write the pre-registration**

```markdown
## v36 VALIDATION pre-registration
- Primary: win rate at MIN_ALERT_CONFIDENCE_LEVEL=4 with LEVEL_TOUCH_STRENGTH=on.
- Arms shipped: <B | C | D>, chosen from TRAIN Step 1.
- tolerance_pct=<X>, halflife multiplier=<Y> (frozen from Step 2).
- PASS: win rate improves vs. the v35 baseline AND alert volume falls by no
  more than 30% AND full-watchlist scan duration stays inside
  SCAN_INTERVAL_MINUTES.
- One shot. FAIL means LEVEL_TOUCH_STRENGTH stays default-off.
```

- [ ] **Step 6: Commit**

```bash
git add docs/superpowers/plans/v36-train-preregistration.md swingbot/core/scanning/factors.py data/v36_train.json
git commit -m "feat(v36): TRAIN arms for selection vs confidence, weights derived"
```

---

### Task 7: VALIDATION, docs, version bump

**Files:**
- Modify: `swingbot/config.py`, `docs/strategy.md`, `VERSION.json`

- [ ] **Step 1: Confirm the pre-registration is committed and unedited**

- [ ] **Step 2: Run VALIDATION once**

Run: `python scripts/backtest/run_backtest_range.py --validation --json data/v36_validation.json`

- [ ] **Step 3: Record the result verbatim. Do not re-run on FAIL.**

- [ ] **Step 4: On PASS, flip `LEVEL_TOUCH_STRENGTH` to `default="true"`**

- [ ] **Step 5: Document in `docs/strategy.md`**

Cover the rejection/break/consolidation distinction, per-horizon decay, and that
an ungraded level is neutral rather than weak.

- [ ] **Step 6: Run the full suite**

Run: `python scripts/dev/testrun.py full`
Expected: `0 failed`, `0 xfailed`

- [ ] **Step 7: Bump and close**

```bash
git mv docs/superpowers/specs/2026-08-16-v36-level-touch-strength-design.md docs/superpowers/specs/implemented/
git mv docs/superpowers/plans/2026-08-16-v36-level-touch-strength.md docs/superpowers/plans/implemented/
git add -A
git commit -m "feat(v36): VALIDATION result, docs, version bump"
```

---

## Parallelisation

- **Sequential: Task 1 → Task 2.** Task 2 consumes `find_touches`.
- **Sequential: Task 2 → Task 3.** Task 3 consumes `grade_level`.
- **Group A (parallel, after Task 3):** Task 4 and Task 5 — different files
  (the selector module vs `factors.py`), both consuming the `Level.strength`
  contract Task 3 fixes. **But Task 4 is additionally blocked on v31**, so in
  practice Task 5 usually runs first and alone.
- **Sequential: Task 6 after Tasks 4–5** (its four arms need both wired).
- **Sequential: Task 6 → Task 7.**

## Progress

- [x] Task 1 — `find_touches`
- [x] Task 2 — `grade_level` + per-horizon decay
- [x] Task 3 — `Level.strength` + cache + duration check
- [x] Task 4 — Target selection *(blocked on v31)*
- [x] Task 5 — Confidence factor
- [x] Task 6 — TRAIN, four arms (Steps 1 and 3 only; Steps 2/4-6 skipped — see
      closing note and `results/2026-08-22-level-touch-strength-train.md`)
- [ ] Task 7 — VALIDATION, docs, bump — **not run, deliberately.** No-go
      recorded instead; `LEVEL_TOUCH_STRENGTH` stays default-off.
