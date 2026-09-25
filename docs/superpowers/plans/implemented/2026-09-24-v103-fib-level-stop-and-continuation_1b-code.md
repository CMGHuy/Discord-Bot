# v103 Part 1b — Code (worktree branch)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Global Constraints, Review Focus and Parallelisation live in `2026-09-24-v103-fib-level-stop-and-continuation_0-index.md` and bind every task here.

**Spec:** `docs/superpowers/specs/2026-09-24-v103-fib-level-stop-and-continuation-design.md`

Tasks V103-1..5 are in `2026-09-24-v103-fib-level-stop-and-continuation_1a-code.md`.

## Parallelisation

- **Group 1 (parallel):** V103-6, V103-7 here, with V103-1 and V103-2 in `_1a-code.md`.
- **Sequential:** V103-8 after V103-5 (in `_1a`) + V103-7.

---

# Phase A — Code (continued)

### Task V103-6: Admin gate description renders a fully-off gate honestly

**Files:**
- Modify: `swingbot/admin/queries.py` (`_gate_description`)
- Test: `tests/admin/test_gate_description.py` (create)

- [ ] **Step 1: Write the failing test**

```python
"""v103: a strategy gated to no direction must not render as 'no gate'."""
from swingbot.admin import queries


def test_empty_directions_reads_disabled(monkeypatch):
    monkeypatch.setitem(queries.STRATEGY_GATES, "Probe", {"directions": ()})
    assert queries._gate_description("Probe") == "disabled (no direction allowed)"


def test_single_direction_and_missing_gate_are_unchanged(monkeypatch):
    monkeypatch.setitem(queries.STRATEGY_GATES, "Probe", {"directions": ("bullish",)})
    assert queries._gate_description("Probe") == "bullish only"
    monkeypatch.delitem(queries.STRATEGY_GATES, "Probe")
    assert queries._gate_description("Probe") == "no gate (all directions, all horizons)"
```

Run: `python scripts/dev/testrun.py file tests/admin/test_gate_description.py`
Expected: FAIL, `AssertionError: 'no gate (all directions, all horizons)' != 'disabled (no direction allowed)'`.

- [ ] **Step 2: Implement**

In `_gate_description`, directly after the `if not gate: return "no gate (all directions, all horizons)"` guard, add:

```python
    directions = gate.get("directions")
    if directions is not None and len(directions) == 0:
        return "disabled (no direction allowed)"
```

Then delete the later `directions = gate.get("directions")` line, since the value now comes from the new block. Leave the rest unchanged.

- [ ] **Step 3: Run and commit**

Run: `python scripts/dev/testrun.py file tests/admin/test_gate_description.py` → 2 passed.

```bash
git add swingbot/admin/queries.py tests/admin/test_gate_description.py
git commit -m "fix(v103): admin gate description reads 'disabled' for a no-direction gate"
```

---

### Task V103-7: Grid-agnostic funnel `fib_funnel.py`, with v102 moved onto it

**Files:**
- Create: `scripts/backtest/fib_funnel.py`
- Modify: `scripts/backtest/measure_fib_confluence.py` (constants and helper functions now come from `fib_funnel`)
- Test: `tests/scripts/test_fib_funnel.py` (create); `tests/scripts/test_measure_fib_confluence.py` stays **unchanged** and must stay green

**Interfaces:**
- Produces (module `fib_funnel`):
  - Constants: `WR_FLOOR, MIN_N_TRAIN, MIN_N_VALIDATION, MAX_SCRATCH_SHARE, FOLD_MIN_N, FOLD_POSITIVE_SHARE, MIN_QUALIFYING_FOLDS, TRAIN_START_YEAR, FOLD_YEARS, BOOTSTRAP_SEED`.
  - Functions:
    - `cell_key(value) -> str`
    - `pooled(rows) -> dict`
    - `dir_rows(rows, direction)`, `year_rows(rows, first, last)`
    - `badge_verdict(stats, min_n) -> {"clears", "clauses"}`
    - `expr_lower_bound(rows, *, n_resamples, seed) -> float | None`
    - `tier2_verdict(stats, lower_bound, min_n) -> {"clears", "clauses"}`
    - `score_cell(rows, min_n, *, n_resamples, seed) -> {"stats", "lower_bound", "tier1", "tier2", "tier"}`
    - `plateau_ok(passes, grid, value) -> bool`
    - `stage1(rows_by_cell, direction, grid, *, n_resamples, seed) -> {"cells", "plateau_tier1", "plateau_tier2", "winner", "winner_tier"}`
    - `fold_pick(rows_by_cell, direction, year, grid)`
    - `fold_verdict(folds)`
    - `stage2(rows_by_cell, direction, grid) -> {"folds", "verdict"}`

- [ ] **Step 1: Write the failing tests**

```python
"""v103: grid-agnostic Fibonacci funnel -- two tiers, plateau, folds."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))

import fib_funnel as f  # noqa: E402

FAST = dict(n_resamples=400, seed=42)
GRID = (0.1, 0.25, 0.5)


def _r(ticker, outcome, r, year="2015", direction="bullish"):
    return {"ticker": ticker, "horizon_key": "4w", "direction": direction,
            "entry_date": f"{year}-06-01", "outcome": outcome, "r_multiple": r}


def tier1_only():
    """WR 76%, ExpR > 0, but one ticker carries it -> the bootstrap lower bound < 0."""
    rows = [_r("T0", "win", 3.0) for _ in range(20)]
    for k in range(1, 10):
        rows += [_r(f"T{k}", "win", 0.1), _r(f"T{k}", "loss", -1.0)]
    return rows


def tier2_only():
    """WR 33% (fails the badge), but every ticker is +0.333R -> lower bound > 0."""
    rows = []
    for k in range(10):
        rows += [_r(f"T{k}", "win", 3.0) for _ in range(2)] + [_r(f"T{k}", "loss", -1.0) for _ in range(4)]
    return rows


def losers():
    return [_r(f"T{k}", "loss", -1.0) for k in range(40)]


def test_cell_key_is_stable():
    assert [f.cell_key(v) for v in (0.0, 0.1, 0.618, 1.0)] == ["0", "0.1", "0.618", "1"]


def test_score_cell_assigns_tiers():
    assert f.score_cell(tier1_only(), 30, **FAST)["tier"] == 1
    t2 = f.score_cell(tier2_only(), 30, **FAST)
    assert t2["tier"] == 2 and t2["lower_bound"] > 0 and not t2["tier1"]["clears"]
    assert f.score_cell(losers(), 30, **FAST)["tier"] is None
    assert f.score_cell(tier1_only(), 30, **FAST)["tier2"]["clauses"]["lower_bound"] is False


def test_lower_bound_is_deterministic_and_none_when_empty():
    assert f.expr_lower_bound(tier1_only(), **FAST) == f.expr_lower_bound(tier1_only(), **FAST)
    assert f.expr_lower_bound([], **FAST) is None


def test_stage1_prefers_a_tier1_plateau():
    rows = {f.cell_key(v): tier1_only() for v in GRID}
    out = f.stage1(rows, "bullish", GRID, **FAST)
    assert out["plateau_tier1"] == list(GRID) and out["winner_tier"] == 1


def test_stage1_falls_back_to_a_tier2_plateau():
    rows = {f.cell_key(v): tier2_only() for v in GRID}
    out = f.stage1(rows, "bullish", GRID, **FAST)
    assert out["plateau_tier1"] == [] and out["winner_tier"] == 2 and out["winner"] in GRID


def test_stage1_isolated_spike_has_no_winner():
    rows = {f.cell_key(0.1): losers(), f.cell_key(0.25): tier1_only(), f.cell_key(0.5): losers()}
    out = f.stage1(rows, "bullish", GRID, **FAST)
    assert out["winner"] is None and out["winner_tier"] is None


def test_fold_pick_uses_only_the_train_span():
    rows = {f.cell_key(v): [] for v in GRID}
    rows[f.cell_key(0.1)] = ([_r("A", "win", 2.0, "2011") for _ in range(20)]
                             + [_r("A", "loss", -1.0, "2011") for _ in range(15)]
                             + [_r("A", "loss", -1.0, "2016") for _ in range(40)])
    rows[f.cell_key(0.25)] = ([_r("A", "win", 2.0, "2011") for _ in range(5)]
                              + [_r("A", "loss", -1.0, "2011") for _ in range(30)]
                              + [_r("A", "win", 2.0, "2016") for _ in range(40)])
    assert f.fold_pick(rows, "bullish", 2013, GRID) == 0.1
    assert f.fold_pick(rows, "bullish", 2011, GRID) is None
    assert f.fold_pick(rows, "bullish", 2017, GRID) == 0.25


def test_fold_verdict_two_thirds_and_minimum_three():
    good, bad, thin = {"n": 20, "expectancy_r": 0.2}, {"n": 20, "expectancy_r": -0.1}, {"n": 5, "expectancy_r": 1.0}
    assert f.fold_verdict([{"tol": 0.1, "stats": s} for s in (good, good, bad, thin)])["clears"] is True
    assert f.fold_verdict([{"tol": 0.1, "stats": s} for s in (good, bad, bad)])["clears"] is False
    v = f.fold_verdict([{"tol": 0.1, "stats": good}, {"tol": 0.1, "stats": good}, {"tol": None, "stats": None}])
    assert v["clears"] is False and v["unselected"] == 1


def test_stage2_shape():
    rows = {f.cell_key(v): tier2_only() for v in GRID}
    out = f.stage2(rows, "bullish", GRID)
    assert len(out["folds"]) == len(f.FOLD_YEARS) and set(out["verdict"]) >= {"clears", "qualifying"}
```

Run: `python scripts/dev/testrun.py file tests/scripts/test_fib_funnel.py`
Expected: FAIL, `ModuleNotFoundError: No module named 'fib_funnel'`.

- [ ] **Step 2: Implement `scripts/backtest/fib_funnel.py`**

```python
"""Grid-agnostic Fibonacci measurement funnel, shared by v102
(measure_fib_confluence.py) and v103 (measure_fib_v103.py).

Pure functions over trade rows ({"ticker", "horizon_key", "direction",
"entry_date", "outcome", "r_multiple"}); no data loading, no backtest.
Tier 1 = the strategy badge. Tier 2 (v103) = ExpR > 0 with a ticker-cluster
bootstrap lower bound > 0, no WR floor.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from swingbot.core.backtesting import acceptance, arm_rule  # noqa: E402

WR_FLOOR = 50.0
MIN_N_TRAIN = 30
MIN_N_VALIDATION = 15
MAX_SCRATCH_SHARE = 0.5
FOLD_MIN_N = 15
FOLD_POSITIVE_SHARE = 2 / 3
MIN_QUALIFYING_FOLDS = 3
TRAIN_START_YEAR = 2010
FOLD_YEARS = tuple(range(2013, 2024))
BOOTSTRAP_SEED = 42


def cell_key(value) -> str:
    return f"{float(value):g}"


def pooled(rows):
    return arm_rule.pooled_stats([SimpleNamespace(**r) for r in rows])


def dir_rows(rows, direction):
    return [r for r in rows if r["direction"] == direction]


def year_rows(rows, first, last):
    return [r for r in rows if first <= int(r["entry_date"][:4]) <= last]


def _floors(stats, min_n):
    return {
        "n": (stats.get("n") or 0) >= min_n,
        "scratch": (stats.get("scratch_timeout_share") is not None
                    and stats["scratch_timeout_share"] <= MAX_SCRATCH_SHARE),
    }


def badge_verdict(stats, min_n):
    clauses = {
        "wr": stats.get("win_rate") is not None and stats["win_rate"] >= WR_FLOOR,
        "exp_r": stats.get("expectancy_r") is not None and stats["expectancy_r"] > 0,
        **_floors(stats, min_n),
    }
    return {"clears": all(clauses.values()), "clauses": clauses}


def expr_lower_bound(rows, *, n_resamples=acceptance.BOOTSTRAP_RESAMPLES, seed=BOOTSTRAP_SEED):
    """Ticker-cluster bootstrap of ExpR (acceptance.cluster_bootstrap with an
    empty baseline arm); the 100*ALPHA/2 percentile, the convention
    acceptance.py uses for every lower bound. None when nothing is closed."""
    trades = [SimpleNamespace(**r) for r in rows]
    draws = acceptance.cluster_bootstrap(
        [], trades, lambda _b, c: acceptance.expectancy_r(c), n_resamples=n_resamples, seed=seed)
    if draws.size == 0:
        return None
    return float(np.percentile(draws, 100 * acceptance.ALPHA / 2))


def tier2_verdict(stats, lower_bound, min_n):
    clauses = {
        "exp_r": stats.get("expectancy_r") is not None and stats["expectancy_r"] > 0,
        "lower_bound": lower_bound is not None and lower_bound > 0,
        **_floors(stats, min_n),
    }
    return {"clears": all(clauses.values()), "clauses": clauses}


def score_cell(rows, min_n, *, n_resamples=acceptance.BOOTSTRAP_RESAMPLES, seed=BOOTSTRAP_SEED):
    stats = pooled(rows)
    lower = expr_lower_bound(rows, n_resamples=n_resamples, seed=seed) if rows else None
    t1, t2 = badge_verdict(stats, min_n), tier2_verdict(stats, lower, min_n)
    tier = 1 if t1["clears"] else (2 if t2["clears"] else None)
    return {"stats": stats, "lower_bound": lower, "tier1": t1, "tier2": t2, "tier": tier}


def plateau_ok(passes, grid, value):
    """`value` passes AND every grid neighbour (one step each side) passes."""
    i = list(grid).index(value)
    neighbours = [grid[j] for j in (i - 1, i + 1) if 0 <= j < len(grid)]
    return bool(passes[value]) and all(passes[n] for n in neighbours)


def _pick_winner(cells, plateau1, plateau2):
    for tier, plateau in ((1, plateau1), (2, plateau2)):
        if plateau:
            return max(plateau, key=lambda v: cells[v]["stats"]["expectancy_r"]), tier
    return None, None


def stage1(rows_by_cell, direction, grid, *, n_resamples=acceptance.BOOTSTRAP_RESAMPLES,
           seed=BOOTSTRAP_SEED):
    cells = {v: score_cell(dir_rows(rows_by_cell[cell_key(v)], direction), MIN_N_TRAIN,
                           n_resamples=n_resamples, seed=seed) for v in grid}
    t1 = {v: cells[v]["tier1"]["clears"] for v in grid}
    t2 = {v: cells[v]["tier2"]["clears"] for v in grid}
    plateau1 = [v for v in grid if plateau_ok(t1, grid, v)]
    plateau2 = [v for v in grid if plateau_ok(t2, grid, v)]
    winner, tier = _pick_winner(cells, plateau1, plateau2)
    return {"cells": {cell_key(v): c for v, c in cells.items()}, "plateau_tier1": plateau1,
            "plateau_tier2": plateau2, "winner": winner, "winner_tier": tier}


def fold_pick(rows_by_cell, direction, year, grid):
    """Train span TRAIN_START_YEAR..year-1: the highest-ExpR grid cell with
    decided N >= MIN_N_TRAIN. None when no cell qualifies."""
    best = None
    for v in grid:
        stats = pooled(dir_rows(year_rows(rows_by_cell[cell_key(v)], TRAIN_START_YEAR, year - 1),
                                direction))
        if stats["n"] < MIN_N_TRAIN or stats["expectancy_r"] is None:
            continue
        if best is None or stats["expectancy_r"] > best[1]:
            best = (v, stats["expectancy_r"])
    return None if best is None else best[0]


def fold_verdict(folds):
    qualifying = [x for x in folds if x["stats"] is not None and x["stats"]["n"] >= FOLD_MIN_N]
    positive = sum(1 for x in qualifying
                   if x["stats"]["expectancy_r"] is not None and x["stats"]["expectancy_r"] > 0)
    clears = (len(qualifying) >= MIN_QUALIFYING_FOLDS
              and positive >= FOLD_POSITIVE_SHARE * len(qualifying))
    return {"clears": clears, "qualifying": len(qualifying), "positive": positive,
            "unselected": sum(1 for x in folds if x["tol"] is None)}


def stage2(rows_by_cell, direction, grid):
    folds = []
    for year in FOLD_YEARS:
        v = fold_pick(rows_by_cell, direction, year, grid)
        stats = (pooled(dir_rows(year_rows(rows_by_cell[cell_key(v)], year, year), direction))
                 if v is not None else None)
        folds.append({"test_year": year, "tol": v, "stats": stats})
    return {"folds": folds, "verdict": fold_verdict(folds)}
```

- [ ] **Step 3: Move v102 onto it (behaviour unchanged)**

In `scripts/backtest/measure_fib_confluence.py`:

1. Replace the eleven constant lines `TRAIN_START_YEAR = 2010` … `MIN_QUALIFYING_FOLDS = 3` with the block below. Keep `TRAIN_EXT`, `VALIDATION`, `GRID` and `BASELINE_TOL`, which stay in this file. That leaves `TRAIN_START_YEAR` and `FOLD_YEARS` defined only by the import.

```python
# v103: one grid-agnostic funnel for v102 and v103 -- same values, one source.
from fib_funnel import FOLD_YEARS, MIN_N_TRAIN, MIN_N_VALIDATION  # noqa: E402
from fib_funnel import badge_verdict, fold_verdict, plateau_ok, pooled  # noqa: E402
from fib_funnel import cell_key as tol_key  # noqa: E402
from fib_funnel import dir_rows as _dir, year_rows as _years  # noqa: E402
from fib_funnel import fold_pick as _fold_pick_on  # noqa: E402
```

After the edit, run `git grep -n "WR_FLOOR\|MAX_SCRATCH_SHARE\|FOLD_MIN_N\|FOLD_POSITIVE_SHARE\|MIN_QUALIFYING_FOLDS\|TRAIN_START_YEAR" -- scripts/backtest/measure_fib_confluence.py`. It must return nothing: those constants are now only read inside `fib_funnel`. If a hit remains, import that name too; never re-define it.

2. Delete the local definitions of `tol_key`, `pooled`, `badge_verdict`, `_dir`, `_years` and `fold_verdict`.

3. Replace `_plateau_ok` and `fold_pick` with:

```python
def _plateau_ok(cells, tol):
    return plateau_ok({t: cells[t]["verdict"]["clears"] for t in cells}, GRID, tol)


def fold_pick(rows_by_tol, direction, year):
    """v102's GRID bound onto fib_funnel.fold_pick (train span 2010..year-1)."""
    return _fold_pick_on(rows_by_tol, direction, year, GRID)
```

`stage1`, `stage2`, `registry_record` and every `_cmd_*` stay as they are.

- [ ] **Step 4: Run tests and complexity**

Run: `python scripts/dev/testrun.py file tests/scripts/test_fib_funnel.py` → 10 passed.
Run: `python scripts/dev/testrun.py file tests/scripts/test_measure_fib_confluence.py` → 12 passed, with **the file unchanged**.
Run: `python -m radon cc -s -n C scripts/backtest/fib_funnel.py scripts/backtest/measure_fib_confluence.py` → nothing listed.

- [ ] **Step 5: Commit**

```bash
git add scripts/backtest/fib_funnel.py scripts/backtest/measure_fib_confluence.py tests/scripts/test_fib_funnel.py
git commit -m "refactor(v103): grid-agnostic fib_funnel with a Tier 2 bootstrap; v102 moved onto it unchanged"
```

---

### Task V103-8: `measure_fib_v103.py` — count / collect / evaluate / validation / emit-registry

Load `backtest-gate` first.

**Files:**
- Create: `scripts/backtest/measure_fib_v103.py`
- Test: `tests/scripts/test_measure_fib_v103.py` (create)

**Interfaces:**
- Consumes:
  - `fib_funnel` (V103-7).
  - `measure_fib_confluence`: `TRAIN_EXT, VALIDATION, Progress, _load_frames, _write, require_ext_cache`.
  - `measure_bearish_arms`: `_unmasked_gates, apply_laggard_rule`.
  - `run_backtest_range`: `_build_asof_map, merge_registry, window_trades`.
  - `config.FIB_LEVEL_STOP_*` (V103-1); `DEFAULT_PARAMS["Fibonacci Continuation"]` (V103-4).
- Produces:
  - `MECHANISMS`; `mechanism_cell(mech, value)` (context manager); `direction_gate(strategy, direction)`.
  - `collect_trades(mech, frames, asof_map, value, window, *, directions, horizons, run_fn, progress)`.
  - `count_signals(mech, frames, values, *, horizons)`; `stage0_closures(counts, mech)`.
  - `evaluate(mech, rows_by_cell, *, closed, n_resamples, seed)`; `validation_verdict(rows, tier, *, n_resamples, seed)`.
  - `require_committed(path)`; `registry_status(payloads, rows)`; `registry_record(strategy, rows, status, run_date)`; `main(argv=None)`.

- [ ] **Step 1: Write the failing tests**

```python
"""v103: measurement funnel for mechanisms A and C (logic + refusals; no backtest)."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace as T

import pytest

from tests.helpers import make_ohlcv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))

FAST = dict(n_resamples=400, seed=42)


def _m():
    import measure_fib_v103 as m
    return m


def _r(ticker, outcome, r, direction="bullish", year="2015"):
    return {"ticker": ticker, "horizon_key": "4w", "direction": direction,
            "entry_date": f"{year}-06-01", "outcome": outcome, "r_multiple": r}


def _tier2_rows(direction="bullish"):
    rows = []
    for k in range(10):
        rows += [_r(f"T{k}", "win", 3.0, direction) for _ in range(2)]
        rows += [_r(f"T{k}", "loss", -1.0, direction) for _ in range(4)]
    return rows


def test_mechanism_cell_sets_and_restores():
    m = _m()
    from swingbot import config
    from swingbot.core.market import entry_filters as ef
    before = (config.FIB_LEVEL_STOP_ATR, config.FIB_LEVEL_STOP_DIRECTIONS)
    with m.mechanism_cell("A", 0.25):
        assert ef._fib_level_stop_config() == (0.25, frozenset({"bullish", "bearish"}))
    with m.mechanism_cell("A", 0.0):
        assert ef._fib_level_stop_config() == (0.0, frozenset())
    assert (config.FIB_LEVEL_STOP_ATR, config.FIB_LEVEL_STOP_DIRECTIONS) == before
    d_max = ef.DEFAULT_PARAMS["Fibonacci Continuation"]["d_max"]
    with m.mechanism_cell("C", 0.786):
        assert ef.DEFAULT_PARAMS["Fibonacci Continuation"]["d_max"] == 0.786
    assert ef.DEFAULT_PARAMS["Fibonacci Continuation"]["d_max"] == d_max


def test_direction_gate_uses_the_live_gate_only_where_it_admits():
    m = _m()
    with m.direction_gate("Fibonacci", "bullish"):
        assert m.STRATEGY_GATES["Fibonacci"]["directions"] == ("bullish",)
    with m.direction_gate("Fibonacci", "bearish"):
        assert set(m.STRATEGY_GATES["Fibonacci"]["directions"]) == {"bullish", "bearish"}
    with m.direction_gate("Fibonacci Continuation", "bullish"):
        assert set(m.STRATEGY_GATES["Fibonacci Continuation"]["directions"]) == {"bullish", "bearish"}
    assert m.STRATEGY_GATES["Fibonacci Continuation"] == {"directions": ()}


def test_collect_trades_window_laggard_and_directions():
    m = _m()
    frame = make_ohlcv([100.0] * 300, start="2012-01-02")
    seen = []

    def run_fn(ticker, df, strategy, horizon, **kw):
        seen.append((strategy, tuple(m.STRATEGY_GATES[strategy]["directions"])))
        return T(trades=[
            T(direction="bullish", entry_date="2012-06-01", outcome="win", r_multiple=2.0, context={}),
            T(direction="bullish", entry_date="2024-06-01", outcome="win", r_multiple=2.0, context={}),
            T(direction="bearish", entry_date="2012-06-01", outcome="loss", r_multiple=-1.0,
              context={"rs_combined": 10.0}),
            T(direction="bearish", entry_date="2012-06-01", outcome="win", r_multiple=2.0,
              context={"rs_combined": 80.0}),
        ])

    progress = T(tick=lambda label: None)
    rows = m.collect_trades("C", {"AAA": frame}, {}, 0.618, m.TRAIN_EXT, horizons=("4w",),
                            run_fn=run_fn, progress=progress)
    assert [(r["direction"], r["entry_date"]) for r in rows] == [("bullish", "2012-06-01"),
                                                                ("bearish", "2012-06-01")]
    assert all(s == "Fibonacci Continuation" and set(d) == {"bullish", "bearish"} for s, d in seen)
    only = m.collect_trades("C", {"AAA": frame}, {}, 0.618, m.TRAIN_EXT, directions=("bearish",),
                            horizons=("4w",), run_fn=run_fn, progress=progress)
    assert {r["direction"] for r in only} == {"bearish"}


def test_count_signals_totals_years_and_horizons(monkeypatch):
    m = _m()
    import pandas as pd
    frame = make_ohlcv([100.0] * 10, start="2012-12-27")

    def fake(strategy, df, horizon):
        s = pd.Series(True, index=df.index)
        return s, s

    monkeypatch.setattr(m, "entries_for", fake)
    out = m.count_signals("C", {"AAA": frame}, (0.5,), horizons=("2w", "4w"))
    cell = out["0.5|bullish"]
    assert cell["total"] == 20 and cell["by_year"] == {"2012": 6, "2013": 14}
    assert cell["by_horizon"] == {"2w": 10, "4w": 10}


def test_stage0_closures_read_the_loosest_cell():
    m = _m()
    counts = {"0.1|bullish": {"total": 30}, "0.1|bearish": {"total": 29}}
    assert m.stage0_closures(counts, "A") == ["bearish"]


def test_evaluate_marks_stage0_closures_and_reports_the_a_baseline():
    m = _m()
    rows = {"0": _tier2_rows(), "0.1": _tier2_rows(), "0.25": _tier2_rows(), "0.5": _tier2_rows()}
    out = m.evaluate("A", rows, closed=("bearish",), **FAST)
    assert out["mechanism"] == "A" and out["bearish"]["closed_at"] == "stage0"
    assert out["bullish"]["baseline"]["n"] == 60 and out["bullish"]["stage1"]["winner_tier"] == 2


def test_validation_verdict_scores_only_the_assigned_tier():
    m = _m()
    rows = _tier2_rows()
    assert m.validation_verdict(rows, 2, **FAST)["passes"] is True
    assert m.validation_verdict(rows, 1, **FAST)["passes"] is False


def test_validation_refuses_a_second_shot(tmp_path):
    m = _m()
    out = tmp_path / "v.json"
    out.write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit):
        m.main(["validation", "--mechanism", "A", "--direction", "bullish", "--evaluate", "e.json",
                "--preregistration", "p.md", "--out", str(out)])


def test_validation_refuses_an_uncommitted_preregistration(tmp_path):
    m = _m()
    (tmp_path / "p.md").write_text("x", encoding="utf-8")
    with pytest.raises(SystemExit):
        m.require_committed(tmp_path / "p.md")
    m.require_committed(ROOT / "bot.py")


def test_validation_refuses_a_cell_that_did_not_proceed(monkeypatch, tmp_path):
    m = _m()
    monkeypatch.setattr(m, "require_committed", lambda path: None)
    ev = tmp_path / "e.json"
    ev.write_text(json.dumps({"mechanism": "A", "bullish": {"proceed_to_validation": False}}),
                  encoding="utf-8")
    base = ["validation", "--direction", "bullish", "--evaluate", str(ev),
            "--preregistration", "p.md", "--out", str(tmp_path / "v.json")]
    with pytest.raises(SystemExit):
        m.main(base[:1] + ["--mechanism", "A"] + base[1:])
    with pytest.raises(SystemExit):
        m.main(base[:1] + ["--mechanism", "C"] + base[1:])        # evaluate file is for A


def test_emit_refuses_mixed_mechanisms_and_failures(tmp_path):
    m = _m()
    ok = {"mechanism": "A", "strategy": "Fibonacci", "verdict": {"passes": True, "tier": 2}, "rows": []}
    paths = []
    for name, payload in (("a", ok), ("c", {**ok, "mechanism": "C"}),
                          ("f", {**ok, "verdict": {"passes": False, "tier": 2}})):
        p = tmp_path / f"{name}.json"
        p.write_text(json.dumps(payload), encoding="utf-8")
        paths.append(str(p))
    reg = str(tmp_path / "reg.json")
    with pytest.raises(SystemExit):
        m.main(["emit-registry", "--validation-json", paths[0], paths[1], "--registry", reg,
                "--run-date", "2026-10-01"])
    with pytest.raises(SystemExit):
        m.main(["emit-registry", "--validation-json", paths[2], "--registry", reg,
                "--run-date", "2026-10-01"])


def test_registry_status_and_record():
    m = _m()
    rows = [_r("A", "win", 2.0) for _ in range(10)] + [_r("A", "loss", -1.0) for _ in range(5)]
    t1 = [{"verdict": {"tier": 1}}]
    assert m.registry_status(t1, rows) == "VALIDATED"
    assert m.registry_status([{"verdict": {"tier": 1}}, {"verdict": {"tier": 2}}], rows) == "WEAK"
    rec = m.registry_record("Fibonacci Continuation", rows, "WEAK", "2026-10-01")
    assert rec["strategy"] == "Fibonacci Continuation" and rec["horizon"] is None
    assert rec["window"] == "2024-01-01..2025-12-31" and rec["n"] == 15
```

Run: `python scripts/dev/testrun.py file tests/scripts/test_measure_fib_v103.py`
Expected: FAIL, `ModuleNotFoundError: No module named 'measure_fib_v103'`.

- [ ] **Step 2: Implement `scripts/backtest/measure_fib_v103.py`**

```python
#!/usr/bin/env python3
"""v103: Fibonacci level-stop (A) and measured-move continuation (C) funnel.

Spec: docs/superpowers/specs/2026-09-24-v103-fib-level-stop-and-continuation-design.md
Reads the EXTENDED cache only -- run with BACKTEST_CACHE_DIR=data/backtest_cache_ext.

  count          Stage 0: entry signals per cell x direction, by year and horizon
  collect        TRAIN_EXT trades per cell (A also the b=0 reference), open directions only
  evaluate       Stage 1 (two tiers, plateau) + Stage 2 folds, pure over a collect JSON
  validation     Stage 3: ONE mechanism x direction at the committed evaluate's winner.
                 Refuses a second shot, an uncommitted pre-registration or evaluate
                 file, and a cell that did not proceed.
  emit-registry  one registry row per mechanism, from passing validation JSONs only

Run (from the repo root):
  BACKTEST_CACHE_DIR=data/backtest_cache_ext python scripts/backtest/measure_fib_v103.py count --mechanism A --out <json>
  BACKTEST_CACHE_DIR=data/backtest_cache_ext python scripts/backtest/measure_fib_v103.py collect --mechanism A --stage0 <count json> --out <json>
  python scripts/backtest/measure_fib_v103.py evaluate --rows <collect json> --out <json>
  BACKTEST_CACHE_DIR=data/backtest_cache_ext python scripts/backtest/measure_fib_v103.py validation \\
      --mechanism A --direction bullish --evaluate <json> --preregistration <md> --out <json>
"""
from __future__ import annotations

import argparse
import collections
import contextlib
import json
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(Path(__file__).resolve().parent)]

import fib_funnel  # noqa: E402
from fib_funnel import BOOTSTRAP_SEED, MIN_N_TRAIN, MIN_N_VALIDATION, cell_key, dir_rows  # noqa: E402
from measure_bearish_arms import _unmasked_gates, apply_laggard_rule  # noqa: E402
from measure_fib_confluence import (  # noqa: E402
    TRAIN_EXT, VALIDATION, Progress, _load_frames, _write, require_ext_cache,
)
from run_backtest_range import _build_asof_map, merge_registry, window_trades  # noqa: E402
from swingbot import config  # noqa: E402
from swingbot.core.backtesting.acceptance import BOOTSTRAP_RESAMPLES  # noqa: E402
from swingbot.core.backtesting.backtest import run_backtest  # noqa: E402
from swingbot.core.market.entry_filters import DEFAULT_PARAMS, entries_for, gate_override  # noqa: E402
from swingbot.core.market.strategy_types import HORIZONS, STRATEGY_GATES  # noqa: E402

DIRECTIONS = ("bullish", "bearish")
ALL_HZ = tuple(HORIZONS)
_MISSING = object()

# --- pre-registered (spec "Windows, populations and funnel") ---
MECHANISMS = {
    "A": SimpleNamespace(strategy="Fibonacci", grid=(0.1, 0.25, 0.5), loosest=0.1, baseline=0.0),
    "C": SimpleNamespace(strategy="Fibonacci Continuation", grid=(0.5, 0.618, 0.786),
                         loosest=0.786, baseline=None),
}


@contextlib.contextmanager
def _config_values(**values):
    saved = {k: getattr(config, k, _MISSING) for k in values}
    try:
        for k, v in values.items():
            setattr(config, k, v)
        yield
    finally:
        for k, v in saved.items():
            if v is _MISSING:
                delattr(config, k)
            else:
                setattr(config, k, v)


@contextlib.contextmanager
def _param_value(strategy, key, value):
    params = DEFAULT_PARAMS[strategy]
    previous = params[key]
    params[key] = value
    try:
        yield
    finally:
        params[key] = previous


def mechanism_cell(mech, value):
    """One grid cell's knob. A: FIB_LEVEL_STOP_ATR=b on both directions
    (b=0 = today's swing stop, the reference). C: DEFAULT_PARAMS d_max."""
    if mech == "A":
        on = float(value) > 0
        return _config_values(FIB_LEVEL_STOP_ATR=float(value),
                              FIB_LEVEL_STOP_DIRECTIONS="bullish,bearish" if on else "")
    return _param_value(MECHANISMS["C"].strategy, "d_max", float(value))


def direction_gate(strategy, direction):
    """The live gate where it admits `direction`; unmasked (v93) where not."""
    gates = STRATEGY_GATES.get(strategy) or {}
    directions = gates.get("directions")
    if directions is not None and direction not in directions:
        return gate_override(strategy, _unmasked_gates(strategy))
    return contextlib.nullcontext()


def _row(ticker, horizon_key, trade):
    return {"ticker": ticker, "horizon_key": horizon_key, "direction": trade.direction,
            "entry_date": trade.entry_date, "outcome": trade.outcome, "r_multiple": trade.r_multiple}


def _direction_pass(strategy, frames, asof_map, direction, window, horizons, run_fn, progress, label):
    raw = []
    with direction_gate(strategy, direction):
        for ticker, frame in sorted(frames.items()):
            progress.tick(f"{label} {direction} {ticker}")
            for h in horizons:
                summary = run_fn(ticker, frame, strategy, h, one_at_a_time=True, exit_model="v2",
                                 scale_out=True, tp2_mode="levels", frictions=True,
                                 asof=asof_map.get(ticker))
                raw.extend({"ticker": ticker, "horizon_key": h, "trade": t}
                           for t in window_trades(summary, *window) if t.direction == direction)
    if direction == "bearish":
        raw = apply_laggard_rule(raw)
    return [_row(r["ticker"], r["horizon_key"], r["trade"]) for r in raw]


def collect_trades(mech, frames, asof_map, value, window, *, directions=DIRECTIONS, horizons=ALL_HZ,
                   run_fn=None, progress=None):
    spec = MECHANISMS[mech]
    run_fn = run_fn or run_backtest
    progress = progress or Progress(len(frames) * len(directions))
    rows = []
    with mechanism_cell(mech, value):
        for direction in directions:
            rows.extend(_direction_pass(spec.strategy, frames, asof_map, direction, window,
                                        horizons, run_fn, progress, f"{mech} {cell_key(value)}"))
    return rows


def _signal_years(strategy, frame, horizon, direction):
    bullish, bearish = entries_for(strategy, frame, horizon)
    series = bullish if direction == "bullish" else bearish
    dates = frame.index[series.to_numpy(dtype=bool)].strftime("%Y-%m-%d")
    return [d[:4] for d in dates if TRAIN_EXT[0] <= d <= TRAIN_EXT[1]]


def _count_direction(strategy, frames, direction, horizons):
    by_year, by_hz = collections.Counter(), collections.Counter()
    with direction_gate(strategy, direction):
        for frame in frames.values():
            for h in horizons:
                years = _signal_years(strategy, frame, h, direction)
                by_year.update(years)
                by_hz[h] += len(years)
    return {"total": sum(by_year.values()), "by_year": dict(sorted(by_year.items())),
            "by_horizon": {h: by_hz[h] for h in horizons}}


def count_signals(mech, frames, values, *, horizons=ALL_HZ):
    """Stage 0: raw entry signals (an UPPER bound on decided trades) per
    cell|direction, TRAIN_EXT only, by year and by horizon."""
    strategy = MECHANISMS[mech].strategy
    out = {}
    for value in values:
        with mechanism_cell(mech, value):
            for direction in DIRECTIONS:
                out[f"{cell_key(value)}|{direction}"] = _count_direction(strategy, frames, direction,
                                                                         horizons)
    return out


def stage0_closures(counts, mech):
    key = cell_key(MECHANISMS[mech].loosest)
    return [d for d in DIRECTIONS if counts[f"{key}|{d}"]["total"] < MIN_N_TRAIN]


def _evaluate_direction(spec, rows_by_cell, direction, n_resamples, seed):
    s1 = fib_funnel.stage1(rows_by_cell, direction, spec.grid, n_resamples=n_resamples, seed=seed)
    s2 = fib_funnel.stage2(rows_by_cell, direction, spec.grid)
    proceed = s1["winner"] is not None and s2["verdict"]["clears"]
    baseline = (fib_funnel.pooled(dir_rows(rows_by_cell[cell_key(spec.baseline)], direction))
                if spec.baseline is not None else None)
    return {"baseline": baseline, "stage1": s1, "stage2": s2, "proceed_to_validation": proceed,
            "validation_cell": s1["winner"] if proceed else None,
            "tier": s1["winner_tier"] if proceed else None}


def evaluate(mech, rows_by_cell, *, closed=(), n_resamples=BOOTSTRAP_RESAMPLES, seed=BOOTSTRAP_SEED):
    spec = MECHANISMS[mech]
    out = {"mechanism": mech, "strategy": spec.strategy}
    for direction in DIRECTIONS:
        out[direction] = ({"closed_at": "stage0", "proceed_to_validation": False,
                           "validation_cell": None, "tier": None}
                          if direction in closed
                          else _evaluate_direction(spec, rows_by_cell, direction, n_resamples, seed))
    return out


def validation_verdict(rows, tier, *, n_resamples=BOOTSTRAP_RESAMPLES, seed=BOOTSTRAP_SEED):
    """Score the VALIDATION rows on the tier TRAIN assigned -- never another."""
    scored = fib_funnel.score_cell(rows, MIN_N_VALIDATION, n_resamples=n_resamples, seed=seed)
    key = "tier1" if tier == 1 else "tier2"
    return {"tier": tier, "stats": scored["stats"], "lower_bound": scored["lower_bound"],
            "clauses": scored[key]["clauses"], "passes": scored[key]["clears"]}


def require_committed(path):
    """SystemExit unless `path` is tracked and has no uncommitted change."""
    path = Path(path).resolve()
    tracked = subprocess.run(["git", "ls-files", "--error-unmatch", str(path)], cwd=ROOT,
                             capture_output=True)
    clean = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", str(path)], cwd=ROOT,
                           capture_output=True)
    if tracked.returncode != 0 or clean.returncode != 0:
        raise SystemExit(f"must be committed before VALIDATION: {path}")


def registry_status(payloads, rows):
    tiers = {p["verdict"]["tier"] for p in payloads}
    badge = fib_funnel.badge_verdict(fib_funnel.pooled(rows), MIN_N_VALIDATION)["clears"]
    return "VALIDATED" if tiers == {1} and badge else "WEAK"


def registry_record(strategy, rows, status, run_date):
    stats = fib_funnel.pooled(rows)
    return {"source": "strategy", "strategy": strategy, "horizon": None, "status": status,
            "n": stats["n"],
            "win_rate": None if stats["win_rate"] is None else round(stats["win_rate"], 1),
            "expectancy_r": None if stats["expectancy_r"] is None else round(stats["expectancy_r"], 3),
            "window": f"{VALIDATION[0]}..{VALIDATION[1]}", "run_date": run_date}


def _frames_and_asof(args):
    require_ext_cache()
    frames = _load_frames(args.universe, args.tickers)
    return frames, _build_asof_map(list(frames), frames, args.universe)


def _cmd_count(args):
    require_ext_cache()
    spec = MECHANISMS[args.mechanism]
    frames = _load_frames(args.universe, args.tickers)
    values = ((spec.baseline,) if spec.baseline is not None else ()) + spec.grid
    counts = count_signals(args.mechanism, frames, values)
    _write(args.out, {"mechanism": args.mechanism, "universe_n": len(frames), "counts": counts,
                      "closed_at_stage0": stage0_closures(counts, args.mechanism)})


def _cmd_collect(args):
    started = time.monotonic()
    spec = MECHANISMS[args.mechanism]
    closed = json.loads(Path(args.stage0).read_text(encoding="utf-8"))["closed_at_stage0"]
    directions = tuple(d for d in DIRECTIONS if d not in closed)
    if not directions:
        raise SystemExit(f"{args.mechanism}: every direction closed at Stage 0")
    frames, asof_map = _frames_and_asof(args)
    values = ((spec.baseline,) if spec.baseline is not None else ()) + spec.grid
    progress = Progress(len(values) * len(frames) * len(directions))
    rows_by_cell = {cell_key(v): collect_trades(args.mechanism, frames, asof_map, v, TRAIN_EXT,
                                                directions=directions, progress=progress)
                    for v in values}
    _write(args.out, {"mechanism": args.mechanism, "window": TRAIN_EXT, "universe_n": len(frames),
                      "closed_at_stage0": closed, "rows_by_cell": rows_by_cell,
                      "elapsed_s": round(time.monotonic() - started, 1)})


def _cmd_evaluate(args):
    collected = json.loads(Path(args.rows).read_text(encoding="utf-8"))
    _write(args.out, evaluate(collected["mechanism"], collected["rows_by_cell"],
                              closed=tuple(collected["closed_at_stage0"])))


def _validation_target(args):
    require_committed(args.preregistration)
    require_committed(args.evaluate)
    ev = json.loads(Path(args.evaluate).read_text(encoding="utf-8"))
    if ev.get("mechanism") != args.mechanism:
        raise SystemExit(f"--evaluate is for mechanism {ev.get('mechanism')}, not {args.mechanism}")
    cell = ev[args.direction]
    if not cell.get("proceed_to_validation"):
        raise SystemExit(f"{args.mechanism} {args.direction} did not proceed to VALIDATION")
    return cell["validation_cell"], cell["tier"]


def _cmd_validation(args):
    if Path(args.out).exists():
        raise SystemExit(f"VALIDATION is one shot, ever: {args.out} already exists")
    value, tier = _validation_target(args)
    frames, asof_map = _frames_and_asof(args)
    rows = collect_trades(args.mechanism, frames, asof_map, value, VALIDATION,
                          directions=(args.direction,))
    _write(args.out, {"mechanism": args.mechanism, "strategy": MECHANISMS[args.mechanism].strategy,
                      "direction": args.direction, "cell": value,
                      "preregistration": str(args.preregistration),
                      "verdict": validation_verdict(rows, tier), "rows": rows})


def _cmd_emit(args):
    payloads = [json.loads(Path(p).read_text(encoding="utf-8")) for p in args.validation_json]
    if len({p["mechanism"] for p in payloads}) != 1:
        raise SystemExit("one mechanism per registry row")
    if not all(p["verdict"]["passes"] for p in payloads):
        raise SystemExit("refusing to emit a failing VALIDATION")
    rows = [r for p in payloads for r in p["rows"]]
    merge_registry(args.registry, [registry_record(payloads[0]["strategy"], rows,
                                                   registry_status(payloads, rows), args.run_date)])


def _parser():
    ap = argparse.ArgumentParser(description="v103 Fibonacci level-stop / continuation funnel")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("count", "collect", "validation"):
        p = sub.add_parser(name)
        p.add_argument("--mechanism", required=True, choices=tuple(MECHANISMS))
        p.add_argument("--out", required=True)
        p.add_argument("--universe")
        p.add_argument("--tickers", help="comma-separated subset, smoke runs only")
    sub.choices["collect"].add_argument("--stage0", required=True)
    val = sub.choices["validation"]
    val.add_argument("--direction", required=True, choices=DIRECTIONS)
    val.add_argument("--evaluate", required=True)
    val.add_argument("--preregistration", required=True)
    ev = sub.add_parser("evaluate")
    ev.add_argument("--rows", required=True)
    ev.add_argument("--out", required=True)
    em = sub.add_parser("emit-registry")
    em.add_argument("--validation-json", nargs="+", required=True)
    em.add_argument("--registry", required=True)
    em.add_argument("--run-date", required=True)
    return ap


COMMANDS = {"count": _cmd_count, "collect": _cmd_collect, "evaluate": _cmd_evaluate,
            "validation": _cmd_validation, "emit-registry": _cmd_emit}


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    COMMANDS[args.cmd](args)
    print(f"v103 {args.cmd} done", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Run tests, complexity, smoke refusal**

Run: `python scripts/dev/testrun.py file tests/scripts/test_measure_fib_v103.py` → 13 passed.
Run: `python -m radon cc -s -n C scripts/backtest/measure_fib_v103.py` → nothing listed.
Run: `python scripts/backtest/measure_fib_v103.py count --mechanism A --tickers AAPL --out "<scratchpad>/v103_smoke.json"`, *without* `BACKTEST_CACHE_DIR`. Expected: exits with `v102 reads the extended cache only: ...`, the shared guard.

- [ ] **Step 4: Commit, then review and merge Phase A**

```bash
git add scripts/backtest/measure_fib_v103.py tests/scripts/test_measure_fib_v103.py
git commit -m "feat(v103): measure_fib_v103 -- two-tier funnel for A and C, validation refusals"
```

Then dispatch the final whole-branch review of V103-1..8 on the most capable model. Point it at the index's Review Focus list and the 2% "drop, never cap" invariant, and fix Critical/Important findings with TDD.
Then merge to `main` per the `worktree-lifecycle` skill. Check `git log main` for other sessions' commits first; if main moved, rebase or merge and run `testrun.py fast` once over the merge.
