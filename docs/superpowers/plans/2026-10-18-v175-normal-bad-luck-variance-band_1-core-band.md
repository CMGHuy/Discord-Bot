# v175 Normal bad luck, part 1: core band (close days, week-block sampler, assembly, calibration)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time: `grep -n "^### Task V175-2:" -A 400 docs/superpowers/plans/2026-10-18-v175-normal-bad-luck-variance-band_1-core-band.md`.

**Spec:** [`docs/superpowers/specs/2026-10-18-v175-normal-bad-luck-variance-band-design.md`](../specs/2026-10-18-v175-normal-bad-luck-variance-band-design.md)
**Index:** [`2026-10-18-v175-normal-bad-luck-variance-band_0-index.md`](2026-10-18-v175-normal-bad-luck-variance-band_0-index.md) — **Global Constraints, Parallelisation, the task ledger and `$WT`/`$R` are defined there; every task below implicitly includes the Global Constraints.**

`$WT` = `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v175-normal-bad-luck-variance-band`, `$R` = `E:/Documents/Private/Projects/Discord-Bot`. Never `cd`; use absolute paths and `git -C $WT`.

All four tasks build one pure module, `swingbot/core/analytics/variance_band.py`, and its tests in `tests/analytics/` (suite `edge-analytics`). No test touches a database: inputs are trade dicts built in the test file.

# Phase 1 — Core band

### Task V175-1: Worktree; constants, ET close date, close-day series, current run and window drawdown

**Model:** sonnet — pure series code inside one module, rules given by the spec

**Files:**
- Create: `swingbot/core/analytics/variance_band.py`
- Test: `tests/analytics/test_variance_band_days.py` (suite `edge-analytics`)

**Interfaces:**
- Consumes (existing): `metrics.r_multiple(trade: dict) -> float | None` (`swingbot/core/analytics/metrics.py:173`), `stats.WEEK_BOOTSTRAP_SEED = 42` (`swingbot/core/backtesting/instrument/stats.py:25`), `session.US_MARKET_TZ` (`swingbot/core/market/session.py:12`).
- Produces (ledger contract, consumed by V175-2..V175-4 and, through `variance_band`, by part 2):
  - every frozen constant of Global Constraints: `MIN_DAYS`, `MIN_WEEKS`, `HORIZONS`, `WINDOW`, `PATHS`, `SEED`, `SCRATCH_R`, `ROUGH_PCT`, `OUTSIDE_PCT`, `OUTER_RESAMPLES`, `OUTER_PATHS`, `CI_PCT`, `EXPR_RESAMPLES`, `EXPR_CI_PCT`, `ZONES`, `CAVEAT`
  - `@dataclass(frozen=True) class CloseDay: day: date; r: float; kind: str`
  - `et_close_date(closed_at: str) -> date`
  - `day_kind(r: float) -> str` — `"loss"` / `"win"` / `"scratch"`
  - `close_days(trades: list[dict]) -> list[CloseDay]` — date order
  - `current_run(days: list[CloseDay]) -> tuple[int, date | None]` — length, first loss day of the run
  - `window_drawdown(days: list[CloseDay], window: int = WINDOW) -> tuple[float, date | None]` — peak-to-now R (2 dp), peak day
  - `zone_of(value: float, p80: float, p95: float) -> str`
  - `worse_zone(a: str, b: str) -> str`

- [ ] **Step 1: Create or reuse the worktree**

Invoke the `worktree-lifecycle` skill. Then:

```bash
git -C E:/Documents/Private/Projects/Discord-Bot worktree list
```

If `.claude/worktrees/2026-10-18-v175-normal-bad-luck-variance-band` is listed, reuse it (resume at its first uncommitted task). Otherwise:

```bash
git -C E:/Documents/Private/Projects/Discord-Bot worktree add .claude/worktrees/2026-10-18-v175-normal-bad-luck-variance-band -b 2026-10-18-v175-normal-bad-luck-variance-band main
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v175-normal-bad-luck-variance-band log --oneline -1
```

Expected: the worktree exists on branch `2026-10-18-v175-normal-bad-luck-variance-band`, at `main`'s HEAD (which carries this plan).

- [ ] **Step 2: Confirm the symbols this task reads**

```bash
git -C $WT grep -n "^def r_multiple\|^WEEK_BOOTSTRAP_SEED\|^def iso_week_key\|^US_MARKET_TZ" -- swingbot
git -C $WT ls-files swingbot/core/analytics/variance_band.py tests/analytics/test_variance_band_days.py
```

Expected: `metrics.py:173 def r_multiple`, `stats.py:25 WEEK_BOOTSTRAP_SEED = 42`, `stats.py:28 def iso_week_key`, `session.py:12 US_MARKET_TZ`; the `ls-files` prints nothing (both files are new).

- [ ] **Step 3: Write the failing tests**

Create `$WT/tests/analytics/test_variance_band_days.py`:

```python
"""v175 § 1: the close-day series and the current state (run, window drawdown).

Trades are built with entry 100, stop 99 (1 point of risk), bullish, so a
trade's R is exactly ``exit_price - 100``.
"""
from datetime import date, timedelta

import pytest

from swingbot.core.analytics import variance_band as vb
from swingbot.core.analytics.variance_band import CloseDay


def _trade(r, closed_at, **extra):
    return {"entry": 100.0, "stop_loss": 99.0, "direction": "bullish",
            "exit_price": 100.0 + r, "closed_at": closed_at,
            "status": "loss" if r < 0 else "win", **extra}


def _days(*rs, start=date(2026, 1, 5)):
    """CloseDay list, one per consecutive calendar day, kinds from day_kind."""
    return [CloseDay(start + timedelta(days=i), r, vb.day_kind(r))
            for i, r in enumerate(rs)]


def test_frozen_constants():
    assert (vb.MIN_DAYS, vb.MIN_WEEKS, vb.HORIZONS, vb.WINDOW) == (100, 20, (20, 50), 50)
    assert vb.WINDOW == vb.HORIZONS[-1]
    assert (vb.PATHS, vb.SEED, vb.SCRATCH_R) == (10_000, 42, 0.05)
    assert (vb.ROUGH_PCT, vb.OUTSIDE_PCT) == (80, 95)
    assert (vb.OUTER_RESAMPLES, vb.OUTER_PATHS, vb.CI_PCT) == (200, 1_000, (10, 90))
    assert (vb.EXPR_RESAMPLES, vb.EXPR_CI_PCT) == (10_000, (2.5, 97.5))
    assert vb.ZONES == ("normal", "rough", "outside")
    assert vb.CAVEAT == ("This book's past results are not positive. "
                         "A run within their range is still a losing run.")
    assert "edge" not in vb.CAVEAT.lower()


@pytest.mark.parametrize("closed_at, expected", [
    ("2026-03-10T19:59:00+00:00", date(2026, 3, 10)),   # 15:59 EDT, in session
    ("2026-03-11T01:30:00+00:00", date(2026, 3, 10)),   # 21:30 EDT: after hours, same NYSE day
    ("2026-03-11T01:30:00", date(2026, 3, 10)),         # naive is read as UTC
    ("2026-01-06T03:00:00Z", date(2026, 1, 5)),         # 22:00 EST the day before
    ("2026-01-06T14:30:00+00:00", date(2026, 1, 6)),    # 09:30 EST
])
def test_et_close_date_puts_an_after_hours_close_on_its_session(closed_at, expected):
    assert vb.et_close_date(closed_at) == expected


@pytest.mark.parametrize("r, kind", [
    (-1.0, "loss"), (-0.0501, "loss"), (-0.05, "scratch"), (0.0, "scratch"),
    (0.05, "scratch"), (0.0501, "win"), (2.0, "win"),
])
def test_day_kind_scratch_band_is_inclusive(r, kind):
    assert vb.day_kind(r) == kind


def test_five_losses_on_one_date_are_one_loss_day():
    trades = [_trade(-1.0, f"2026-03-10T1{i}:00:00+00:00") for i in range(5)]
    assert vb.close_days(trades) == [CloseDay(date(2026, 3, 10), -5.0, "loss")]


def test_mixed_r_on_one_date_nets_out():
    trades = [_trade(-1.0, "2026-03-10T15:00:00+00:00"),
              _trade(1.03, "2026-03-10T18:00:00+00:00"),     # net +0.03: scratch
              _trade(-1.0, "2026-03-12T15:00:00+00:00"),
              _trade(0.5, "2026-03-12T18:00:00+00:00")]      # net -0.5: loss
    assert vb.close_days(trades) == [
        CloseDay(date(2026, 3, 10), 0.03, "scratch"),
        CloseDay(date(2026, 3, 12), -0.5, "loss"),
    ]


def test_close_days_are_in_date_order_and_after_hours_joins_its_session():
    trades = [_trade(2.0, "2026-03-12T15:00:00+00:00"),
              _trade(-1.0, "2026-03-11T01:30:00+00:00"),     # 2026-03-10 ET
              _trade(-1.0, "2026-03-10T15:00:00+00:00")]
    assert vb.close_days(trades) == [
        CloseDay(date(2026, 3, 10), -2.0, "loss"),
        CloseDay(date(2026, 3, 12), 2.0, "win"),
    ]


def test_trade_without_r_or_close_is_skipped():
    no_exit = {**_trade(-1.0, "2026-03-10T15:00:00+00:00"), "exit_price": None}
    no_close = _trade(-1.0, None)
    bad_direction = {**_trade(-1.0, "2026-03-10T15:00:00+00:00"), "direction": "flat"}
    kept = _trade(2.0, "2026-03-11T15:00:00+00:00")
    assert vb.close_days([no_exit, no_close, bad_direction, kept]) == [
        CloseDay(date(2026, 3, 11), 2.0, "win")]


def test_close_days_of_an_empty_book():
    assert vb.close_days([]) == []


def test_current_run_counts_loss_days_and_scratch_neither_breaks_nor_extends():
    days = _days(2.0, -1.0, -1.0, 0.0, -1.0, 0.01)
    assert vb.current_run(days) == (3, days[1].day)


def test_a_win_day_ends_the_run():
    days = _days(-1.0, -1.0, 2.0, -1.0, -1.0)
    assert vb.current_run(days) == (2, days[3].day)


@pytest.mark.parametrize("rs", [(), (2.0,), (-1.0, 2.0), (0.0, 0.01)])
def test_no_run_in_progress(rs):
    assert vb.current_run(_days(*rs)) == (0, None)


def test_window_drawdown_is_peak_to_now_inside_the_window():
    # 10 losing days (an all-time drawdown of 10R), then 40 wins, then 10 x -0.5:
    # the last 50 days climb to +40R and give back 5R.
    days = _days(*([-1.0] * 10 + [1.0] * 40 + [-0.5] * 10))
    assert vb.window_drawdown(days) == (5.0, days[49].day)


def test_older_deeper_drawdown_outside_the_window_does_not_count():
    days = _days(*([-1.0] * 30 + [1.0] * 50))
    assert vb.window_drawdown(days) == (0.0, None)


def test_window_drawdown_from_the_zero_baseline_peaks_on_the_first_window_day():
    days = _days(*([2.0] * 60 + [-1.0] * 3))
    assert vb.window_drawdown(days, window=3) == (3.0, days[60].day)


def test_window_drawdown_takes_the_latest_equal_peak():
    days = _days(1.0, -1.0, 1.0, -0.5)
    assert vb.window_drawdown(days) == (0.5, days[2].day)


def test_window_drawdown_of_no_days():
    assert vb.window_drawdown([]) == (0.0, None)


@pytest.mark.parametrize("value, p80, p95, zone", [
    (3, 4, 6, "normal"), (4, 4, 6, "normal"), (5, 4, 6, "rough"),
    (6, 4, 6, "rough"), (7, 4, 6, "outside"),
    (4, 4, 4, "normal"), (5, 4, 4, "outside"),           # tie: rough is empty
    (2.5, 2.5, 4.1, "normal"), (4.1, 2.5, 4.1, "rough"), (4.11, 2.5, 4.1, "outside"),
])
def test_zone_boundaries_exactly_at_p80_and_p95(value, p80, p95, zone):
    assert vb.zone_of(value, p80, p95) == zone


@pytest.mark.parametrize("a, b, worse", [
    ("normal", "normal", "normal"), ("normal", "rough", "rough"),
    ("outside", "rough", "outside"), ("rough", "normal", "rough"),
])
def test_worse_zone_follows_zones_order(a, b, worse):
    assert vb.worse_zone(a, b) == worse
```

Two expectations worth reading twice. In `test_window_drawdown_from_the_zero_baseline_peaks_on_the_first_window_day` the last three days are all losses, so the window's 0 baseline is its peak, and the peak is dated to the window's first day (`days[60]`); the +120R before the window is ignored. In `test_window_drawdown_takes_the_latest_equal_peak` cumulative R is 1, 0, 1, 0.5: the two peaks of 1 tie and the later one (`days[2]`) dates the drawdown.

- [ ] **Step 4: Run the tests to verify they fail**

```bash
python $WT/scripts/dev/testrun.py file tests/analytics/test_variance_band_days.py
```

Expected: collection error, `ModuleNotFoundError: No module named 'swingbot.core.analytics.variance_band'`.

- [ ] **Step 5: Write the module**

Create `$WT/swingbot/core/analytics/variance_band.py`:

```python
"""v175 Normal bad luck: the range of losing runs this book's past produces.

Pure functions, no I/O: no store, no TradeLog, no config, no network. The
input is the closed book as trade dicts (``status`` in win/loss/closed,
every ledger, ``scope.select`` never applied: the band is whole-book).

The unit is the **close day**: every trade's R (``metrics.r_multiple``) is
summed per America/New_York close date, so five stop-outs on one gap day
are one loss day. A day is a loss below ``-SCRATCH_R``, a win above
``+SCRATCH_R``, a scratch otherwise. A losing run counts consecutive loss
days; a scratch day neither extends nor breaks it; a win day ends it. The
same rule is used for the bootstrap paths and for the current state.

The close date is the UTC ``closed_at`` converted to ET, deliberately
unlike ``pnl_calendar.day_of``'s UTC slice: an after-hours close belongs
to its NYSE session.

Spec: docs/superpowers/specs/2026-10-18-v175-normal-bad-luck-variance-band-design.md
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass

from swingbot.core.analytics import metrics
from swingbot.core.backtesting.instrument import stats
from swingbot.core.market.session import US_MARKET_TZ

# Frozen constants (v175 Global Constraints): changing one is a new spec.
MIN_DAYS = 100
MIN_WEEKS = 20
HORIZONS = (20, 50)
WINDOW = 50                       # current-drawdown window, == HORIZONS[-1]
PATHS = 10_000
SEED = stats.WEEK_BOOTSTRAP_SEED
SCRATCH_R = 0.05
ROUGH_PCT = 80
OUTSIDE_PCT = 95
OUTER_RESAMPLES = 200
OUTER_PATHS = 1_000               # inner paths per outer resample (plan choice)
CI_PCT = (10, 90)
EXPR_RESAMPLES = 10_000
EXPR_CI_PCT = (2.5, 97.5)
ZONES = ("normal", "rough", "outside")
CAVEAT = ("This book's past results are not positive. "
          "A run within their range is still a losing run.")


@dataclass(frozen=True)
class CloseDay:
    """One NYSE close date: the net R of every trade closed on it."""

    day: dt.date
    r: float
    kind: str


def et_close_date(closed_at: str) -> dt.date:
    """The America/New_York date of a ``closed_at`` stamp (naive = UTC)."""
    stamp = dt.datetime.fromisoformat(closed_at)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=dt.timezone.utc)
    return stamp.astimezone(US_MARKET_TZ).date()


def day_kind(r: float) -> str:
    """``loss`` below -SCRATCH_R, ``win`` above +SCRATCH_R, else ``scratch``."""
    if r < -SCRATCH_R:
        return "loss"
    if r > SCRATCH_R:
        return "win"
    return "scratch"


def _dated_r(trades: list[dict]):
    """(ET close date, R) for every trade with a computable R and a close."""
    for trade in trades:
        closed_at = trade.get("closed_at")
        r = metrics.r_multiple(trade)
        if r is None or not closed_at:
            continue
        yield et_close_date(closed_at), r


def close_days(trades: list[dict]) -> list[CloseDay]:
    """Net R per ET close date, in date order (R rounded to 4 dp)."""
    sums: dict[dt.date, float] = defaultdict(float)
    for day, r in _dated_r(trades):
        sums[day] += r
    out = []
    for day in sorted(sums):
        net = round(sums[day], 4)
        out.append(CloseDay(day, net, day_kind(net)))
    return out


def current_run(days: list[CloseDay]) -> tuple[int, dt.date | None]:
    """Loss days in the run in progress at the last close day, and its first day.

    Walks back from the latest day: a loss day counts, a scratch day is
    passed over, a win day ends the walk. ``(0, None)`` when no run is on."""
    length, first = 0, None
    for close_day in reversed(days):
        if close_day.kind == "win":
            break
        if close_day.kind == "loss":
            length, first = length + 1, close_day.day
    return length, first


def window_drawdown(days: list[CloseDay],
                    window: int = WINDOW) -> tuple[float, dt.date | None]:
    """Peak-to-now drawdown in R inside the last ``window`` close days.

    Cumulative R starts from a 0 baseline at the window's start; the peak is
    the latest highest point (the baseline counts, and is dated to the
    window's first day). Returns ``(drawdown rounded to 2 dp, peak day)``,
    ``(0.0, None)`` when the book is at its window peak."""
    tail = days[-window:]
    if not tail:
        return 0.0, None
    cum, peak, peak_day = 0.0, 0.0, tail[0].day
    for close_day in tail:
        cum += close_day.r
        if cum >= peak:
            peak, peak_day = cum, close_day.day
    drawdown = round(peak - cum, 2)
    if drawdown <= 0:
        return 0.0, None
    return drawdown, peak_day


def zone_of(value: float, p80: float, p95: float) -> str:
    """``normal`` at or below p80, ``rough`` up to p95, ``outside`` beyond.

    With ``p80 == p95`` the rough zone is empty."""
    if value <= p80:
        return "normal"
    if value <= p95:
        return "rough"
    return "outside"


def worse_zone(a: str, b: str) -> str:
    """The later of two zones in ``ZONES`` order."""
    return max(a, b, key=ZONES.index)
```

- [ ] **Step 6: Run the tests to verify they pass**

```bash
python $WT/scripts/dev/testrun.py file tests/analytics/test_variance_band_days.py
```

Expected: all pass, `0 failed`.

- [ ] **Step 7: Complexity**

```bash
python -m radon cc -s -n C $WT/swingbot/core/analytics/variance_band.py
```

Expected: no output (every function below rank C).

- [ ] **Step 8: Commit**

```bash
git -C $WT add swingbot/core/analytics/variance_band.py tests/analytics/test_variance_band_days.py
git -C $WT commit -m "feat(analytics): v175 close-day series, current run and window drawdown"
git -C $R status --short
```

Expected: one commit on the branch; `$R`'s status shows only what it showed before the task.

### Task V175-2: Week-block path sampler and per-horizon band

**Model:** sonnet — vectorised numpy bootstrap in one module, method fixed by the spec

**Files:**
- Modify: `swingbot/core/analytics/variance_band.py` (created by V175-1)
- Test: `tests/analytics/test_variance_band_paths.py` (suite `edge-analytics`)

**Interfaces:**
- Consumes (V175-1): `CloseDay`, `SCRATCH_R`, `PATHS`, `OUTER_RESAMPLES`, `OUTER_PATHS`, `SEED`, `ROUGH_PCT`, `OUTSIDE_PCT`, `CI_PCT`. Existing: `stats.iso_week_key(entry_date) -> str` (`swingbot/core/backtesting/instrument/stats.py:28`).
- Produces (ledger contract, consumed by V175-3 and V175-4):
  - `week_blocks(days: list[CloseDay]) -> list[np.ndarray]` — day R per ISO week of the close date, weeks and days in date order
  - `sample_paths(blocks: list[np.ndarray], h: int, n_paths: int, rng: np.random.Generator) -> np.ndarray` — shape `(n_paths, h)`
  - `path_longest_runs(paths: np.ndarray) -> np.ndarray` — int per path
  - `path_max_drawdowns(paths: np.ndarray) -> np.ndarray` — float per path
  - `horizon_band(blocks: list[np.ndarray], h: int, *, paths: int = PATHS, outer: int = OUTER_RESAMPLES, outer_paths: int = OUTER_PATHS, seed: int = SEED) -> dict` — `{"horizon": h, "run": {"p80": int, "p95": int, "p95_lo": int, "p95_hi": int}, "drawdown": {"p80": float, "p95": float, "p95_lo": float, "p95_hi": float}}` (the `horizons[]` entry of the `Band` without `weeks_span`, which V175-3 adds)

**Design notes (read before coding):**
- A path is whole ISO weeks, drawn with replacement, concatenated until it holds `h` close days; the last week is truncated. Same-week losses stay together (the repo's week-cluster convention).
- Drawing `h` weeks per path (enough even for one-day weeks) makes the 200 outer resamples about 5x slower than needed; measured while writing this plan, that version took 20–36 s per band. `sample_paths` draws `ceil(1.5 * h / mean week length) + 2` weeks per path and appends another batch of that width, for every path, while any path is still short of `h`. The draw stays deterministic for a seed. With it, the 200 outer resamples of one horizon took about 1 s on the dev machine.
- The run statistic walks the `h` columns once with vector state (`h <= 50` numpy steps), with the same loss/scratch/win rule as `current_run`. The drawdown statistic is the running peak of cumulative R with a 0 baseline, minus cumulative R, maximised over the path.
- One `rng = np.random.default_rng(seed)` per `horizon_band` call: the main `paths` draw first, then `outer` resamples. Each resamples the week set with replacement (`len(blocks)` picks), then draws `outer_paths` inner paths and keeps their p95 run and p95 drawdown. `p95_lo`/`p95_hi` are the `CI_PCT` percentiles of those outer p95s.
- Quantiles: runs use `np.percentile(..., method="higher")` cast to `int`; drawdowns use the default linear method rounded to 2 dp. `outer` must be at least 1.

- [ ] **Step 1: Confirm the V175-1 symbols**

```bash
git -C $WT grep -n "^class CloseDay\|^def current_run\|^OUTER_PATHS\|^CI_PCT\|^SCRATCH_R" -- swingbot/core/analytics/variance_band.py
```

Expected: all five lines are found. If any is missing, V175-1 is not done; stop.

- [ ] **Step 2: Write the failing tests**

Create `$WT/tests/analytics/test_variance_band_paths.py`:

```python
"""v175 § 1: the week-block path sampler and the per-horizon band.

Blocks in the intactness tests carry tagged values: block ``b`` holds
``10*b + 1, 10*b + 2, ...``, so any value says which block it came from and
where it sat inside that block.
"""
from datetime import date, timedelta

import numpy as np
import pytest

from swingbot.core.analytics import variance_band as vb
from swingbot.core.analytics.variance_band import CloseDay

TAGGED = [np.array([1.0, 2.0, 3.0]), np.array([11.0, 12.0]),
          np.array([21.0, 22.0, 23.0, 24.0, 25.0]), np.array([31.0])]
FAST = {"paths": 2_000, "outer": 20, "outer_paths": 200}


def _day(d, r):
    return CloseDay(d, r, vb.day_kind(r))


def _assert_whole_weeks(path):
    """The path is whole TAGGED blocks in a row, only the last one cut short."""
    i, h = 0, len(path)
    while i < h:
        start = path[i]
        assert start % 10 == 1, f"position {i} is not a week start: {path}"
        block = TAGGED[int(start) // 10]
        take = min(len(block), h - i)
        assert list(path[i:i + take]) == list(block[:take]), path
        i += take


def test_week_blocks_group_by_iso_week_of_the_close_date_in_order():
    monday = date(2026, 1, 5)
    days = [_day(monday, -1.0), _day(monday + timedelta(days=2), 2.0),
            _day(monday + timedelta(days=6), 0.0),          # Sunday, same ISO week
            _day(monday + timedelta(days=7), -0.5),         # next Monday
            _day(monday + timedelta(days=21), 1.0)]         # two weeks later
    blocks = vb.week_blocks(days)
    assert [b.tolist() for b in blocks] == [[-1.0, 2.0, 0.0], [-0.5], [1.0]]
    assert all(b.dtype == float for b in blocks)


def test_week_blocks_of_no_days():
    assert vb.week_blocks([]) == []


@pytest.mark.parametrize("h", [1, 4, 7, 20, 50])
def test_paths_hold_h_days_of_whole_weeks_with_the_last_truncated(h):
    paths = vb.sample_paths(TAGGED, h, 500, np.random.default_rng(1))
    assert paths.shape == (500, h)
    for path in paths:
        _assert_whole_weeks(path)


def test_every_week_is_drawn():
    paths = vb.sample_paths(TAGGED, 10, 500, np.random.default_rng(2))
    assert {int(v) // 10 for v in paths[:, 0]} == {0, 1, 2, 3}


def test_one_day_weeks_still_fill_the_path():
    blocks = [np.array([-1.0]), np.array([2.0])]
    paths = vb.sample_paths(blocks, 50, 300, np.random.default_rng(3))
    assert paths.shape == (300, 50)
    assert set(np.unique(paths)) <= {-1.0, 2.0}


def test_a_seed_reproduces_the_paths():
    a = vb.sample_paths(TAGGED, 20, 200, np.random.default_rng(42))
    b = vb.sample_paths(TAGGED, 20, 200, np.random.default_rng(42))
    c = vb.sample_paths(TAGGED, 20, 200, np.random.default_rng(43))
    assert np.array_equal(a, b)
    assert not np.array_equal(a, c)


def test_longest_run_uses_the_close_day_rule():
    paths = np.array([
        [-1.0, -1.0, 0.0, -1.0, 1.0, -1.0],    # L L S L | W L: scratch passed over -> 3
        [1.0, 1.0, 1.0, 1.0, 1.0, 1.0],        # no loss day -> 0
        [-1.0, 0.05, -0.06, 0.06, -1.0, -1.0],  # L S L | W L L -> 2
        [-0.05, -0.05, -0.05, -0.05, -0.05, -0.05],  # all scratch -> 0
    ])
    assert vb.path_longest_runs(paths).tolist() == [3, 0, 2, 0]


def test_max_drawdown_from_the_running_peak_with_a_zero_baseline():
    paths = np.array([
        [1.0, -1.0, -1.0, 2.0, -3.0],          # cum 1 0 -1 1 -2, peak 1 -> 3
        [-1.0, -1.0, 0.0, 0.0, 0.0],           # never above 0: from the baseline -> 2
        [1.0, 1.0, 1.0, 1.0, 1.0],             # -> 0
    ])
    assert vb.path_max_drawdowns(paths).tolist() == pytest.approx([3.0, 2.0, 0.0])


def test_horizon_band_shape_and_types():
    blocks = [np.array([-1.0, 2.0, -1.0, 0.0, -1.0]), np.array([1.5, -1.0]),
              np.array([-1.0, -1.0, -1.0]), np.array([2.0, 2.0, -1.0, 1.0])]
    band = vb.horizon_band(blocks, 20, **FAST)
    assert set(band) == {"horizon", "run", "drawdown"}
    assert band["horizon"] == 20
    for key in ("run", "drawdown"):
        assert set(band[key]) == {"p80", "p95", "p95_lo", "p95_hi"}
        q = band[key]
        assert q["p80"] <= q["p95"]
        assert q["p95_lo"] <= q["p95_hi"]
    assert all(type(v) is int for v in band["run"].values())
    assert all(type(v) is float for v in band["drawdown"].values())
    assert all(round(v, 2) == v for v in band["drawdown"].values())


def test_horizon_band_is_reproducible_from_its_seed():
    blocks = [np.array([-1.0, 2.0, -1.0]), np.array([1.5, -1.0, -1.0, -1.0])]
    assert vb.horizon_band(blocks, 50, **FAST) == vb.horizon_band(blocks, 50, **FAST)


def test_an_all_win_book_gives_a_zero_band():
    blocks = [np.array([1.0, 2.0, 1.0]), np.array([0.5, 0.5])]
    band = vb.horizon_band(blocks, 20, **FAST)
    assert band["run"] == {"p80": 0, "p95": 0, "p95_lo": 0, "p95_hi": 0}
    assert band["drawdown"] == {"p80": 0.0, "p95": 0.0, "p95_lo": 0.0, "p95_hi": 0.0}


def test_an_all_loss_book_runs_the_whole_horizon():
    blocks = [np.array([-1.0] * 5), np.array([-1.0] * 3)]
    band = vb.horizon_band(blocks, 20, **FAST)
    assert band["run"] == {"p80": 20, "p95": 20, "p95_lo": 20, "p95_hi": 20}
    assert band["drawdown"] == {"p80": 20.0, "p95": 20.0, "p95_lo": 20.0, "p95_hi": 20.0}


def test_correlated_weeks_widen_the_run_band():
    # Same day mix (half losses): kept in all-loss weeks versus spread
    # across alternating weeks. Week blocks keep the clusters, so the
    # clustered book's p95 run is longer.
    clustered = [np.array([-1.0] * 5), np.array([1.0] * 5)] * 10
    spread = [np.array([-1.0, 1.0, -1.0, 1.0, -1.0]),
              np.array([1.0, -1.0, 1.0, -1.0, 1.0])] * 10
    wide = vb.horizon_band(clustered, 50, **FAST)["run"]["p95"]
    narrow = vb.horizon_band(spread, 50, **FAST)["run"]["p95"]
    assert wide > narrow
```

- [ ] **Step 3: Run the tests to verify they fail**

```bash
python $WT/scripts/dev/testrun.py file tests/analytics/test_variance_band_paths.py
```

Expected: FAIL, `AttributeError: module 'swingbot.core.analytics.variance_band' has no attribute 'week_blocks'` (and the same for the other new names).

- [ ] **Step 4: Add the sampler to the module**

In `$WT/swingbot/core/analytics/variance_band.py`, add `import numpy as np` to the imports, between `from dataclasses import dataclass` and the `swingbot` imports, with a blank line on each side (stdlib, third-party, first-party):

```python
import datetime as dt
from collections import defaultdict
from dataclasses import dataclass

import numpy as np

from swingbot.core.analytics import metrics
```

Then append at the end of the module:

```python
# --- Week-block path bootstrap -------------------------------------------


def week_blocks(days: list[CloseDay]) -> list[np.ndarray]:
    """Close-day R grouped by the ISO week of the close date.

    ``days`` is in date order (``close_days`` returns it so), so the weeks
    come out in date order and each week's days stay in date order."""
    weeks: dict[str, list[float]] = {}
    for close_day in days:
        key = stats.iso_week_key(close_day.day.isoformat())
        weeks.setdefault(key, []).append(close_day.r)
    return [np.asarray(rs, dtype=float) for rs in weeks.values()]


def _week_picks(lengths: np.ndarray, h: int, n_paths: int,
                rng: np.random.Generator) -> np.ndarray:
    """Week indices per path, wide enough that every path holds ``h`` days.

    A batch of ``ceil(1.5 * h / mean week length) + 2`` picks per path
    covers ``h`` almost always; another batch of the same width is appended
    to every path while any path is still short (deterministic per seed)."""
    width = int(np.ceil(1.5 * h / lengths.mean())) + 2
    picks = rng.integers(0, len(lengths), size=(n_paths, width))
    while (lengths[picks].sum(axis=1) < h).any():
        more = rng.integers(0, len(lengths), size=(n_paths, width))
        picks = np.hstack([picks, more])
    return picks


def sample_paths(blocks: list[np.ndarray], h: int, n_paths: int,
                 rng: np.random.Generator) -> np.ndarray:
    """``n_paths`` paths of ``h`` close days, each whole weeks drawn with
    replacement and concatenated; the last week is truncated.

    Vectorised: every picked week is laid out end to end in one flat index
    array, then each path keeps its first ``h`` entries."""
    lengths = np.array([len(block) for block in blocks])
    starts = np.cumsum(lengths) - lengths
    flat = np.concatenate(blocks)
    picks = _week_picks(lengths, h, n_paths, rng)
    pick_lens = lengths[picks]
    seg_lens = pick_lens.ravel()
    seg_offsets = np.cumsum(seg_lens) - seg_lens
    day_index = (np.repeat(starts[picks].ravel() - seg_offsets, seg_lens)
                 + np.arange(int(seg_lens.sum())))
    row_lens = pick_lens.sum(axis=1)
    row_starts = np.cumsum(row_lens) - row_lens
    take = row_starts[:, None] + np.arange(h)[None, :]
    return flat[day_index[take]]


def path_longest_runs(paths: np.ndarray) -> np.ndarray:
    """Longest losing run per path: a loss day extends it, a scratch day
    neither extends nor breaks it, a win day ends it (``current_run``'s rule)."""
    current = np.zeros(len(paths), dtype=int)
    best = current.copy()
    for column in paths.T:
        current = np.where(column < -SCRATCH_R, current + 1,
                           np.where(column > SCRATCH_R, 0, current))
        best = np.maximum(best, current)
    return best


def path_max_drawdowns(paths: np.ndarray) -> np.ndarray:
    """Maximum drawdown per path in R: running peak of cumulative R (0
    baseline) minus cumulative R."""
    cum = np.cumsum(paths, axis=1)
    peak = np.maximum.accumulate(np.maximum(cum, 0.0), axis=1)
    return (peak - cum).max(axis=1)


def _run_q(values, pct: float) -> int:
    return int(np.percentile(values, pct, method="higher"))


def _dd_q(values, pct: float) -> float:
    return round(float(np.percentile(values, pct)), 2)


def _quantiles(values, outer_p95s, q) -> dict:
    """p80/p95 of the main draw and the CI_PCT range of the outer p95s."""
    return {"p80": q(values, ROUGH_PCT), "p95": q(values, OUTSIDE_PCT),
            "p95_lo": q(outer_p95s, CI_PCT[0]), "p95_hi": q(outer_p95s, CI_PCT[1])}


def _outer_p95s(blocks: list[np.ndarray], h: int, outer: int, outer_paths: int,
                rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """p95 run and p95 drawdown of ``outer`` resampled week sets."""
    runs, drawdowns = [], []
    for _ in range(outer):
        picks = rng.integers(0, len(blocks), size=len(blocks))
        inner = sample_paths([blocks[i] for i in picks], h, outer_paths, rng)
        runs.append(np.percentile(path_longest_runs(inner), OUTSIDE_PCT,
                                  method="higher"))
        drawdowns.append(np.percentile(path_max_drawdowns(inner), OUTSIDE_PCT))
    return np.asarray(runs), np.asarray(drawdowns)


def horizon_band(blocks: list[np.ndarray], h: int, *, paths: int = PATHS,
                 outer: int = OUTER_RESAMPLES, outer_paths: int = OUTER_PATHS,
                 seed: int = SEED) -> dict:
    """The band for one horizon: p80/p95 of the longest losing run and of the
    maximum drawdown over ``h`` close days, with p95's own uncertainty.

    One generator per call: the main draw first, then the outer resamples,
    so a seed reproduces the whole band. ``outer`` must be at least 1."""
    rng = np.random.default_rng(seed)
    main = sample_paths(blocks, h, paths, rng)
    outer_runs, outer_dds = _outer_p95s(blocks, h, outer, outer_paths, rng)
    return {
        "horizon": h,
        "run": _quantiles(path_longest_runs(main), outer_runs, _run_q),
        "drawdown": _quantiles(path_max_drawdowns(main), outer_dds, _dd_q),
    }
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
python $WT/scripts/dev/testrun.py file tests/analytics/test_variance_band_paths.py
python $WT/scripts/dev/testrun.py file tests/analytics/test_variance_band_days.py
```

Expected: both files pass, `0 failed`. If `test_correlated_weeks_widen_the_run_band` fails, the sampler is breaking weeks apart; fix the sampler, never the test.

- [ ] **Step 6: Complexity**

```bash
python -m radon cc -s -n C $WT/swingbot/core/analytics/variance_band.py
```

Expected: no output.

- [ ] **Step 7: Commit**

```bash
git -C $WT add swingbot/core/analytics/variance_band.py tests/analytics/test_variance_band_paths.py
git -C $WT commit -m "feat(analytics): v175 week-block path sampler and per-horizon band"
git -C $R status --short
```

Expected: one commit on the branch; `$R` unchanged.

### Task V175-3: `variance_band(closed)`: era pool, composition, zones, ExpR and caveat, dollars

**Model:** sonnet — assembly over finished helpers plus a reused bootstrap

**Files:**
- Modify: `swingbot/core/analytics/variance_band.py` (created by V175-1, extended by V175-2)
- Test: `tests/analytics/test_variance_band_assembly.py` (suite `edge-analytics`)

**Interfaces:**
- Consumes (V175-1, V175-2): `CloseDay`, `close_days`, `et_close_date`, `current_run`, `window_drawdown`, `zone_of`, `worse_zone`, `week_blocks`, `horizon_band`, and the constants. Existing: `metrics.r_multiple`, `metrics.r_multiples(closed) -> list[float]` (`metrics.py:353`), `metrics.expectancy_r(closed) -> float | None` (`metrics.py:235`), `stats.week_cluster_bootstrap(baseline, component, statistic, *, n_resamples, seed) -> np.ndarray` (`stats.py:57`), `stats.iso_week_key` (`stats.py:28`).
- Produces (ledger contract; `variance_band` and `Band` are consumed by V175-4, V175-5 and V175-7):
  - `Band = dict[str, Any]`
  - `variance_band(closed: list[dict], *, paths: int = PATHS, outer: int = OUTER_RESAMPLES, outer_paths: int = OUTER_PATHS) -> Band` — the shape in Global Constraints, exactly
  - `era_of(trade: dict) -> str` — `"v2"` when `plan_id` is truthy, else `"legacy"`
  - `pool_trades(closed: list[dict]) -> tuple[list[dict], str]` — `(v2 trades, "v2")` once they alone reach `MIN_DAYS` close days and `MIN_WEEKS` weeks, else `(closed, "all")`
  - `composition(closed: list[dict]) -> dict` — `{"days_by_era": {"v2": int, "legacy": int}, "trades_by_horizon": {str: int}}`
  - `expr_block(pool: list[dict], days: list[CloseDay]) -> dict` — `{"value", "n", "start", "end", "ci", "not_positive"}`; `ci` is `[lo, hi]` or `None`
  - `dollars_block(pool: list[dict], drawdown: float) -> dict | None` — `{"median_risk", "drawdown_usd"}` or `None`
  - `current_state(days: list[CloseDay], band50: dict) -> dict` — the `current` block (module-internal use; tested directly for the zone boundaries)

**Design notes:**
- "Skipped everywhere": `variance_band` first keeps only trades with a `closed_at` and a computable R (`_usable`). The insufficient check, the pool, the composition, the ExpR and the dollars all work on that list, so `expr.n` equals the number of trades behind the close days.
- `insufficient` is decided on the whole usable book: fewer than `MIN_DAYS` close days or fewer than `MIN_WEEKS` distinct ISO weeks.
- `weeks` in the full band is `len(week_blocks(pool days))`; `weeks_span = round(h * weeks / days, 1)`.
- ExpR interval: items `_RItem(entry_date=<ET close date ISO>, r=<R>)`, sorted (input order never changes the draw), statistic = mean R, `n_resamples=EXPR_RESAMPLES`, `seed=stats.WEEK_BOOTSTRAP_SEED`, the same pattern as `calibration.live_expr_bound` (`swingbot/core/analytics/calibration.py:294-320`) but two-sided at `EXPR_CI_PCT`. `stats.group_by_week` reads `.entry_date`, which is why the items are objects, not dicts.
- `current_state` takes the 50-day horizon entry (`horizons[-1]`); ages are inclusive calendar days to `asof`.
- `dollars` is added to the band only when `dollars_block` returns a dict: the key is absent, never `null`.

- [ ] **Step 1: Confirm the symbols**

```bash
git -C $WT grep -n "^def horizon_band\|^def week_blocks\|^def window_drawdown\|^def zone_of\|^def worse_zone" -- swingbot/core/analytics/variance_band.py
git -C $WT grep -n "^def expectancy_r\|^def r_multiples\|^def week_cluster_bootstrap\|^def live_expr_bound" -- swingbot/core
```

Expected: the five V175-1/V175-2 functions; `metrics.py:235`, `metrics.py:353`, `stats.py:57`, `calibration.py:307`.

- [ ] **Step 2: Write the failing tests**

Create `$WT/tests/analytics/test_variance_band_assembly.py`:

```python
"""v175 § 1: ``variance_band(closed)``, the whole band.

Books are built on dated weeks starting Monday 2025-01-06; every trade
closes at 20:00 UTC (15:00 or 16:00 in New York, the same date). Entry 100,
stop 99, bullish: a trade's R is ``exit_price - 100`` and its dollar risk
is ``shares * 1``. ``FAST`` shrinks the bootstrap so the file stays quick;
the timing test runs the real sizes.
"""
import time
from datetime import date, timedelta

import numpy as np
import pytest

from swingbot.core.analytics import variance_band as vb
from swingbot.core.analytics.variance_band import CloseDay

MONDAY = date(2025, 1, 6)
FAST = {"paths": 2_000, "outer": 20, "outer_paths": 200}
POSITIVE = (2.0, -1.0, -1.0, 2.0, -1.0)            # +1R every 5-day week
NEGATIVE = (-1.0, -1.0, 2.0, -1.0, -1.0)           # -2R every 5-day week
NOISY = (2.0, -1.0, -1.0, -1.0, 2.0, -1.0, 2.0, -1.0, -1.0, 0.5)   # mean +0.05R
FULL_KEYS = {"status", "scope", "asof", "days", "weeks", "pool", "composition",
             "horizons", "current", "expr", "dollars"}


def _dates(per_week, start_week=0):
    """Dates: ``per_week[i]`` consecutive days from the Monday of week i."""
    out = []
    for w, k in enumerate(per_week, start=start_week):
        out += [MONDAY + timedelta(days=7 * w + i) for i in range(k)]
    return out


def _trade(r, d, *, plan_id="plan-1", shares=10.0, horizon="swing"):
    return {"entry": 100.0, "stop_loss": 99.0, "direction": "bullish",
            "exit_price": 100.0 + r, "closed_at": f"{d.isoformat()}T20:00:00+00:00",
            "status": "loss" if r < 0 else "win", "plan_id": plan_id,
            "shares": shares, "horizon_key": horizon}


def _book(dates, pattern=POSITIVE, **kw):
    return [_trade(pattern[i % len(pattern)], d, **kw) for i, d in enumerate(dates)]


def _band(closed):
    return vb.variance_band(closed, **FAST)


def test_99_close_days_are_insufficient():
    book = _book(_dates([5] * 19 + [4]))                 # 99 days over 20 weeks
    assert _band(book) == {"status": "insufficient", "scope": "whole_book",
                           "days": 99, "weeks": 20}


def test_19_weeks_are_insufficient():
    book = _book(_dates([7] * 6 + [5] * 13))             # 107 days over 19 weeks
    assert _band(book) == {"status": "insufficient", "scope": "whole_book",
                           "days": 107, "weeks": 19}


def test_an_empty_book_is_insufficient():
    assert _band([]) == {"status": "insufficient", "scope": "whole_book",
                         "days": 0, "weeks": 0}


def test_trades_without_r_do_not_count_toward_the_floor():
    book = _book(_dates([5] * 20))
    book[0] = {**book[0], "exit_price": None}
    assert _band(book)["status"] == "insufficient"


def test_full_band_shape_at_100_days_over_20_weeks():
    dates = _dates([5] * 20)
    band = _band(_book(dates))
    assert set(band) == FULL_KEYS
    assert (band["status"], band["scope"], band["pool"]) == ("ok", "whole_book", "v2")
    assert (band["days"], band["weeks"]) == (100, 20)
    assert band["asof"] == dates[-1].isoformat()
    assert [h["horizon"] for h in band["horizons"]] == [20, 50]
    assert [h["weeks_span"] for h in band["horizons"]] == [4.0, 10.0]
    for entry in band["horizons"]:
        assert set(entry) == {"horizon", "weeks_span", "run", "drawdown"}
        assert set(entry["run"]) == set(entry["drawdown"]) == {"p80", "p95", "p95_lo", "p95_hi"}
    assert set(band["current"]) == {"run", "run_age_days", "drawdown", "drawdown_age_days",
                                    "run_zone", "drawdown_zone", "zone"}
    assert set(band["expr"]) == {"value", "n", "start", "end", "ci", "not_positive"}


def test_band_is_reproducible():
    book = _book(_dates([5] * 22), pattern=NOISY)
    assert _band(book) == _band(book)


def test_pool_is_v2_once_v2_alone_reaches_the_floor():
    legacy = _book(_dates([5] * 6), plan_id=None)                   # 30 days, weeks 0-5
    v2 = _book(_dates([5] * 20, start_week=6))                      # 100 days, weeks 6-25
    band = _band(legacy + v2)
    assert (band["pool"], band["days"], band["weeks"]) == ("v2", 100, 20)
    assert band["composition"]["days_by_era"] == {"v2": 100, "legacy": 30}
    assert band["expr"]["n"] == 100
    assert band["expr"]["start"] == (MONDAY + timedelta(weeks=6)).isoformat()


def test_pool_is_the_whole_book_until_v2_reaches_the_floor():
    legacy = _book(_dates([5] * 12), plan_id=None)                  # 60 days
    v2 = _book(_dates([5] * 10, start_week=12))                     # 50 days
    band = _band(legacy + v2)
    assert (band["pool"], band["days"], band["weeks"]) == ("all", 110, 22)
    assert band["composition"]["days_by_era"] == {"v2": 50, "legacy": 60}
    assert band["expr"]["n"] == 110


def test_pool_trades_and_era_of():
    v2 = _book(_dates([5] * 20))
    legacy = _book(_dates([5] * 2, start_week=30), plan_id=None)
    assert vb.era_of(v2[0]) == "v2"
    assert vb.era_of(legacy[0]) == "legacy"
    assert vb.era_of({**v2[0], "plan_id": ""}) == "legacy"
    assert vb.pool_trades(v2 + legacy) == (v2, "v2")
    assert vb.pool_trades(v2[:-1] + legacy) == (v2[:-1] + legacy, "all")


def test_composition_counts_trades_per_horizon_with_unknown():
    dates = _dates([5] * 20)
    book = _book(dates[:60], horizon="swing") + _book(dates[60:90], horizon="position")
    book += _book(dates[90:], horizon=None)
    book.append(_trade(2.0, dates[0], horizon="swing", plan_id=None))   # same date, legacy
    assert vb.composition(book) == {
        "days_by_era": {"v2": 100, "legacy": 1},
        "trades_by_horizon": {"position": 30, "swing": 61, "unknown": 10},
    }


def test_expr_positive_book_has_no_caveat():
    dates = _dates([5] * 20)
    expr = _band(_book(dates))["expr"]
    assert expr["value"] == pytest.approx(0.2)
    assert expr["n"] == 100
    assert (expr["start"], expr["end"]) == (dates[0].isoformat(), dates[-1].isoformat())
    assert expr["ci"][0] > 0
    assert expr["not_positive"] is False


def test_expr_not_positive_when_negative():
    expr = _band(_book(_dates([5] * 20), pattern=NEGATIVE))["expr"]
    assert expr["value"] == pytest.approx(-0.4)
    assert expr["not_positive"] is True


def test_expr_not_positive_when_the_interval_includes_zero():
    expr = _band(_book(_dates([5] * 20), pattern=NOISY))["expr"]
    assert expr["value"] > 0
    assert expr["ci"][0] <= 0 <= expr["ci"][1]
    assert expr["not_positive"] is True


def test_expr_block_values_are_rounded_and_input_order_free():
    book = _book(_dates([5] * 20), pattern=NOISY)
    days = vb.close_days(book)
    forward = vb.expr_block(book, days)
    backward = vb.expr_block(list(reversed(book)), days)
    assert forward == backward
    assert forward["value"] == round(forward["value"], 3)
    assert all(v == round(v, 3) for v in forward["ci"])


def test_expr_block_of_an_empty_pool():
    assert vb.expr_block([], []) == {"value": None, "n": 0, "start": None, "end": None,
                                     "ci": None, "not_positive": True}


def test_dollars_from_the_median_per_trade_risk():
    dates = _dates([5] * 20)
    book = _book(dates[:50], shares=10.0) + _book(dates[50:], shares=30.0)
    book[0] = {**book[0], "shares": 20.0}        # risks: 49 x 10, 1 x 20, 50 x 30
    band = _band(book)
    assert band["dollars"] == {"median_risk": 25.0,
                               "drawdown_usd": round(band["current"]["drawdown"] * 25.0, 2)}


def test_dollars_omitted_when_no_trade_has_shares():
    band = _band(_book(_dates([5] * 20), shares=None))
    assert band["status"] == "ok"
    assert "dollars" not in band


def test_dollars_block_skips_zero_risk_and_missing_prices():
    trade = _trade(-1.0, MONDAY)
    assert vb.dollars_block([{**trade, "shares": 0}], 2.0) is None
    assert vb.dollars_block([{**trade, "stop_loss": 100.0}], 2.0) is None
    assert vb.dollars_block([{**trade, "entry": None}], 2.0) is None
    assert vb.dollars_block([trade], 2.5) == {"median_risk": 10.0, "drawdown_usd": 25.0}


def _band50(run=(2, 4), drawdown=(3.0, 5.0)):
    return {"horizon": 50, "weeks_span": 10.0,
            "run": {"p80": run[0], "p95": run[1], "p95_lo": run[1], "p95_hi": run[1]},
            "drawdown": {"p80": drawdown[0], "p95": drawdown[1],
                         "p95_lo": drawdown[1], "p95_hi": drawdown[1]}}


def _days(*rs, start=date(2026, 3, 2)):
    return [CloseDay(start + timedelta(days=i), r, vb.day_kind(r)) for i, r in enumerate(rs)]


@pytest.mark.parametrize("losses, run_zone", [(2, "normal"), (3, "rough"), (4, "rough"),
                                              (5, "outside")])
def test_current_run_zone_boundaries(losses, run_zone):
    days = _days(*([10.0] + [-0.2] * losses))       # small losses: drawdown stays normal
    current = vb.current_state(days, _band50())
    assert current["run"] == losses
    assert current["run_zone"] == run_zone
    assert current["drawdown_zone"] == "normal"
    assert current["zone"] == run_zone


@pytest.mark.parametrize("drawdown, dd_zone", [(3.0, "normal"), (3.5, "rough"), (5.0, "rough"),
                                               (5.5, "outside")])
def test_current_drawdown_zone_boundaries(drawdown, dd_zone):
    days = _days(10.0, -drawdown)                   # one loss day: run 1, normal
    current = vb.current_state(days, _band50())
    assert current["drawdown"] == drawdown
    assert current["drawdown_zone"] == dd_zone
    assert current["run_zone"] == "normal"
    assert current["zone"] == dd_zone


def test_current_state_ages_are_inclusive_calendar_days():
    days = _days(2.0, -1.0, 0.0, -1.0)              # 2026-03-02 .. 2026-03-05
    current = vb.current_state(days, _band50())
    assert (current["run"], current["run_age_days"]) == (2, 3)          # 03-03 to 03-05
    assert (current["drawdown"], current["drawdown_age_days"]) == (2.0, 4)  # peak 03-02


def test_current_state_at_a_peak_has_no_ages():
    current = vb.current_state(_days(-1.0, 2.0), _band50())
    assert current == {"run": 0, "run_age_days": None, "drawdown": 0.0,
                       "drawdown_age_days": None, "run_zone": "normal",
                       "drawdown_zone": "normal", "zone": "normal"}


def test_tie_band_skips_rough():
    days = _days(*([10.0] + [-0.2] * 5))
    current = vb.current_state(days, _band50(run=(4, 4)))
    assert current["run_zone"] == "outside"


@pytest.mark.slow
def test_one_full_size_band_on_300_close_days_is_fast():
    rng = np.random.default_rng(7)
    pattern = tuple(rng.choice([-1.0, 1.5, 0.0], size=300, p=[0.5, 0.4, 0.1]))
    book = _book(_dates([5] * 60), pattern=pattern)
    started = time.process_time()
    band = vb.variance_band(book)
    elapsed = time.process_time() - started
    assert band["status"] == "ok"
    assert elapsed < 5.0, f"variance_band took {elapsed:.1f}s of CPU"
```

- [ ] **Step 3: Run the tests to verify they fail**

```bash
python $WT/scripts/dev/testrun.py file tests/analytics/test_variance_band_assembly.py
```

Expected: FAIL, `AttributeError: module 'swingbot.core.analytics.variance_band' has no attribute 'variance_band'` (and the other new names).

- [ ] **Step 4: Add the assembly to the module**

In `$WT/swingbot/core/analytics/variance_band.py` change the imports to:

```python
import datetime as dt
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, NamedTuple

import numpy as np
```

Add, right after the `CAVEAT` constant:

```python

Band = dict[str, Any]
```

Then append at the end of the module:

```python
# --- The band -------------------------------------------------------------


class _RItem(NamedTuple):
    """A trade as ``stats.week_cluster_bootstrap`` sees it: week of the close."""

    entry_date: str
    r: float


def era_of(trade: dict) -> str:
    """``v2`` for a trade linked to a plan, ``legacy`` (v1) otherwise."""
    return "v2" if trade.get("plan_id") else "legacy"


def _week_count(days: list[CloseDay]) -> int:
    return len({stats.iso_week_key(d.day.isoformat()) for d in days})


def _enough(days: list[CloseDay]) -> bool:
    return len(days) >= MIN_DAYS and _week_count(days) >= MIN_WEEKS


def _usable(closed: list[dict]) -> list[dict]:
    """Trades with a close stamp and a computable R; the rest are skipped."""
    return [t for t in closed
            if t.get("closed_at") and metrics.r_multiple(t) is not None]


def pool_trades(closed: list[dict]) -> tuple[list[dict], str]:
    """The v2 trades once they alone reach the floor, else the whole book."""
    v2 = [t for t in closed if era_of(t) == "v2"]
    if _enough(close_days(v2)):
        return v2, "v2"
    return list(closed), "all"


def composition(closed: list[dict]) -> dict:
    """Close days per era and trades per horizon, over the whole book."""
    days_by_era = {era: len(close_days([t for t in closed if era_of(t) == era]))
                   for era in ("v2", "legacy")}
    horizons = Counter(t.get("horizon_key") or "unknown" for t in closed)
    return {"days_by_era": days_by_era, "trades_by_horizon": dict(sorted(horizons.items()))}


def _mean_r(draw: list, _component=()) -> float | None:
    if not draw:
        return None
    return sum(item.r for item in draw) / len(draw)


def _r_items(pool: list[dict]) -> list[_RItem]:
    """Sorted, so the input order never changes the bootstrap draw."""
    items = []
    for trade in pool:
        r = metrics.r_multiple(trade)
        closed_at = trade.get("closed_at")
        if r is not None and closed_at:
            items.append(_RItem(et_close_date(closed_at).isoformat(), r))
    return sorted(items)


def _expr_ci(pool: list[dict]) -> list[float] | None:
    """EXPR_CI_PCT interval of mean R, resampling weeks of the close date."""
    draws = stats.week_cluster_bootstrap(_r_items(pool), (), _mean_r,
                                         n_resamples=EXPR_RESAMPLES,
                                         seed=stats.WEEK_BOOTSTRAP_SEED)
    if draws.size == 0:
        return None
    lo, hi = np.percentile(draws, EXPR_CI_PCT)
    return [round(float(lo), 3), round(float(hi), 3)]


def expr_block(pool: list[dict], days: list[CloseDay]) -> dict:
    """The pool's ExpR with N, window and week-cluster interval, re-derived
    on every call; ``not_positive`` drives the caveat."""
    raw = metrics.expectancy_r(pool)
    value = None if raw is None else round(raw, 3)
    ci = _expr_ci(pool)
    not_positive = (value is None or value <= 0
                    or (ci is not None and ci[0] <= 0 <= ci[1]))
    return {"value": value, "n": len(metrics.r_multiples(pool)),
            "start": days[0].day.isoformat() if days else None,
            "end": days[-1].day.isoformat() if days else None,
            "ci": ci, "not_positive": not_positive}


def _dollar_risk(trade: dict) -> float | None:
    """shares x |entry - stop_loss| (the v170 basis), None when unknown."""
    shares, entry, stop = trade.get("shares"), trade.get("entry"), trade.get("stop_loss")
    if not shares or entry is None or stop is None:
        return None
    risk = float(shares) * abs(entry - stop)
    return risk if risk > 0 else None


def dollars_block(pool: list[dict], drawdown: float) -> dict | None:
    """The drawdown in dollars at the median per-trade risk; None when no
    pool trade has a dollar risk (the band then omits the key)."""
    risks = [risk for trade in pool if (risk := _dollar_risk(trade)) is not None]
    if not risks:
        return None
    median = round(float(np.median(risks)), 2)
    return {"median_risk": median, "drawdown_usd": round(drawdown * median, 2)}


def _age(start: dt.date | None, asof: dt.date) -> int | None:
    return None if start is None else (asof - start).days + 1


def current_state(days: list[CloseDay], band50: dict) -> dict:
    """The run and window drawdown now, each placed against the 50-day band."""
    asof = days[-1].day
    run, run_start = current_run(days)
    drawdown, peak_day = window_drawdown(days)
    run_zone = zone_of(run, band50["run"]["p80"], band50["run"]["p95"])
    drawdown_zone = zone_of(drawdown, band50["drawdown"]["p80"], band50["drawdown"]["p95"])
    return {"run": run, "run_age_days": _age(run_start, asof),
            "drawdown": drawdown, "drawdown_age_days": _age(peak_day, asof),
            "run_zone": run_zone, "drawdown_zone": drawdown_zone,
            "zone": worse_zone(run_zone, drawdown_zone)}


def _horizon_entry(blocks: list[np.ndarray], h: int, n_days: int,
                   sizes: dict) -> dict:
    entry = horizon_band(blocks, h, **sizes)
    return {**entry, "weeks_span": round(h * len(blocks) / n_days, 1)}


def variance_band(closed: list[dict], *, paths: int = PATHS,
                  outer: int = OUTER_RESAMPLES,
                  outer_paths: int = OUTER_PATHS) -> Band:
    """The whole-book band, or ``insufficient`` below the floor.

    ``closed`` is the closed book (every ledger, no scope applied)."""
    usable = _usable(closed)
    book_days = close_days(usable)
    if not _enough(book_days):
        return {"status": "insufficient", "scope": "whole_book",
                "days": len(book_days), "weeks": _week_count(book_days)}
    pool, pool_name = pool_trades(usable)
    days = close_days(pool)
    blocks = week_blocks(days)
    sizes = {"paths": paths, "outer": outer, "outer_paths": outer_paths}
    horizons = [_horizon_entry(blocks, h, len(days), sizes) for h in HORIZONS]
    current = current_state(days, horizons[-1])
    band: Band = {"status": "ok", "scope": "whole_book", "asof": days[-1].day.isoformat(),
                  "days": len(days), "weeks": len(blocks), "pool": pool_name,
                  "composition": composition(usable), "horizons": horizons,
                  "current": current, "expr": expr_block(pool, days)}
    dollars = dollars_block(pool, current["drawdown"])
    if dollars is not None:
        band["dollars"] = dollars
    return band
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
python $WT/scripts/dev/testrun.py file tests/analytics/test_variance_band_assembly.py
python $WT/scripts/dev/testrun.py file tests/analytics/test_variance_band_paths.py
python $WT/scripts/dev/testrun.py file tests/analytics/test_variance_band_days.py
```

Expected: all three pass, `0 failed`. `testrun.py file` includes `slow` tests, so the timing test runs; it measures CPU time, so a loaded machine slows it less. If it fails on CPU time, profile (`python -m cProfile -s cumtime`) before changing anything; never raise the bound.

- [ ] **Step 6: Complexity and JSON-readiness**

```bash
python -m radon cc -s -n C $WT/swingbot/core/analytics/variance_band.py
python -c "import json, sys; sys.path.insert(0, r'$WT'); from tests.analytics.test_variance_band_assembly import _book, _dates; from swingbot.core.analytics.variance_band import variance_band; print(json.dumps(variance_band(_book(_dates([5] * 20)), paths=500, outer=5, outer_paths=100))[:300])"
```

Expected: radon prints nothing; the second command prints the start of a JSON object (`json.dumps` raising would mean a numpy scalar leaked into the band).

- [ ] **Step 7: Commit**

```bash
git -C $WT add swingbot/core/analytics/variance_band.py tests/analytics/test_variance_band_assembly.py
git -C $WT commit -m "feat(analytics): v175 variance_band assembly: era pool, zones, ExpR caveat, dollars"
git -C $R status --short
```

Expected: one commit on the branch; `$R` unchanged.

### Task V175-4: Calibration test: per-look `outside` rate on i.i.d. and week-correlated books

**Model:** opus — statistical calibration whose measured rate the panel caption rests on

**Files:**
- Test: `tests/analytics/test_variance_band_calibration.py` (suite `edge-analytics`, marked `slow`)
- Modify: `docs/superpowers/plans/2026-10-18-v175-normal-bad-luck-variance-band_0-index.md` (§ Progress only, on `main` in `$R`)

**Interfaces:**
- Consumes (V175-1, V175-2): `CloseDay`, `day_kind`, `current_run`, `window_drawdown`, `zone_of`, `sample_paths`, `path_longest_runs`, `path_max_drawdowns`, `WINDOW`, `SEED`, `OUTSIDE_PCT`.
- Produces: the recorded per-look rates (the test docstring and the index's § Progress). Nothing in code.

**What is measured.** A *look* compares the book's current state with its 50-day band, as the panel and the scan do. Each simulated book has a known close-day R process. Its first 30 weeks build the band with the module's own sampler and statistics, and the next 10 weeks (50 close days) are the look: the run in progress at their end and the window drawdown over them, placed with `zone_of`. The rate is the share of 400 books whose look lands `outside`. Two processes are measured, i.i.d. and week-correlated (a bad week makes every day in it likelier to lose), because the week-block bootstrap exists for the second.

**Rates measured while writing this plan** (the code in V175-1..V175-3 as written there; the test is seeded, so the same code gives the same numbers):

| Process | Run outside | Drawdown outside |
|---|---|---|
| i.i.d. | 1.00% | 2.50% |
| week-correlated | 0.75% | 3.25% |

Both statistics sit **below** 5% per look: the band holds the worst run and the deepest drawdown of a whole 50-day path, while a look sees the run in progress and the drawdown from the window's peak to now. The spec expected the drawdown rate "near 5%". It is lower for that reason, and the test bounds are set on the measured values, not on the spec's guess: run at most 5%, drawdown between 1% and 8%. The caption's wording ("will sometimes appear by chance alone") holds either way: one look is rarely `outside`, and many looks over months make one likelier. This is reported to the controller (`OPEN`); it is not a reason to change a frozen constant.

- [ ] **Step 1: Confirm the symbols**

```bash
git -C $WT grep -n "^def sample_paths\|^def path_longest_runs\|^def path_max_drawdowns\|^def current_run\|^def window_drawdown\|^def zone_of" -- swingbot/core/analytics/variance_band.py
```

Expected: all six found (V175-1 and V175-2 are committed).

- [ ] **Step 2: Write the calibration test**

Create `$WT/tests/analytics/test_variance_band_calibration.py`:

```python
"""v175 § Testing, calibration: the per-look ``outside`` rate.

Each simulated book has a known daily R process. Its first 30 weeks (150
close days) build the 50-day band exactly as ``horizon_band`` does (week
blocks, the module's sampler and statistics, seed ``SEED``; 2 000 paths
per book to keep the file fast). The next 10 weeks (50 close days) are
the "look": the current run at their end and the window drawdown over
them, compared with the band's p95 through ``zone_of``. The rate is the
share of books whose look lands ``outside``.

Two processes, close-day R in {-1, +1.5, 0}:
  * i.i.d.: P = (0.50, 0.40, 0.10) every day;
  * week-correlated: each week is "bad" with probability 0.3
    (P = 0.75, 0.20, 0.05) else (0.40, 0.50, 0.10), days i.i.d. inside it.

Measured (400 books per process, generator seed 2026):
  * i.i.d.:          run 1.00%, drawdown 2.50%
  * week-correlated: run 0.75%, drawdown 3.25%
The current statistics are peak-to-now and the run in progress at one
moment, while the band holds the worst run and the deepest drawdown of a
whole path, so a look falls at or below the band's 5%. The panel caption
("Checked continuously, so 'beyond 95%' will sometimes appear by chance
alone") rests on these per-look rates: a single look is rarely outside,
and many looks over months make one more likely.
"""
from datetime import date, timedelta

import numpy as np
import pytest

from swingbot.core.analytics import variance_band as vb
from swingbot.core.analytics.variance_band import CloseDay

pytestmark = pytest.mark.slow

BOOKS = 400
HIST_WEEKS = 30
LOOK_WEEKS = 10
BAND_PATHS = 2_000
VALUES = np.array([-1.0, 1.5, 0.0])
START = date(2025, 1, 6)


def _iid_week(rng):
    return rng.choice(VALUES, size=5, p=[0.50, 0.40, 0.10])


def _correlated_week(rng):
    p = [0.75, 0.20, 0.05] if rng.random() < 0.3 else [0.40, 0.50, 0.10]
    return rng.choice(VALUES, size=5, p=p)


def _close_days(rs):
    return [CloseDay(START + timedelta(days=i), float(r), vb.day_kind(float(r)))
            for i, r in enumerate(rs)]


def _band_p95(blocks):
    paths = vb.sample_paths(blocks, vb.WINDOW, BAND_PATHS, np.random.default_rng(vb.SEED))
    run = int(np.percentile(vb.path_longest_runs(paths), vb.OUTSIDE_PCT, method="higher"))
    drawdown = round(float(np.percentile(vb.path_max_drawdowns(paths), vb.OUTSIDE_PCT)), 2)
    return run, drawdown


def _outside_rates(week):
    rng = np.random.default_rng(2026)
    run_out = drawdown_out = 0
    for _ in range(BOOKS):
        run_p95, drawdown_p95 = _band_p95([week(rng) for _ in range(HIST_WEEKS)])
        look = _close_days(np.concatenate([week(rng) for _ in range(LOOK_WEEKS)]))
        run, _ = vb.current_run(look)
        drawdown, _ = vb.window_drawdown(look)
        run_out += vb.zone_of(run, run_p95, run_p95) == "outside"
        drawdown_out += vb.zone_of(drawdown, drawdown_p95, drawdown_p95) == "outside"
    return run_out / BOOKS, drawdown_out / BOOKS


@pytest.mark.parametrize("week", [_iid_week, _correlated_week], ids=["iid", "week-correlated"])
def test_per_look_outside_rate(week):
    run_rate, drawdown_rate = _outside_rates(week)
    print(f"{week.__name__}: run {run_rate:.4f}, drawdown {drawdown_rate:.4f}")
    assert run_rate <= 0.05
    assert 0.01 <= drawdown_rate <= 0.08
```

The `print` puts the measured rates in the `-s` output for Step 3. The docstring's "Measured" lines hold the plan-time numbers and are replaced with yours in Step 4 if they differ.

- [ ] **Step 3: Run it and read the rates**

```bash
python -m pytest $WT/tests/analytics/test_variance_band_calibration.py -s -q -p no:cacheprovider
```

Expected: `2 passed` and two printed lines, about 10 s. With V175-1..V175-3 exactly as the plan wrote them:
`_iid_week: run 0.0100, drawdown 0.0250` and `_correlated_week: run 0.0075, drawdown 0.0325`.
A different rate means the module differs from the plan (rng order, the sampler's batch width, quantile method). Find the difference; never retune the process or the bounds to make a number match. A failing bound is a finding: stop and report it with the rates, do not loosen the assertion.

- [ ] **Step 4: Record the rates**

If the printed rates differ from the docstring's, write the printed ones into the docstring's "Measured" lines. Then, in the **main tree**, replace the body of `## Progress` in `$R/docs/superpowers/plans/2026-10-18-v175-normal-bad-luck-variance-band_0-index.md` (keep the heading) with:

```markdown
Phase 1 (V175-1..V175-4) done on the branch. Calibration (V175-4, `tests/analytics/test_variance_band_calibration.py`, 400 synthetic books per process, seeded): per-look `outside` rate, run / drawdown: i.i.d. 1.00% / 2.50%; week-correlated 0.75% / 3.25%. Both below the band's 5%, because a look sees the run in progress and peak-to-now, not a whole path's worst. Synthetic books, not the live book.
```

using the rates printed in Step 3.

- [ ] **Step 5: Run the module's test files together**

```bash
python $WT/scripts/dev/testrun.py file tests/analytics/test_variance_band_calibration.py
python $WT/scripts/dev/testrun.py file tests/analytics/test_variance_band_assembly.py
```

Expected: both pass, `0 failed`.

- [ ] **Step 6: Commit (branch, then the index on main)**

```bash
git -C $WT add tests/analytics/test_variance_band_calibration.py
git -C $WT commit -m "test(analytics): v175 calibration of the per-look outside rate"
git -C $R add docs/superpowers/plans/2026-10-18-v175-normal-bad-luck-variance-band_0-index.md
git -C $R commit -m "docs(plans): v175 progress: phase 1 done, calibration rates recorded"
git -C $R status --short
```

Expected: one commit on the branch, one on `main` touching only the index; `$R` otherwise unchanged.

