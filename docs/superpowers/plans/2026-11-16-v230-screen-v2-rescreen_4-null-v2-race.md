# v230 Plan 1, Part 4 — the v2 null: level and avoid draws, the race pass and the orchestration

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V230-10" -A 400 <this file>`).

**Spec:** [2026-11-16-v230-screen-v2-ladder-additive-gate-design.md](../specs/2026-11-16-v230-screen-v2-ladder-additive-gate-design.md) (A2: level-entry and avoid-control paths, stage 3 race pass, one frame resident, checkpoint manifest with `null_version`, `SCOPE` and stage; Found while briefing: descriptive blocks computed per null bar on its own frame)
**Index:** [2026-11-16-v230-screen-v2-rescreen_0-index.md](2026-11-16-v230-screen-v2-rescreen_0-index.md) — Goal, Architecture, `## Global Constraints`, `## Parallelisation` and the task ledger live there; every task below obeys them.
**Tasks:** V230-9..V230-11

What this part builds: V230-9 finishes stage 2 of `null_v2.py` (the
level-entry draw on the null ticker's own bars and ATR14, the avoid control
draw, and the `draw` dispatcher that ends in `check_starvation`). V230-10 adds
stage 3 (`race_pass`, one null ticker's frame resident at a time, per-ticker
checkpoints) and `scatter` back to events. V230-11 adds
`screen/screen_v2.py`: `run_v2` runs the three stages with staged checkpoints
and returns one `V2Ticker` per event ticker for V230-12's `TickerScreen`
adapter.

**Runs only if V230-5 recorded `BIAS`** (index `## Handoff`). Every test here
uses synthetic panels or `helpers.random_walk` frames; nothing reads the real
cache (Global Constraints: no real idea under v2 before V230-13).

**Contracts this part adds beyond the ledger rows** (Parts 5–6 rely on them):

- **Unfilled level slots are table rows.** `draw_ticker_level` writes one row
  per drawn slot; a slot still unfilled after replacement is a row with
  `null_ticker = ""`, `null_pos = -1`, `fill = NaN`. So for a level draw
  `DrawResult.slots == len(table)` and `DrawResult.unfilled ==
  (table.null_pos < 0).sum()`. An event with no filled slot keeps its rows
  and is counted in `dropped` (v1: `group.size == 0` drops the event).
  Next-open, market and control tables never hold such rows.
- **`race_pass`** keeps every input column (V230-11 adds an `arm` column) and
  the input row order; rows with `null_pos < 0` are not raced
  (`r = gross_r = NaN`, `outcome = "unfilled"`, `fwd_<h> = NaN`). A ticker's
  rows are all level (`fill` finite) or all next-open (`fill` NaN); a mix is a
  `ValueError`. A null ticker whose `load` returns None is a `ValueError`.
- **`EventNull`**: `slots` = rows of the event, `unfilled` = rows with
  `null_pos < 0`; means, outcomes, `fwd` (mean of the finite values, NaN when
  none) and `timeout_r` read filled rows only.
- **`run_v2`**: the manifest it passes to `open_stage` is the caller's
  manifest plus `scope`, `event_tickers_sha256` and `costs`. Stage keys: one
  per ticker in `panel`, the single key `draw` in `draw` (a
  `(DrawResult, DrawResult | None)` pair: the null draw and the avoid control
  draw), one per null ticker in `race`. `inputs.extras(name, df, ctx)` is
  called on event tickers only, with `ctx` plus `"book"` (that ticker's event
  book, a `race.RaceResult`). `V2Ticker.counters` carries the `run_book`
  counters, `dropped_no_match` (from `DrawResult.dropped`) and, in avoid mode,
  `control_below_floor` (from the control draw's `dropped`). An event is kept
  when its null has at least one filled slot. `null_timeout_r` is filled for
  `race_shape == "trail"` only (v1 `_null_timeout_r`); `depths` is
  `{"event": [...], "null": [...]}` for level ideas only (a filled null slot's
  realised depth equals its event's depth, as v1's `_realised_depth`), else
  None; `avoid_control` holds the control rows (same keys as `events`) for
  avoid ideas only, else None.

# Phase 4 — the v2 null, stage 2 paths and stage 3

### Task V230-9: v2 level-entry and avoid-control draws, and the dispatcher

**Model:** opus — the level path reproduces v1's fill and replacement-stream semantics on another ticker's bars, and the dispatcher is the one place the refusal fires before any race.

**Files:**
- Modify: `swingbot/core/backtesting/screen/null_v2.py` (append the level, control and dispatcher section)
- Test: `tests/backtesting/screen/test_null_v2_level.py` (create)

**Interfaces:**
- Consumes: V230-1 `Idea.scope`; V230-6 `TickerPanel.level_bars`, `cross_section`; V230-7 `ticker_pool`, `date_seed`, `DrawResult`, `draw_ticker_scope`, `check_starvation`, `NullRefusal`, `SCOPE_MISMATCH`, `NULL_STARVED`, `_v2_name`, `_records`, `_events_by_row`, `_Tally`; V230-8 `draw_market_scope`; existing `null.K`, `null.MIN_CANDIDATES`, `null.null_seed`, `null.child_seed`, `null._null_fills` (test only).
- Produces: `level_fill(bar_row, depth, direction) -> float`; `draw_ticker_level(xs, panels, booked, depths: Mapping[str, array], *, idea: str, direction: str, k=null.K) -> DrawResult`; `draw_control(xs, booked, *, idea: str, k=null.K) -> DrawResult`; `draw(xs, panels, booked, *, idea: Idea, depths=None) -> DrawResult` (`xs` may be None for a market-scope idea). Unfilled level slots are rows with `null_ticker = ""`, `null_pos = -1` (part header).

**Level rules (spec A2, v1 `null._draw_level`):** per date, the main
generator is `date_seed(idea, t)` and the replacement generator
`null.child_seed(date_seed(idea, t))`, one of each per date, consumed over the
date's events in sorted-ticker order. An event draws `m = min(K, pool)` first
picks **unsorted** from the main generator; each pick fills at
`Open_j ± depth × ATR14_j[t-1]` when bar *t* of ticker *j* reaches it; when
fewer than `m` filled and the rest of the pool (`setdiff1d(pool, first)`) is
not empty, one `child.permutation(rest)` supplies replacements in order until
`m` fill. Filled rows are sorted by ticker; the rows left unfilled follow as
blank rows. An event with no fill is counted in `dropped` (not starved: its
pool reached the floor). **Control (avoid mode):** the ticker-scope draw with
`xs.control` required of *j*, seed `null_seed(f"{idea}:v2:control", ISO day)`;
never refused (v1 counts it in `below_floor`), so `draw` does not route it.

- [ ] **Step 1: Write the failing tests**

Create `tests/backtesting/screen/test_null_v2_level.py`:

```python
"""v230 A2 stage 2: the level-entry draw on the null ticker's own bars and
ATR14, the avoid control draw, and the dispatcher that ends in the refusal."""
from collections import Counter

import numpy as np
import pandas as pd
import pytest

from swingbot.core.backtesting.screen import indicators, null, null_v2
from swingbot.core.backtesting.screen.ideas import Idea
from tests.backtesting.screen.helpers import random_walk

IDEA = "x"
DAYS = pd.bdate_range("2015-01-05", periods=5)
OPEN = 100.0


def _panel(ticker, *, high=103.0, low=97.0, atr=2.0, event=(), control=None, n=len(DAYS),
           dates=DAYS):
    ev = np.zeros(n, dtype=bool)
    ev[list(event)] = True
    bars = np.column_stack([np.full(n, OPEN), np.full(n, high), np.full(n, low),
                            np.full(n, atr)])
    return null_v2.TickerPanel(ticker, dates.to_numpy(), ~ev, np.full(n, True),
                               np.full(n, 0.02), ev,
                               None if control is None else np.asarray(control, dtype=bool),
                               bars)


def _universe(n=30, **special):
    panels = {f"T{i:02d}": _panel(f"T{i:02d}", **special.get(f"T{i:02d}", {}))
              for i in range(n)}
    return null_v2.cross_section(panels), panels


def _level(xs, panels, booked, depths):
    return null_v2.draw_ticker_level(xs, panels, booked, depths, idea=IDEA, direction="long")


def _idea(**kw):
    return Idea(name=IDEA, events=lambda df: df["Close"] > 0, time_cap_bars=4, **kw)


@pytest.mark.parametrize("row, direction, expected", [
    ((100.0, 103.0, 97.0, 2.0), "long", 102.0),
    ((100.0, 102.0, 97.0, 2.0), "long", 102.0),      # High == level fills (v1 >=)
    ((100.0, 101.9, 97.0, 2.0), "long", np.nan),
    ((100.0, 103.0, 98.0, 2.0), "short", 98.0),      # Low == level fills (v1 <=)
    ((100.0, 103.0, 98.1, 2.0), "short", np.nan),
    ((100.0, 103.0, 97.0, np.nan), "long", np.nan),  # row 0: no previous ATR
    ((100.0, 103.0, 97.0, 0.0), "long", np.nan),
])
def test_level_fill_reads_open_high_low_and_the_previous_atr(row, direction, expected):
    got = null_v2.level_fill(np.asarray(row), 1.0, direction)
    assert (np.isnan(got) and np.isnan(expected)) or got == pytest.approx(expected)


def test_level_fill_refuses_an_unknown_direction():
    with pytest.raises(ValueError, match="direction"):
        null_v2.level_fill(np.array([100.0, 103.0, 97.0, 2.0]), 1.0, "flat")


@pytest.mark.parametrize("direction", ["long", "short"])
def test_level_fill_matches_the_v1_rule_bar_for_bar(direction):
    df = random_walk(300, seed=11)
    atr = indicators.atr(df).to_numpy(dtype=float)
    bars = np.column_stack([df["Open"], df["High"], df["Low"], np.r_[np.nan, atr[:-1]]])
    positions = np.arange(len(df))
    fill, ok = null._null_fills(df, positions, 0.3, atr, direction)
    ours = np.array([null_v2.level_fill(bars[p], 0.3, direction) for p in positions])
    np.testing.assert_allclose(ours[ok], fill[ok])
    assert np.isnan(ours[~ok]).all()


def test_level_fills_use_the_null_tickers_own_open_and_atr():
    panels = {f"T{i:02d}": _panel(f"T{i:02d}", high=150.0, atr=1.0 + i / 10,
                                  event=(2,) if i == 0 else ()) for i in range(30)}
    xs = null_v2.cross_section(panels)
    table = _level(xs, panels, {"T00": [2]}, {"T00": [0.5]}).table
    assert len(table) == null.K and (table.null_pos == 2).all()
    atr = table.null_ticker.map(lambda t: 1.0 + int(t[1:]) / 10)
    np.testing.assert_allclose(table.fill, OPEN + 0.5 * atr)
    assert "T00" not in set(table.null_ticker)


def test_unfilled_first_draws_are_replaced_in_child_permutation_order():
    # odd tickers reach the level 101, even ones (High 100.5) never do
    panels = {f"T{i:02d}": _panel(f"T{i:02d}", high=150.0 if i % 2 else 100.5,
                                  event=(1,) if i == 0 else ()) for i in range(61)}
    xs = null_v2.cross_section(panels)
    got = _level(xs, panels, {"T00": [1]}, {"T00": [0.5]})
    pool = null_v2.ticker_pool(xs, 1, 0)
    seed = null_v2.date_seed(IDEA, DAYS[1])
    first = np.random.default_rng(seed).choice(pool, size=null.K, replace=False)
    kept = [j for j in first.tolist() if j % 2]
    order = np.random.default_rng(null.child_seed(seed)).permutation(np.setdiff1d(pool, first))
    kept += [j for j in order.tolist() if j % 2][: null.K - len(kept)]
    assert list(got.table.null_ticker) == [xs.tickers[j] for j in sorted(kept)]
    assert (got.slots, got.unfilled, got.dropped) == (null.K, 0, Counter())


def test_slots_left_unfilled_stay_as_blank_rows():
    panels = {f"T{i:02d}": _panel(f"T{i:02d}", high=150.0 if i in (1, 2, 3) else 100.5,
                                  event=(1,) if i == 0 else ()) for i in range(11)}
    xs = null_v2.cross_section(panels)
    got = _level(xs, panels, {"T00": [1]}, {"T00": [0.5]})
    assert got.slots == len(got.table) == 10            # pool of 10 < K
    assert got.unfilled == int((got.table.null_pos < 0).sum()) == 7
    assert list(got.table.null_ticker) == ["T01", "T02", "T03"] + [""] * 7
    assert got.table.fill[3:].isna().all() and got.dropped == Counter()


def test_an_event_without_any_fill_drops_but_does_not_starve():
    panels = {f"T{i:02d}": _panel(f"T{i:02d}", high=100.5, event=(1,) if i == 0 else ())
              for i in range(11)}
    xs = null_v2.cross_section(panels)
    got = _level(xs, panels, {"T00": [1]}, {"T00": [0.5]})
    assert got.dropped == Counter({"T00": 1}) and got.starved_dates == 0
    assert (got.slots, got.unfilled, len(got.table)) == (10, 10, 10)


def test_a_short_level_pool_drops_and_starves():
    xs, panels = _universe(4, T00={"event": (1,)})
    got = _level(xs, panels, {"T00": [1]}, {"T00": [0.5]})
    assert got.dropped == Counter({"T00": 1}) and (got.starved_dates, got.slots) == (1, 0)


def test_depths_need_one_value_per_booked_event():
    xs, panels = _universe()
    with pytest.raises(ValueError, match="depth"):
        _level(xs, panels, {"T00": [1, 2]}, {"T00": [0.5]})


def test_control_draw_requires_the_flag_and_uses_its_own_seed():
    xs, panels = _universe(40, **{f"T{i:02d}": {"control": [i % 3 != 0] * 5}
                                  for i in range(40)})
    got = null_v2.draw_control(xs, {"T01": [2]}, idea=IDEA)
    cols = [xs.tickers.index(t) for t in got.table.null_ticker]
    assert all(xs.control[2, j] for j in cols)
    pool = null_v2.ticker_pool(xs, 2, 1, require_control=True)
    rng = np.random.default_rng(null.null_seed("x:v2:control", "2015-01-07"))
    assert cols == np.sort(rng.choice(pool, size=null.K, replace=False)).tolist()


def test_control_below_the_floor_is_counted_never_refused():
    xs, _ = _universe(30, **{"T02": {"control": [True] * 5}, "T03": {"control": [True] * 5}})
    got = null_v2.draw_control(xs, {"T01": [2]}, idea=IDEA)
    assert got.dropped == Counter({"T01": 1}) and got.table.empty


def test_control_draw_without_a_control_flag_is_refused():
    xs, _ = _universe()
    with pytest.raises(ValueError, match="control"):
        null_v2.draw_control(xs, {"T01": [2]}, idea=IDEA)


def test_draw_dispatches_the_ticker_scope_next_open_draw():
    xs, panels = _universe()
    got = null_v2.draw(xs, panels, {"T01": [2]}, idea=_idea())
    want = null_v2.draw_ticker_scope(xs, {"T01": [2]}, idea=IDEA)
    pd.testing.assert_frame_equal(got.table, want.table)


def test_draw_dispatches_a_level_idea_and_needs_its_depths():
    xs, panels = _universe()
    idea = _idea(entry="level", levels=lambda df: df["Open"])
    with pytest.raises(ValueError, match="depth"):
        null_v2.draw(xs, panels, {"T01": [2]}, idea=idea)
    got = null_v2.draw(xs, panels, {"T01": [2]}, idea=idea, depths={"T01": [0.5]})
    pd.testing.assert_frame_equal(got.table,
                                  _level(xs, panels, {"T01": [2]}, {"T01": [0.5]}).table)


def _market_panels(event_pos):
    dates = pd.bdate_range("2015-01-05", periods=300)
    return {"AAA": _panel("AAA", n=300, dates=dates, event=(event_pos,))}


def test_draw_dispatches_a_market_idea_without_a_cross_section():
    panels = _market_panels(290)
    got = null_v2.draw(None, panels, {"AAA": [290]}, idea=_idea(scope="market"))
    want = null_v2.draw_market_scope(panels, {"AAA": [290]}, idea=IDEA, cap=4)
    pd.testing.assert_frame_equal(got.table, want.table)


def test_draw_refuses_a_starved_ticker_scope_before_any_race():
    xs, panels = _universe(3)
    with pytest.raises(null_v2.NullRefusal) as exc:
        null_v2.draw(xs, panels, {"T01": [2]}, idea=_idea())
    assert exc.value.code == null_v2.SCOPE_MISMATCH


def test_draw_refuses_a_starved_market_scope_before_any_race():
    with pytest.raises(null_v2.NullRefusal) as exc:
        null_v2.draw(None, _market_panels(3), {"AAA": [3]}, idea=_idea(scope="market"))
    assert exc.value.code == null_v2.NULL_STARVED
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_null_v2_level.py`
Expected: FAIL with `AttributeError: module ... has no attribute 'level_fill'`.

- [ ] **Step 3: Write the level, control and dispatcher section**

Append to `swingbot/core/backtesting/screen/null_v2.py` (add
`from typing import TYPE_CHECKING` to the imports and, below them,
`if TYPE_CHECKING:` / `    from swingbot.core.backtesting.screen.ideas import Idea`;
the annotation stays a string under `from __future__ import annotations`, so
no runtime import of `ideas`):

```python
def level_fill(bar_row, depth: float, direction: str) -> float:
    """One null bar's resting-order fill from its ``level_bars`` row (Open,
    High, Low, ATR14[t-1]): Open +/- depth x ATR when the bar reaches it (v1
    ``null._null_fills``); NaN when unreached or the ATR is not finite and > 0."""
    if direction not in ("long", "short"):
        raise ValueError(f"unknown direction {direction!r}; expected 'long' or 'short'")
    o, h, l, a = (float(v) for v in bar_row)
    if not (np.isfinite(a) and a > 0):
        return float("nan")
    if direction == "short":
        level = o - depth * a
        return level if l <= level else float("nan")
    level = o + depth * a
    return level if h >= level else float("nan")


def _depth_lookup(booked: Mapping, depths: Mapping) -> dict:
    """{(ticker, own position): depth}; one depth per booked event, in order."""
    out = {}
    for ticker, positions in booked.items():
        positions = np.asarray(positions, dtype=int)
        values = np.asarray(depths.get(ticker, ()), dtype=float)
        if values.shape != positions.shape:
            raise ValueError(f"{ticker}: a level draw needs one depth per booked event "
                             f"({values.size} for {positions.size})")
        out.update(zip(((ticker, p) for p in positions.tolist()), values.tolist()))
    return out


def _fill_at(xs: CrossSection, panels: Mapping, row: int, col: int, d: float,
             direction: str) -> float:
    bars = panels[xs.tickers[col]].level_bars
    if bars is None:
        raise ValueError(f"{xs.tickers[col]}: a level draw needs level_bars (keep_bars=True)")
    return level_fill(bars[xs.pos[row, col]], d, direction)


def _level_slots(xs, panels, row, pool, first, d, child, direction):
    """Filled (columns, fills) sorted by column: the first picks, then
    replacements from the rest of the pool in ``child.permutation`` order
    (v1 ``null._level_group``)."""
    m = len(first)
    cols, fills = [], []

    def take(candidates) -> None:
        for j in candidates:
            if len(cols) == m:
                return
            f = _fill_at(xs, panels, row, j, d, direction)
            if np.isfinite(f):
                cols.append(j)
                fills.append(f)

    take(first.tolist())
    rest = np.setdiff1d(pool, first)
    if len(cols) < m and rest.size:
        take(child.permutation(rest).tolist())
    order = np.argsort(np.asarray(cols, dtype=int), kind="stable")
    return np.asarray(cols, dtype=int)[order], np.asarray(fills, dtype=float)[order]


def _level_event(tally: _Tally, xs, panels, row, col, pos, d, rng, child, *,
                 direction: str, k: int) -> bool:
    """One level event's slots; True when its pool is under the floor."""
    ticker = xs.tickers[col]
    pool = ticker_pool(xs, row, col)
    if pool.size < null.MIN_CANDIDATES:
        tally.dropped[ticker] += 1
        return True
    m = min(k, pool.size)
    tally.count_slots(m)
    first = rng.choice(pool, size=m, replace=False)
    cols, fills = _level_slots(xs, panels, row, pool, first, d, child, direction)
    blank = m - cols.size
    tally.count_unfilled(blank)
    if cols.size == 0:
        tally.dropped[ticker] += 1
    day = xs.dates[row]
    tally.add(_records(ticker, pos, day, [xs.tickers[j] for j in cols], xs.pos[row, cols], fills))
    tally.add(_records(ticker, pos, day, [""] * blank, np.full(blank, -1)))
    return False


def draw_ticker_level(xs: CrossSection, panels: Mapping[str, TickerPanel], booked: Mapping,
                      depths: Mapping, *, idea: str, direction: str,
                      k: int = null.K) -> DrawResult:
    """Stage 2, level entry: the event's depth on each null ticker's own Open
    and ATR14[t-1]; an unfilled pick is replaced from the rest of the date's
    pool; a slot still unfilled is a blank row (null_ticker "", null_pos -1)."""
    lookup = _depth_lookup(booked, depths)
    tally = _Tally()
    for row, events in sorted(_events_by_row(xs, booked).items()):
        seed = date_seed(idea, xs.dates[row])
        rng, child = np.random.default_rng(seed), np.random.default_rng(null.child_seed(seed))
        starved = False
        for col, pos in events:
            d = lookup[(xs.tickers[col], pos)]
            starved |= _level_event(tally, xs, panels, row, col, pos, d, rng, child,
                                    direction=direction, k=k)
        tally.mark_date(xs.dates[row], starved)
    return tally.result()


def _control_seed(idea: str, day) -> list:
    return null.null_seed(f"{_v2_name(idea)}:control", pd.Timestamp(day).strftime("%Y-%m-%d"))


def draw_control(xs: CrossSection, booked: Mapping, *, idea: str,
                 k: int = null.K) -> DrawResult:
    """Avoid mode's control arm: the ticker-scope draw with the control flag
    required of every null ticker, on its own stream ``idea:v2:control``. Never
    refused; an event under the floor is counted in ``dropped`` (v1 below_floor)."""
    tally = _Tally()
    for row, events in sorted(_events_by_row(xs, booked).items()):
        day = xs.dates[row]
        rng = np.random.default_rng(_control_seed(idea, day))
        starved = False
        for col, pos in events:
            pool = ticker_pool(xs, row, col, require_control=True)
            if pool.size < null.MIN_CANDIDATES:
                tally.dropped[xs.tickers[col]] += 1
                starved = True
                continue
            pick = np.sort(rng.choice(pool, size=min(k, pool.size), replace=False))
            tally.count_slots(pick.size)
            tally.add(_records(xs.tickers[col], pos, day, [xs.tickers[j] for j in pick],
                               xs.pos[row, pick]))
        tally.mark_date(day, starved)
    return tally.result()


def draw(xs: CrossSection | None, panels: Mapping[str, TickerPanel], booked: Mapping, *,
         idea: Idea, depths: Mapping | None = None) -> DrawResult:
    """Stage 2 for one idea -- market scope, level entry or the ticker-scope
    next-open draw -- then the SCOPE_MISMATCH / NULL_STARVED refusal, so a
    starved pool stops the run before any race."""
    if idea.scope == "market":
        result = draw_market_scope(panels, booked, idea=idea.name, cap=idea.time_cap_bars)
    elif idea.entry == "level":
        if depths is None:
            raise ValueError(f"{idea.name}: a level draw needs one depth per booked event")
        result = draw_ticker_level(xs, panels, booked, depths, idea=idea.name,
                                   direction=idea.direction)
    else:
        result = draw_ticker_scope(xs, booked, idea=idea.name)
    check_starvation(result, idea.scope)
    return result
```

Also extend the module docstring's stage-2 paragraph with one sentence:
`Level entry: the event's depth on the null ticker's own Open and ATR14[t-1],
unfilled picks replaced on the child stream; avoid mode's control arm is the
same draw with the control flag required of j.`

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_null_v2_level.py`
Expected: PASS, 0 failed.

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_null_golden.py`
Expected: PASS (the ticker-scope draw and `_Tally` are untouched).

Complexity: `python scripts/dev/complexity_gate.py` — `_level_slots` (with its
inner `take`) and `draw` are the largest, both under 8.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/screen/null_v2.py tests/backtesting/screen/test_null_v2_level.py
git commit -m "feat(v230): v2 level-entry and avoid-control draws and the stage-2 dispatcher"
```

### Task V230-10: v2 race pass and scatter

**Model:** opus — stage 3 must race each null bar on its own ticker's frame and ATR14 with the idea's exact race (shape, direction, costs, level factor) while holding one frame at a time and resuming per ticker.

**Files:**
- Modify: `swingbot/core/backtesting/screen/null_v2.py` (imports; append the race section)
- Test: `tests/backtesting/screen/test_null_v2_race.py` (create)

**Interfaces:**
- Consumes: V230-6 `StageCheckpoint`, `open_stage`, `resumable_map`; V230-7 `DRAW_COLUMNS`, `_table` (test fixtures); V230-9's blank level rows (`null_pos = -1`); existing `race.race_for`, `race.LEVEL_SLIPPAGE_FACTOR`, `forward.forward_atr`, `forward.HORIZONS`.
- Produces: `UNFILLED = "unfilled"`; `race_pass(table, load, *, shape, cap, direction, costs, level_factor=race.LEVEL_SLIPPAGE_FACTOR, horizons=forward.HORIZONS, checkpoint=None, out=print) -> pd.DataFrame` (`table` has a unique index; `load(ticker) -> tuple[pd.DataFrame, pd.Series] | None`, the frame and its ATR14; output = every input column in input order plus `r`, `gross_r`, `outcome`, `fwd_<h>`, rows in input order); `@dataclass(frozen=True) EventNull(mean_r, mean_gross_r, outcomes: Counter, fwd: dict[int, float], timeout_r: tuple, slots: int, unfilled: int)`; `scatter(raced) -> dict[tuple[str, int], EventNull]` (horizons read from the `fwd_<h>` columns).

**Race rules (spec A2 stage 3, v1 `null.matched_null` tail):** rows with
`null_pos >= 0` are grouped by `null_ticker` (sorted); each group loads its
frame once, races its positions with
`race.race_for(shape)(df, positions, cap, atr=atr, **costs, **extra)` where
`extra` is `{"direction": direction}` for a short and adds
`fill=..., level_factor=...` when the group's `fill` values are finite (level
entry), and reads `forward.forward_atr(df, atr, h, direction=direction)` at
each position. The frame is dropped before the next group loads. Null races
are not book-filtered (as v1). Each finished group is saved under its
ticker in the `race` stage checkpoint; a resumed run never loads it again.
The per-event mean is the plain mean over its filled slots (v1 `part.mean()`);
`fwd` is the mean of the finite values, NaN when none (v1 `excess_drift`
drops non-finite null values).

- [ ] **Step 1: Write the failing tests**

Create `tests/backtesting/screen/test_null_v2_race.py`:

```python
"""v230 A2 stage 3: null slots raced on their own ticker's frame and ATR14,
one frame resident at a time, checkpointed per null ticker, then scattered
back to their events."""
import gc
import weakref
from collections import Counter

import numpy as np
import pandas as pd
import pytest

from swingbot.core.backtesting.screen import forward, indicators, null_v2, trail
from swingbot.core.backtesting.screen import race as race_mod
from tests.backtesting.screen.helpers import random_walk

CAP = 10
COSTS = {"slippage_bps": 5.0, "commission": 0.01}
FRAMES = {t: random_walk(400, seed=s) for t, s in (("AAA", 1), ("BBB", 2), ("CCC", 3))}
QUIET = {"out": lambda *a, **k: None}
NEXT_OPEN = [("AAA", 300, "BBB", 250), ("AAA", 300, "CCC", 260),
             ("CCC", 310, "BBB", 270), ("AAA", 320, "BBB", 280)]


def _load(ticker):
    df = FRAMES.get(ticker)
    return None if df is None else (df, indicators.atr(df))


def _table(rows):
    """rows: (event_ticker, event_pos, null_ticker, null_pos[, fill])."""
    return null_v2._table([(e, ep, FRAMES["AAA"].index[ep], n, p, rest[0] if rest else np.nan)
                           for e, ep, n, p, *rest in rows])


def _race(table, load=_load, **kw):
    kw = {"shape": "fixed", "cap": CAP, "direction": "long", "costs": COSTS, **QUIET, **kw}
    return null_v2.race_pass(table, load, **kw)


def _one(ticker, pos, **kw):
    df = FRAMES[ticker]
    return race_mod.race(df, [pos], CAP, atr=indicators.atr(df), **COSTS, **kw)


def test_each_slot_is_raced_on_its_own_frame_and_atr():
    raced = _race(_table(NEXT_OPEN))
    for row in raced.itertuples():
        want = _one(row.null_ticker, row.null_pos)
        assert row.r == pytest.approx(want.r[0])
        assert row.gross_r == pytest.approx(want.gross_r[0])
        assert row.outcome == want.outcome[0]
        df = FRAMES[row.null_ticker]
        assert row.fwd_20 == pytest.approx(
            forward.forward_atr(df, indicators.atr(df), 20)[row.null_pos], nan_ok=True)


def test_rows_keep_their_order_and_extra_columns():
    table = _table(NEXT_OPEN).assign(arm=["null", "control", "null", "null"])
    raced = _race(table)
    pd.testing.assert_frame_equal(raced[list(table.columns)], table)
    assert list(raced.columns[len(table.columns):]) == [
        "r", "gross_r", "outcome", "fwd_5", "fwd_10", "fwd_20", "fwd_60"]


def test_a_short_idea_races_and_reads_its_null_short():
    raced = _race(_table(NEXT_OPEN[:1]), direction="short")
    assert raced.r.iloc[0] == pytest.approx(_one("BBB", 250, direction="short").r[0])
    df = FRAMES["BBB"]
    assert raced.fwd_5.iloc[0] == pytest.approx(
        forward.forward_atr(df, indicators.atr(df), 5, direction="short")[250])


def test_the_trail_shape_races_its_null_on_the_trail():
    raced = _race(_table(NEXT_OPEN[:1]), shape="trail", cap=60)
    df = FRAMES["BBB"]
    want = trail.race_trail(df, [250], 60, atr=indicators.atr(df), **COSTS)
    assert raced.r.iloc[0] == pytest.approx(want.r[0])


def test_level_slots_race_from_their_fill_with_the_level_factor():
    df = FRAMES["BBB"]
    fills = [float(df["Open"].iloc[p]) * 1.001 for p in (250, 251)]
    raced = _race(_table([("AAA", 300, "BBB", 250, fills[0]), ("AAA", 300, "BBB", 251, fills[1])]),
                  level_factor=3.0)
    want = race_mod.race(df, [250, 251], CAP, atr=indicators.atr(df), fill=fills,
                         level_factor=3.0, **COSTS)
    np.testing.assert_allclose(raced.r, want.r)


def test_blank_level_slots_are_not_raced_and_read_unfilled():
    calls = []
    raced = _race(_table([("AAA", 300, "BBB", 250, 101.0), ("AAA", 300, "", -1)]),
                  load=lambda t: calls.append(t) or _load(t))
    assert calls == ["BBB"]
    blank = raced.iloc[1]
    assert blank.outcome == null_v2.UNFILLED
    assert np.isnan(blank.r) and np.isnan(blank.gross_r) and np.isnan(blank.fwd_60)


def test_level_and_next_open_slots_on_one_ticker_are_refused():
    with pytest.raises(ValueError, match="level and next-open"):
        _race(_table([("AAA", 300, "BBB", 250, 101.0), ("AAA", 300, "BBB", 251)]))


def test_a_null_ticker_without_a_frame_is_refused():
    with pytest.raises(ValueError, match="ZZZ"):
        _race(_table([("AAA", 300, "ZZZ", 250)]))


def test_only_one_null_frame_is_resident_at_a_time():
    alive = []

    def load(ticker):
        gc.collect()
        assert all(ref() is None for ref in alive), "a previous null frame is still held"
        df = FRAMES[ticker].copy()
        alive.append(weakref.ref(df))
        return df, indicators.atr(df)

    _race(_table(NEXT_OPEN), load=load)
    assert len(alive) == 2                      # BBB, then CCC


def test_finished_null_tickers_resume_from_their_checkpoint(tmp_path):
    checkpoint = null_v2.open_stage(tmp_path, "race", {"idea": "x"}, **QUIET)
    first = _race(_table(NEXT_OPEN), checkpoint=checkpoint)
    assert checkpoint.done() == {"BBB", "CCC"}

    def refuse(ticker):
        raise AssertionError(f"{ticker} was raced again")

    again = _race(_table(NEXT_OPEN), load=refuse, checkpoint=checkpoint)
    pd.testing.assert_frame_equal(again, first)


def test_an_empty_table_races_nothing():
    raced = _race(null_v2._table([]))
    assert raced.empty and {"r", "gross_r", "outcome", "fwd_60"} <= set(raced.columns)


def _raced(rows):
    return pd.DataFrame(rows, columns=["event_ticker", "event_pos", "null_pos", "r",
                                       "gross_r", "outcome", "fwd_5"])


def test_scatter_groups_slots_back_to_their_events():
    got = null_v2.scatter(_raced([
        ("AAA", 300, 250, 1.0, 1.1, "target", 0.5),
        ("AAA", 300, 251, -1.0, -0.9, "stop", np.nan),
        ("AAA", 300, 252, 0.2, 0.3, "timeout", 1.5),
        ("BBB", 40, 10, 0.4, 0.5, "timeout", 0.1)]))
    assert set(got) == {("AAA", 300), ("BBB", 40)}
    a = got[("AAA", 300)]
    assert a.mean_r == pytest.approx(0.2 / 3) and a.mean_gross_r == pytest.approx(0.5 / 3)
    assert a.outcomes == Counter({"target": 1, "stop": 1, "timeout": 1})
    assert set(a.fwd) == {5} and a.fwd[5] == pytest.approx(1.0)
    assert a.timeout_r == (0.2,) and (a.slots, a.unfilled) == (3, 0)


def test_blank_slots_count_as_unfilled_and_stay_out_of_the_means():
    got = null_v2.scatter(_raced([
        ("AAA", 300, 250, 1.0, 1.1, "target", 0.5),
        ("AAA", 300, -1, np.nan, np.nan, null_v2.UNFILLED, np.nan),
        ("BBB", 40, -1, np.nan, np.nan, null_v2.UNFILLED, np.nan)]))
    a, b = got[("AAA", 300)], got[("BBB", 40)]
    assert (a.mean_r, a.slots, a.unfilled, a.outcomes) == (1.0, 2, 1, Counter({"target": 1}))
    assert np.isnan(b.mean_r) and np.isnan(b.fwd[5])
    assert (b.slots, b.unfilled, b.outcomes, b.timeout_r) == (1, 1, Counter(), ())


def test_scatter_of_nothing_is_empty():
    assert null_v2.scatter(_raced([])) == {}


def test_race_then_scatter_gives_each_event_the_mean_of_its_raced_slots():
    raced = _race(_table(NEXT_OPEN))
    got = null_v2.scatter(raced)
    want = np.mean([_one("BBB", 250).r[0], _one("CCC", 260).r[0]])
    assert got[("AAA", 300)].mean_r == pytest.approx(want)
    assert got[("AAA", 300)].slots == 2
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_null_v2_race.py`
Expected: FAIL with `AttributeError: module ... has no attribute 'race_pass'`.

- [ ] **Step 3: Write the race section**

In `swingbot/core/backtesting/screen/null_v2.py` change the imports to
`from collections import Counter, defaultdict` and
`from swingbot.core.backtesting.screen import forward, null, race as race_mod`
(neither `forward` nor `race` imports `null_v2`, so no cycle), then append:

```python
#: Stage 3's outcome for a level slot that never filled; it is never raced.
UNFILLED = "unfilled"
_KEYS = ["event_ticker", "event_pos"]


def _fwd_name(h: int) -> str:
    return f"fwd_{h}"


def _race_rows(part: pd.DataFrame, df: pd.DataFrame, atr, *, shape: str, cap: int,
               direction: str, costs: Mapping, level_factor: float, horizons) -> pd.DataFrame:
    """One null ticker's slots raced on its own frame and ATR14 (v1 matched_null tail)."""
    pos = part["null_pos"].to_numpy(dtype=int)
    fill = part["fill"].to_numpy(dtype=float)
    level = np.isfinite(fill)
    if level.any() and not level.all():
        raise ValueError(f"{part['null_ticker'].iloc[0]}: level and next-open slots "
                         "on one null ticker")
    extra = {} if direction == "long" else {"direction": direction}
    if level.all():
        extra.update(fill=fill, level_factor=level_factor)
    raced = race_mod.race_for(shape)(df, pos, cap, atr=atr, **costs, **extra)
    out = part.assign(r=raced.r, gross_r=raced.gross_r, outcome=raced.outcome.astype(object))
    for h in horizons:
        out[_fwd_name(h)] = forward.forward_atr(df, atr, h, direction=direction)[pos]
    return out


def _blank_rows(part: pd.DataFrame, horizons) -> pd.DataFrame:
    out = part.assign(r=np.nan, gross_r=np.nan, outcome=UNFILLED)
    for h in horizons:
        out[_fwd_name(h)] = np.nan
    return out.astype({"outcome": object})


def race_pass(table: pd.DataFrame, load: Callable, *, shape: str, cap: int, direction: str,
              costs: Mapping, level_factor: float = race_mod.LEVEL_SLIPPAGE_FACTOR,
              horizons=forward.HORIZONS, checkpoint: StageCheckpoint | None = None,
              out=print) -> pd.DataFrame:
    """Stage 3: every filled slot raced on its null ticker's own frame and
    ATR14, one ticker's frame resident at a time, each finished ticker saved to
    ``checkpoint``; blank level slots read UNFILLED. Rows keep their order."""
    checkpoint = StageCheckpoint(None) if checkpoint is None else checkpoint
    filled = table["null_pos"].to_numpy() >= 0
    sub = table[filled]
    groups = sub.groupby("null_ticker", sort=True).indices
    kw = {"shape": shape, "cap": cap, "direction": direction, "costs": costs,
          "level_factor": level_factor, "horizons": horizons}

    def one(ticker: str) -> pd.DataFrame:
        loaded = load(ticker)
        if loaded is None:
            raise ValueError(f"null ticker {ticker} has no frame to race on")
        df, atr = loaded
        return _race_rows(sub.iloc[groups[ticker]], df, atr, **kw)

    raced = resumable_map(sorted(groups), one, checkpoint=checkpoint, out=out, label="race")
    parts = [raced[t] for t in sorted(raced)]
    if not filled.all():
        parts.append(_blank_rows(table[~filled], horizons))
    if not parts:
        return _blank_rows(table, horizons)
    return pd.concat(parts).loc[table.index]


@dataclass(frozen=True)
class EventNull:
    """One event's null after stage 3: means over its filled slots."""
    mean_r: float
    mean_gross_r: float
    outcomes: Counter
    fwd: dict
    timeout_r: tuple
    slots: int
    unfilled: int


def _outcome_counters(filled: pd.DataFrame) -> dict:
    counters: dict = defaultdict(Counter)
    if not filled.empty:
        for (t, p, outcome), n in filled.groupby(_KEYS)["outcome"].value_counts().items():
            counters[(t, p)][outcome] = int(n)
    return counters


def _timeouts(filled: pd.DataFrame) -> dict:
    out: dict = defaultdict(list)
    hit = filled.loc[filled["outcome"] == "timeout", [*_KEYS, "r"]]
    for t, p, r in hit.itertuples(index=False):
        out[(t, p)].append(float(r))
    return out


def scatter(raced: pd.DataFrame) -> dict[tuple[str, int], EventNull]:
    """Stage 3 back to events: one EventNull per (event ticker, event position)."""
    if raced.empty:
        return {}
    fwd_cols = sorted((c for c in raced.columns if c.startswith("fwd_")),
                      key=lambda c: int(c[4:]))
    filled = raced[raced["null_pos"].to_numpy() >= 0]
    slots = raced.groupby(_KEYS).size()
    means = filled.groupby(_KEYS)[["r", "gross_r", *fwd_cols]].mean().reindex(slots.index)
    n_filled = filled.groupby(_KEYS).size().reindex(slots.index, fill_value=0)
    outcomes, timeouts = _outcome_counters(filled), _timeouts(filled)
    return {(str(t), int(p)): EventNull(
                float(m["r"]), float(m["gross_r"]), outcomes[(t, p)],
                {int(c[4:]): float(m[c]) for c in fwd_cols}, tuple(timeouts[(t, p)]),
                int(slots[(t, p)]), int(slots[(t, p)] - n_filled[(t, p)]))
            for (t, p), m in means.iterrows()}
```

Also extend the module docstring's stage-3 paragraph with one sentence:
`Rows keep the draw table's order; a blank level slot is never raced and
reads "unfilled".`

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_null_v2_race.py`
Expected: PASS, 0 failed.

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_null_v2_level.py`
Expected: PASS (the draw section is untouched).

Complexity: `python scripts/dev/complexity_gate.py` — `_race_rows` and
`race_pass` are the largest, both under 8.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/screen/null_v2.py tests/backtesting/screen/test_null_v2_race.py
git commit -m "feat(v230): v2 null stage 3 -- race pass per null ticker and scatter to events"
```

### Task V230-11: v2 orchestration with staged checkpoints

**Model:** opus — wires the three stages into one resumable run and decides which v1 per-ticker fields survive a cross-ticker null; V230-12's adapter and every v2 verdict read its output.

**Files:**
- Create: `swingbot/core/backtesting/screen/screen_v2.py`
- Test: `tests/backtesting/screen/test_screen_v2.py` (create)

**Interfaces:**
- Consumes: V230-1 `Idea.scope`; V230-6 `ticker_panel`, `cross_section`, `open_stage`, `resumable_map`; V230-7 `NullRefusal`, `draw_ticker_scope` (test); V230-9 `draw`, `draw_control`; V230-10 `race_pass`, `scatter`, `EventNull`; existing `race.run_book`, `race.level_fills`, `forward.forward_atr`, `indicators.atr`.
- Produces: `@dataclass(frozen=True) V2Inputs(load, context, extras)`; `@dataclass V2Ticker(ticker, counters, events, null_outcomes, excess, extras, null_timeout_r, null_slots, null_unfilled, depths, avoid_control)`; event row keys `ticker, entry_date, exit_date, r_event, r_null, outcome, cost_event, cost_null` (`cost_* = gross_r - r`, the mean over filled slots for the null); `run_v2(idea, names, inputs, *, costs, checkpoint_dir=None, manifest=None, out=print, event_tickers=None) -> list[V2Ticker]` (sorted by ticker, event tickers that loaded only). Counters, stage keys, `extras` context and kept-event rule: part header.

**Run (spec A2, index Decisions):** `names` is the whole cached universe (the
pool is the cross-section); `event_tickers` restricts the event book only.
Stage 1 per ticker: panel, and for event tickers the event book exactly as v1
`_books` races it, the level depths, the event's forward drift and `extras`.
Stage 2: `null_v2.draw` (which refuses), plus `draw_control` over the kept
events in avoid mode. Stage 3: both tables in one `race_pass` (an `arm`
column), then `scatter` per arm.

- [ ] **Step 1: Write the failing tests**

Create `tests/backtesting/screen/test_screen_v2.py`:

```python
"""v230 A2: run_v2 runs panel -> draw -> race with staged checkpoints and
returns one V2Ticker per event ticker; a starved pool refuses before stage 3."""
import json

import numpy as np
import pandas as pd
import pytest

from swingbot.core.backtesting.screen import forward, indicators, null, null_v2, race, screen_v2
from swingbot.core.backtesting.screen.ideas import Idea
from tests.backtesting.screen.helpers import random_walk

FRAMES = {f"T{i:02d}": random_walk(500, seed=100 + i) for i in range(90)}
COSTS = {"slippage_bps": 5.0, "commission": 0.01}
QUIET = {"out": lambda *a, **k: None}
ROW_KEYS = {"ticker", "entry_date", "exit_date", "r_event", "r_null", "outcome",
            "cost_event", "cost_null"}


def _breakout(df):
    return df["Close"] > df["Close"].rolling(20).max().shift(1)


def _month_end(df):
    months = df.index.to_series().dt.month
    return months != months.shift(-1)


IDEA = Idea(name="x", events=_breakout, time_cap_bars=10)


def _context(idea):
    def context(name, df):
        atr, sma200 = indicators.atr(df), indicators.sma(df["Close"], 200)
        levels = None if idea.levels is None else idea.levels(df).to_numpy(dtype=float)
        return {"raw": idea.events(df).fillna(False).to_numpy(dtype=bool),
                "member": null.member_mask(df.index, None),
                "warm": race.warm_mask(atr, sma200), "atr": atr,
                "trend": null.trend_state(df, sma200), "levels": levels}
    return context


def _inputs(idea=IDEA, frames=FRAMES, loads=None):
    def load(name):
        if loads is not None:
            loads.append(name)
        return frames.get(name)
    return screen_v2.V2Inputs(load, _context(idea),
                              lambda name, df, ctx: {"booked": len(ctx["book"])})


def _run(idea=IDEA, names=FRAMES, inputs=None, **kw):
    return screen_v2.run_v2(idea, sorted(names), inputs or _inputs(idea), costs=COSTS,
                            **QUIET, **kw)


def _independent_draw():
    ctxs = {t: _context(IDEA)(t, df) for t, df in FRAMES.items()}
    panels = {t: null_v2.ticker_panel(t, FRAMES[t], c, cap=10) for t, c in ctxs.items()}
    booked = {t: race.run_book(FRAMES[t], c["raw"], 10, member=c["member"], warm=c["warm"],
                               atr=c["atr"], **COSTS)[0].event_pos for t, c in ctxs.items()}
    return null_v2.draw_ticker_scope(null_v2.cross_section(panels), booked, idea="x").table


def _pos(row):
    return FRAMES[row["ticker"]].index.get_loc(pd.Timestamp(row["entry_date"])) - 1


def test_each_event_pairs_its_book_race_with_its_raced_null_slots():
    screens = _run(names=[*FRAMES, "ZZZ"])                  # ZZZ has no frame: skipped
    assert [s.ticker for s in screens] == sorted(FRAMES)
    s = next(s for s in screens if s.events)
    row, table = s.events[0], _independent_draw()
    pos, df = _pos(row), FRAMES[s.ticker]
    slots = table[(table.event_ticker == s.ticker) & (table.event_pos == pos)]
    rs = [race.race(FRAMES[t], [p], 10, atr=indicators.atr(FRAMES[t]), **COSTS).r[0]
          for t, p in zip(slots.null_ticker, slots.null_pos)]
    want = race.race(df, [pos], 10, atr=indicators.atr(df), **COSTS)
    assert set(row) == ROW_KEYS
    assert row["r_null"] == pytest.approx(np.mean(rs))
    assert row["r_event"] == pytest.approx(want.r[0])
    assert row["cost_event"] == pytest.approx(want.gross_r[0] - want.r[0])
    assert s.extras == {"booked": len(s.events) + s.counters["dropped_no_match"]}


def test_null_counts_and_drift_come_from_the_null_tickers_frames():
    s = next(s for s in _run() if s.events)
    assert sum(s.null_outcomes.values()) == s.null_slots and s.null_unfilled == 0
    assert set(s.excess) == set(forward.HORIZONS) and len(s.excess[5]) == len(s.events)
    assert (s.depths, s.avoid_control, s.null_timeout_r) == (None, None, [])


def test_a_resumed_run_loads_nothing_and_returns_the_same_screens(tmp_path):
    first = _run(checkpoint_dir=tmp_path, manifest={"idea": "x", "start": "s"})
    loads = []
    again = _run(inputs=_inputs(loads=loads), checkpoint_dir=tmp_path,
                 manifest={"idea": "x", "start": "s"})
    assert loads == [] and [s.events for s in again] == [s.events for s in first]
    for stage in null_v2.STAGES:
        saved = json.loads((tmp_path / stage / null_v2.STAGE_MANIFEST).read_text(encoding="utf-8"))
        assert (saved["null_version"], saved["stage"], saved["scope"], saved["start"]) == (
            "v2", stage, "ticker", "s")


def test_a_v1_checkpoint_never_resumes_under_v2(tmp_path):
    (tmp_path / "T00.pkl").write_bytes(b"v1")
    with pytest.raises(ValueError, match="v1"):
        _run(checkpoint_dir=tmp_path)


def test_event_tickers_restrict_the_book_but_not_the_pool(tmp_path):
    screens = _run(event_tickers=["T03"], checkpoint_dir=tmp_path)
    assert [s.ticker for s in screens] == ["T03"]
    full = next(s for s in _run() if s.ticker == "T03")
    assert ([(r["entry_date"], r["r_event"]) for r in screens[0].events]
            == [(r["entry_date"], r["r_event"]) for r in full.events])
    with pytest.raises(ValueError, match="another run"):
        _run(event_tickers=["T04"], checkpoint_dir=tmp_path)


def test_a_starved_pool_refuses_after_the_draw_and_before_any_race(tmp_path):
    few = {t: FRAMES[t] for t in ("T00", "T01", "T02")}
    with pytest.raises(null_v2.NullRefusal) as exc:
        _run(names=few, inputs=_inputs(frames=few), checkpoint_dir=tmp_path)
    assert exc.value.code == null_v2.SCOPE_MISMATCH
    assert (tmp_path / "draw").is_dir() and not (tmp_path / "race").exists()


def test_a_level_idea_reports_event_and_null_depths():
    idea = Idea(name="lvl", events=lambda df: df["High"] > df["Open"] * 1.012,
                time_cap_bars=10, entry="level", levels=lambda df: df["Open"] * 1.012)
    screens = _run(idea=idea, inputs=_inputs(idea))
    s = next(s for s in screens if s.events)
    df = FRAMES[s.ticker]
    pos = df.index.get_loc(pd.Timestamp(s.events[0]["entry_date"]))   # level: entry on the event bar
    assert df["High"].iloc[pos] > df["Open"].iloc[pos] * 1.012
    assert len(s.depths["event"]) == len(s.events)
    assert len(s.depths["null"]) == s.null_slots - s.null_unfilled
    assert all(d > 0 for d in s.depths["event"])


def _avoid_context(name, df):
    ctx = _context(IDEA)(name, df)
    bars = np.arange(len(df))
    return {**ctx, "condition": bars % 7 == 3, "control_condition": bars % 2 == 0}


def test_an_avoid_idea_carries_its_control_arm():
    idea = Idea(name="av", events=_breakout, time_cap_bars=10, mode="avoid",
                states=lambda df: None)
    inputs = screen_v2.V2Inputs(FRAMES.get, _avoid_context, lambda *a: {})
    screens = screen_v2.run_v2(idea, sorted(FRAMES), inputs, costs=COSTS, **QUIET)
    rows = [r for s in screens for r in s.avoid_control]
    below = sum(s.counters["control_below_floor"] for s in screens)
    assert rows and below
    assert len(rows) + below == sum(len(s.events) for s in screens)
    assert all(_pos(r) % 2 == 0 for r in rows) and set(rows[0]) == ROW_KEYS


def test_a_market_idea_runs_without_a_cross_section():
    idea = Idea(name="mkt", events=_month_end, time_cap_bars=4, scope="market")
    screens = _run(idea=idea, inputs=_inputs(idea))
    rows = [r for s in screens for r in s.events]
    assert rows and all(np.isfinite(r["r_null"]) for r in rows)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_screen_v2.py`
Expected: FAIL with `ImportError: cannot import name 'screen_v2'`.

- [ ] **Step 3: Write the module**

Create `swingbot/core/backtesting/screen/screen_v2.py`:

```python
"""v230 A2: one idea's v2 screen -- stage 1 (panel and event book per ticker),
stage 2 (one draw, which refuses a starved pool), stage 3 (race per null
ticker) -- each stage checkpointed under ``<checkpoint_dir>/<stage>/``.

Frame loading, the per-ticker context and the event-side blocks that read no
null (rank, overlap) come from the caller through V2Inputs, so this module
never imports scripts/backtest/screen_idea.py.
"""
from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass

import numpy as np
import pandas as pd

from swingbot.core.backtesting.screen import forward, indicators, null_v2, race

#: bars from the event bar to the entry bar (screen_idea._ENTRY_OFFSET).
_ENTRY_OFFSET = {"next_open": 1, "level": 0}


@dataclass(frozen=True)
class V2Inputs:
    load: Callable[[str], pd.DataFrame | None]
    context: Callable[[str, pd.DataFrame], dict]
    extras: Callable[[str, pd.DataFrame, dict], dict]


@dataclass
class V2Ticker:
    ticker: str
    counters: Counter
    events: list
    null_outcomes: Counter
    excess: dict
    extras: dict
    null_timeout_r: list
    null_slots: int
    null_unfilled: int
    depths: dict | None
    avoid_control: list | None


@dataclass(frozen=True, eq=False)
class _Book:
    """Stage 1's event side for one event ticker."""
    raced: race.RaceResult
    counts: dict
    depths: np.ndarray | None
    fwd: dict
    extras: dict


def _book(idea, df: pd.DataFrame, ctx: Mapping, costs: Mapping):
    """The event book exactly as v1 ``_books`` races it, and its level depths."""
    level = idea.entry == "level"
    kw = {"levels": ctx["levels"]} if level else {}
    booked, counts = race.run_book(df, ctx["raw"], idea.time_cap_bars, member=ctx["member"],
                                   warm=ctx["warm"], atr=ctx["atr"], shape=idea.race_shape,
                                   direction=idea.direction, **costs, **kw)
    depths = None
    if level:
        depths = (race.level_fills(df, booked.event_pos, ctx["levels"], ctx["atr"],
                                   idea.direction)[1]
                  if len(booked) else np.array([], dtype=float))
    return booked, counts, depths


def _stage1(idea, name: str, inputs: V2Inputs, costs: Mapping, is_event: bool) -> dict | None:
    df = inputs.load(name)
    if df is None:
        return None
    ctx = inputs.context(name, df)
    control = ctx.get("control_condition") if idea.mode == "avoid" else None
    panel = null_v2.ticker_panel(name, df, ctx, cap=idea.time_cap_bars, control=control,
                                 keep_bars=idea.entry == "level")
    if not is_event:
        return {"panel": panel, "book": None}
    booked, counts, depths = _book(idea, df, ctx, costs)
    fwd = {h: forward.forward_atr(df, ctx["atr"], h, direction=idea.direction)[booked.event_pos]
           for h in forward.HORIZONS}
    extras = inputs.extras(name, df, {**ctx, "book": booked})
    return {"panel": panel, "book": _Book(booked, dict(counts), depths, fwd, extras)}


def _kept(table: pd.DataFrame) -> dict:
    filled = table[table["null_pos"] >= 0]
    return {t: np.unique(g["event_pos"].to_numpy(dtype=int))
            for t, g in filled.groupby("event_ticker")}


def _draw_stage(idea, units: Mapping, checkpoint) -> tuple:
    saved = checkpoint.load("draw")
    if saved is not None:
        return saved
    panels = {t: u["panel"] for t, u in units.items()}
    books = {t: u["book"] for t, u in units.items() if u["book"] is not None}
    depths = {t: b.depths for t, b in books.items()} if idea.entry == "level" else None
    xs = None if idea.scope == "market" else null_v2.cross_section(panels)
    result = null_v2.draw(xs, panels, {t: b.raced.event_pos for t, b in books.items()},
                          idea=idea, depths=depths)
    control = (null_v2.draw_control(xs, _kept(result.table), idea=idea.name)
               if idea.mode == "avoid" else None)
    checkpoint.save("draw", (result, control))
    return result, control


def _race_stage(idea, result, control, inputs: V2Inputs, costs: Mapping, checkpoint, out):
    def load(ticker):
        df = inputs.load(ticker)
        return None if df is None else (df, indicators.atr(df))

    tables = [result.table.assign(arm="null")]
    if control is not None:
        tables.append(control.table.assign(arm="control"))
    raced = null_v2.race_pass(pd.concat(tables, ignore_index=True), load,
                              shape=idea.race_shape, cap=idea.time_cap_bars,
                              direction=idea.direction, costs=costs,
                              checkpoint=checkpoint, out=out)
    nulls = null_v2.scatter(raced[raced["arm"] == "null"])
    controls = None if control is None else null_v2.scatter(raced[raced["arm"] == "control"])
    return nulls, controls


def _arm_rows(ticker: str, dates: pd.DatetimeIndex, book: _Book, nulls: Mapping,
              offset: int) -> tuple[list, list]:
    """Rows for the booked events whose null has a filled slot, and (i, EventNull)."""
    rows, kept, rr = [], [], book.raced
    for i, pos in enumerate(rr.event_pos.tolist()):
        en = nulls.get((ticker, pos))
        if en is None or en.slots == en.unfilled:
            continue
        r, gross = float(rr.r[i]), float(rr.gross_r[i])
        rows.append({"ticker": ticker,
                     "entry_date": dates[pos + offset].strftime("%Y-%m-%d"),
                     "exit_date": dates[rr.exit_pos[i]].strftime("%Y-%m-%d"),
                     "r_event": r, "r_null": en.mean_r, "outcome": str(rr.outcome[i]),
                     "cost_event": gross - r, "cost_null": en.mean_gross_r - en.mean_r})
        kept.append((i, en))
    return rows, kept


def _excess(book: _Book, kept: list) -> dict:
    """Event minus null forward drift per horizon, finite pairs only (v1 excess_drift)."""
    out = {h: [] for h in forward.HORIZONS}
    for i, en in kept:
        for h in forward.HORIZONS:
            ev, nl = float(book.fwd[h][i]), en.fwd.get(h, np.nan)
            if np.isfinite(ev) and np.isfinite(nl):
                out[h].append(ev - nl)
    return out


def _depths(idea, book: _Book, kept: list) -> dict | None:
    """Level only: a filled null slot's realised depth is its event's depth."""
    if idea.entry != "level":
        return None
    return {"event": [float(book.depths[i]) for i, _ in kept],
            "null": [float(book.depths[i]) for i, en in kept
                     for _ in range(en.slots - en.unfilled)]}


def _ticker(idea, name: str, unit: Mapping, result, control, nulls, controls) -> V2Ticker:
    book, dates = unit["book"], pd.DatetimeIndex(unit["panel"].dates)
    offset = _ENTRY_OFFSET[idea.entry]
    events, kept = _arm_rows(name, dates, book, nulls, offset)
    counters = Counter(book.counts)
    counters["dropped_no_match"] = int(result.dropped.get(name, 0))
    avoid_rows = None
    if controls is not None:
        avoid_rows = _arm_rows(name, dates, book, controls, offset)[0]
        counters["control_below_floor"] = int(control.dropped.get(name, 0))
    mine = [nulls[(name, p)] for p in book.raced.event_pos.tolist() if (name, p) in nulls]
    timeouts = [r for _, en in kept for r in en.timeout_r] if idea.race_shape == "trail" else []
    return V2Ticker(ticker=name, counters=counters, events=events,
                    null_outcomes=sum((en.outcomes for _, en in kept), Counter()),
                    excess=_excess(book, kept), extras=book.extras, null_timeout_r=timeouts,
                    null_slots=sum(en.slots for en in mine),
                    null_unfilled=sum(en.unfilled for en in mine),
                    depths=_depths(idea, book, kept), avoid_control=avoid_rows)


def _manifest(idea, manifest: Mapping | None, costs: Mapping, event_tickers) -> dict:
    digest = None
    if event_tickers is not None:
        digest = hashlib.sha256("\n".join(sorted(event_tickers)).encode("utf-8")).hexdigest()
    return {"idea": idea.name, **(manifest or {}), "scope": idea.scope,
            "event_tickers_sha256": digest, "costs": dict(costs)}


def run_v2(idea, names, inputs: V2Inputs, *, costs: Mapping, checkpoint_dir=None,
           manifest: Mapping | None = None, out=print, event_tickers=None) -> list[V2Ticker]:
    """The v2 screen of ``idea`` over ``names`` (the pool's whole universe).
    ``event_tickers`` restricts the event book, never the pool. Raises
    ``null_v2.NullRefusal`` after stage 2, before any race."""
    full = _manifest(idea, manifest, costs, event_tickers)
    events = set(names) if event_tickers is None else set(event_tickers)
    units = null_v2.resumable_map(
        sorted(names), lambda n: _stage1(idea, n, inputs, costs, n in events),
        checkpoint=null_v2.open_stage(checkpoint_dir, "panel", full, out),
        out=out, label=f"[{idea.name}] panel")
    result, control = _draw_stage(idea, units,
                                  null_v2.open_stage(checkpoint_dir, "draw", full, out))
    nulls, controls = _race_stage(idea, result, control, inputs, costs,
                                  null_v2.open_stage(checkpoint_dir, "race", full, out), out)
    return [_ticker(idea, t, units[t], result, control, nulls, controls)
            for t in sorted(units) if units[t]["book"] is not None]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_screen_v2.py`
Expected: PASS, 0 failed.

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_import_guard.py`
Expected: PASS (the module sits under `swingbot/core/backtesting/screen/` and imports no script).

Complexity: `python scripts/dev/complexity_gate.py` — `_ticker` and `_arm_rows`
are the largest, both under 8.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/screen/screen_v2.py tests/backtesting/screen/test_screen_v2.py
git commit -m "feat(v230): run_v2 -- the three v2 stages with staged checkpoints"
```

