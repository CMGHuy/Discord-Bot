# v113 Part 1c — `measure_v113.py`: collect, evaluate, holdout, registry

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Global Constraints, amendments, Review Focus and Parallelisation live in `2026-09-28-v113-bearish-day-coverage_0-index.md` and bind every task here.

**Spec:** `docs/superpowers/specs/2026-09-28-v113-bearish-day-coverage-design.md` §3–§7

Same worktree and branch as Parts 1a/1b. No command here contains the substring `eval`: the tests are selected by file path, never by `-k`.

---

### Task V113-10: `measure_v113.py` — collect and evaluate Parts A, B and D

**Files:**
- Create: `scripts/backtest/measure_v113.py`
- Create: `tests/scripts/test_measure_v113.py`

**Interfaces:**
- Consumes: `funnel.stage1`, `funnel.stage2`, `funnel.score_cell`, `funnel.fixed_folds`, `funnel.fold_verdict`, `funnel.pooled`, `funnel.assert_rows_before`, `funnel.cell_key` (`scripts/backtest/funnel.py`); `measure_v104.trade_rows(strategy, frames, asof_map, direction, window, horizons, *, progress=None, label="", run_fn=None) -> list[dict]` (rows carry `ticker, horizon_key, direction, entry_date, outcome, r_multiple, risk_pct`), `measure_v104._frames(args)`, `measure_v104.params(strategy, values)`, `measure_v104.TRAIN`, `measure_v104.FOLD_YEARS` (13 years, 2013..2025); `measure_fib_confluence.Progress`, `_write`; `admits`, `LEGACY_HORIZONS` (V113-2); `reward_floor.DROPS/PASSES/reset` (V113-5); `short_entries.FADE` and the fade's plan (V113-7/8); `stop_scope.stop_ceiling`.
- Produces (module `measure_v113`, consumed by V113-11 and Phase B):
  - Constants `HOLDOUT_END = "2026-09-25"`, `HZ = "1w"`, `A_GRID = (1.0, 1.25, 1.5)`, `PART_B` (22 pairs), `D_TICKERS = ("SH", "PSQ", "RWM", "DOG")`, `RESULTS`.
  - `d_cells() -> tuple[tuple[str, str], ...]`; `admit_1w(strategy, direction)` context manager; `cap_bind_rate(rows, strategy, direction) -> float | None`; `floor_counts(strategy) -> dict`; `strict_clauses(scored) -> dict`.
  - `collect_a(frames, asof_map, window, *, values=A_GRID, progress=None, run_fn=None) -> {"rows_by_cell": {cell_key: rows}, "floor": {cell_key: floor_counts}}`; `collect_b(strategy, direction, frames, asof_map, window, *, progress=None, run_fn=None) -> {"rows": rows, "floor": floor_counts}`; `collect_d(frames, asof_map, window, *, progress=None, run_fn=None) -> rows` (each row also carries `strategy`).
  - `evaluate_a(collected, **kw)`, `evaluate_b(strategy, direction, collected, **kw)`, `evaluate_d(rows, **kw)` — each returns a dict with `part`, `strategy`, `direction`, `proceed_to_holdout`, `tier` (and `validation_cell` for A).
  - `_ab_frames(args)`, `_d_frames(args)`; commands `collect-a`, `collect-b`, `collect-d`, `evaluate`; `EVALUATORS`, `COMMANDS`, `_parser()`, `main(argv=None)`.

- [ ] **Step 1: Write the failing tests** — `tests/scripts/test_measure_v113.py`:

```python
"""v113 funnel logic -- no market data: synthetic rows and fake backtests."""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "backtest"))
import measure_v113 as mv  # noqa: E402

from swingbot.core.backtesting.backtest import ALL_STRATEGIES  # noqa: E402
from swingbot.core.market.entry_filters import DEFAULT_PARAMS  # noqa: E402
from swingbot.core.market.short_entries import FADE  # noqa: E402
from swingbot.core.market.strategy_types import (LEGACY_HORIZONS, SHORT_STRATEGIES,  # noqa: E402
                                                 STRATEGY_GATES, admits)
from swingbot.core.planning import reward_floor  # noqa: E402

FAST = dict(n_resamples=200, seed=42)
YEARS = (2013, 2014, 2015, 2016)


def _rows(years, per_year, win_share, *, direction="bearish", tickers=8, risk_pct=2.0, strategy=None):
    rows = []
    for year in years:
        wins = round(per_year * win_share)
        for i in range(per_year):
            win = i < wins
            row = {"ticker": f"T{i % tickers}", "horizon_key": "1w", "direction": direction,
                   "entry_date": f"{year}-06-01", "outcome": "win" if win else "loss",
                   "r_multiple": 1.0 if win else -1.0, "risk_pct": risk_pct}
            if strategy:
                row["strategy"] = strategy
            rows.append(row)
    return rows


def _trade(direction="bullish", date="2015-01-05"):
    return SimpleNamespace(direction=direction, entry_date=date, outcome="win", r_multiple=1.0,
                           entry=100.0, stop_loss=98.0, context=None)


def test_preregistered_constants():
    assert mv.HOLDOUT_END == "2026-09-25" and mv.HZ == "1w" and mv.A_GRID == (1.0, 1.25, 1.5)
    assert mv.D_TICKERS == ("SH", "PSQ", "RWM", "DOG")
    assert len(mv.PART_B) == 22 and len(set(mv.PART_B)) == 22
    strategies = {strategy for strategy, _ in mv.PART_B}
    assert strategies == set(ALL_STRATEGIES)
    assert not strategies & (set(SHORT_STRATEGIES) | {"Fibonacci Continuation"})


def test_d_cells_are_todays_live_bullish_masks():
    cells = set(mv.d_cells())
    assert ("VWAP", "4w") in cells and ("VWAP", "2w") not in cells
    assert ("MACD", "3m") in cells and ("MACD", "2w") not in cells
    assert {("EMA Crossover", hk) for hk in LEGACY_HORIZONS} <= cells
    assert all(hk != "1w" for _, hk in cells)
    assert {strategy for strategy, _ in cells} <= set(ALL_STRATEGIES)


def test_admit_1w_admits_exactly_one_pair_and_restores():
    before = dict(STRATEGY_GATES["VWAP"])
    with mv.admit_1w("VWAP", "bearish"):
        assert admits("VWAP", "bearish", "1w") and not admits("VWAP", "bullish", "1w")
        assert admits("VWAP", "bullish", "4w") and not admits("VWAP", "bullish", "2w")
        assert not admits("VWAP", "bearish", "4w")
    assert STRATEGY_GATES["VWAP"] == before and not admits("VWAP", "bearish", "1w")
    with mv.admit_1w("EMA Crossover", "bullish"):
        assert admits("EMA Crossover", "bullish", "1w") and admits("EMA Crossover", "bearish", "2w")
    assert "EMA Crossover" not in STRATEGY_GATES


def test_collect_b_runs_1w_only_with_its_cell_admitted():
    calls = []

    def fake_run(ticker, frame, strategy, horizon, **kw):
        calls.append((horizon, admits(strategy, "bearish", "1w"), admits(strategy, "bullish", "1w")))
        return SimpleNamespace(trades=[])

    out = mv.collect_b("MACD", "bearish", {"AAA": None, "BBB": None}, {}, mv.TRAIN, run_fn=fake_run)
    assert calls == [("1w", True, False)] * 2
    assert out["rows"] == [] and out["floor"]["floor_drop_rate"] is None


def test_collect_a_runs_every_grid_value_under_its_own_m():
    seen = []

    def fake_run(ticker, frame, strategy, horizon, **kw):
        seen.append((strategy, horizon, DEFAULT_PARAMS[FADE]["m"], admits(FADE, "bearish", "1w")))
        return SimpleNamespace(trades=[])

    out = mv.collect_a({"AAA": None}, {}, mv.TRAIN, run_fn=fake_run)
    assert seen == [(FADE, "1w", m, True) for m in mv.A_GRID]
    assert set(out["rows_by_cell"]) == set(out["floor"]) == {"1", "1.25", "1.5"}
    assert DEFAULT_PARAMS[FADE]["m"] == 1.0 and not admits(FADE, "bearish", "1w")


def test_collect_d_runs_every_live_bullish_cell_and_tags_the_strategy():
    rows = mv.collect_d({"SH": None}, {}, mv.TRAIN,
                        run_fn=lambda ticker, frame, strategy, horizon, **kw: SimpleNamespace(trades=[_trade()]))
    assert len(rows) == len(mv.d_cells())
    assert {(row["strategy"], row["horizon_key"]) for row in rows} == set(mv.d_cells())


def test_floor_counts_and_cap_bind_rate():
    reward_floor.reset()
    reward_floor.DROPS[("MACD", "1w")] += 1
    reward_floor.PASSES[("MACD", "1w")] += 3
    assert mv.floor_counts("MACD") == {"floor_drops": 1, "floor_passes": 3, "floor_drop_rate": 0.25}
    reward_floor.reset()
    rows = _rows((2015,), 2, 0.5, risk_pct=2.0) + _rows((2015,), 2, 0.5, risk_pct=1.5)
    assert mv.cap_bind_rate(rows, "MACD", "bullish") == 0.5
    assert mv.cap_bind_rate([], "MACD", "bullish") is None


def test_part_b_needs_tier_1_and_a_positive_lower_bound(monkeypatch):
    collected = {"rows": _rows(YEARS, 20, 0.75), "floor": {}}
    ok = mv.evaluate_b("MACD", "bearish", collected, **FAST)
    assert ok["clauses"]["lower_bound"] and ok["stage2"]["clears"]
    assert ok["proceed_to_holdout"] and ok["tier"] == 1
    fake = {"stats": {}, "lower_bound": -0.1, "tier": 1,
            "tier1": {"clears": True, "clauses": {"wr": True, "exp_r": True, "n": True, "scratch": True}},
            "tier2": {"clears": False, "clauses": {"exp_r": True, "lower_bound": False, "n": True, "scratch": True}}}
    monkeypatch.setattr(mv.funnel, "score_cell", lambda *a, **k: fake)
    lucky = mv.evaluate_b("MACD", "bearish", collected, **FAST)
    assert not lucky["proceed_to_holdout"] and lucky["tier"] is None


def test_part_a_takes_the_plateau_winner_through_the_folds(monkeypatch):
    monkeypatch.setattr(mv.funnel, "stage1", lambda *a, **k: {"winner": 1.25, "winner_tier": 2, "cells": {}})
    monkeypatch.setattr(mv.funnel, "stage2", lambda *a, **k: {"verdict": {"clears": True}})
    collected = {"rows_by_cell": {"1": [], "1.25": [], "1.5": []}, "floor": {}}
    ok = mv.evaluate_a(collected, **FAST)
    assert ok["proceed_to_holdout"] and ok["validation_cell"] == {"value": 1.25} and ok["tier"] == 2
    monkeypatch.setattr(mv.funnel, "stage2", lambda *a, **k: {"verdict": {"clears": False}})
    no = mv.evaluate_a(collected, **FAST)
    assert not no["proceed_to_holdout"] and no["validation_cell"] is None and no["tier"] is None


def test_part_d_is_one_pooled_cell_with_reported_breakdowns():
    rows = (_rows(YEARS, 10, 0.8, direction="bullish", strategy="RSI")
            + _rows(YEARS, 10, 0.7, direction="bullish", strategy="MACD"))
    out = mv.evaluate_d(rows, **FAST)
    assert out["scored"]["stats"]["n"] == 80
    assert set(out["by_strategy"]) == {"RSI", "MACD"} and len(out["by_ticker"]) == 8
    assert out["proceed_to_holdout"] and out["tier"] in (1, 2)


def test_part_d_refuses_any_other_universe():
    with pytest.raises(SystemExit):
        mv._d_frames(SimpleNamespace(tickers="SH,PSQ", universe=None))


def test_every_part_has_an_evaluator():
    assert set(mv.EVALUATORS) == {"A", "B", "D"}
```

- [ ] **Step 2: Run to confirm it fails**

Run: `python scripts/dev/testrun.py file tests/scripts/test_measure_v113.py`
Expected: collection error — `ModuleNotFoundError: No module named 'measure_v113'`.

- [ ] **Step 3: Create `scripts/backtest/measure_v113.py`**

```python
#!/usr/bin/env python3
"""v113 measurement: Part A (Downtrend Overbought Fade on 1w, grid m), Part B
(the 22 legacy strategy x direction cells on 1w, Tier 1 + bootstrap lower
bound) and Part D (every live bullish mask on SH/PSQ/RWM/DOG, one pooled cell).

Stages (spec §6): collect -> evaluate (Stages 1-2 on TRAIN) -> holdout (Stage 3,
one shot per cell, thin-holdout rule) -> emit-registry. Reads the EXTENDED
cache only:
  BACKTEST_CACHE_DIR=data/backtest_cache_ext python scripts/backtest/measure_v113.py <command> ...
"""
from __future__ import annotations

import argparse
import collections
import contextlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(Path(__file__).resolve().parent)]

import funnel  # noqa: E402
from funnel import BOOTSTRAP_SEED, MIN_N_TRAIN, cell_key  # noqa: E402
from measure_fib_confluence import Progress, _write  # noqa: E402
from measure_v104 import FOLD_YEARS, TRAIN, _frames, params, trade_rows  # noqa: E402
from swingbot.core.backtesting.acceptance import BOOTSTRAP_RESAMPLES  # noqa: E402
from swingbot.core.backtesting.backtest import ALL_STRATEGIES  # noqa: E402
from swingbot.core.market.entry_filters import gate_override  # noqa: E402
from swingbot.core.market.short_entries import FADE  # noqa: E402
from swingbot.core.market.strategy_types import LEGACY_HORIZONS, STRATEGY_GATES, admits  # noqa: E402
from swingbot.core.planning import reward_floor  # noqa: E402
from swingbot.core.planning.stop_scope import stop_ceiling  # noqa: E402

# --- pre-registered constants (spec §1, §3-§6) ---
HOLDOUT_END: str | None = "2026-09-25"     # spec §6; frozen by the pre-registration commit (V113-13)
HZ = "1w"
A_GRID = (1.0, 1.25, 1.5)
PART_B = tuple((strategy, direction) for strategy in ALL_STRATEGIES for direction in ("bullish", "bearish"))
D_TICKERS = ("SH", "PSQ", "RWM", "DOG")
CAP_TOLERANCE_PCT = 0.001
RESULTS = ROOT / "docs" / "superpowers" / "results"


# --- small helpers ------------------------------------------------------------

def d_cells() -> tuple:
    """Every (strategy, horizon) today's live masks admit BULLISH (spec §5),
    legacy horizons only -- run unchanged on the four inverse ETFs."""
    return tuple((strategy, horizon) for strategy in ALL_STRATEGIES for horizon in LEGACY_HORIZONS
                 if admits(strategy, "bullish", horizon))


@contextlib.contextmanager
def admit_1w(strategy: str, direction: str):
    """Admit exactly (direction, 1w) for `strategy` during the run; every other
    pair keeps its live mask (spec §2)."""
    gates = dict(STRATEGY_GATES.get(strategy) or {})
    gates["cells"] = frozenset(gates.get("cells", ())) | {(direction, HZ)}
    with gate_override(strategy, gates):
        yield


def cap_bind_rate(rows, strategy, direction):
    """Share of trades whose planned risk sits on the 1w stop ceiling (spec §4)."""
    if not rows:
        return None
    cap = stop_ceiling(strategy, direction, HZ)[0]
    return sum(1 for row in rows if row["risk_pct"] >= cap - CAP_TOLERANCE_PCT) / len(rows)


def floor_counts(strategy) -> dict:
    """The 1w reward floor's decisions for `strategy` since the last reset (spec §4)."""
    key = (strategy, HZ)
    drops, passes = reward_floor.DROPS[key], reward_floor.PASSES[key]
    total = drops + passes
    return {"floor_drops": drops, "floor_passes": passes,
            "floor_drop_rate": drops / total if total else None}


def strict_clauses(scored) -> dict:
    """Part B's bar (spec §4): every Tier 1 clause AND the bootstrap lower bound > 0."""
    return {**scored["tier1"]["clauses"], "lower_bound": scored["tier2"]["clauses"]["lower_bound"]}


def _ab_frames(args):
    """Parts A and B run on the watchlist universe, never on Part D's ETFs."""
    frames, asof_map = _frames(args)
    return {ticker: frame for ticker, frame in frames.items() if ticker not in D_TICKERS}, asof_map


def _d_frames(args):
    if sorted((args.tickers or "").split(",")) != sorted(D_TICKERS):
        raise SystemExit(f"Part D runs on exactly --tickers {','.join(D_TICKERS)}")
    return _frames(args)


# --- collectors -----------------------------------------------------------------

def collect_a(frames, asof_map, window, *, values=A_GRID, progress=None, run_fn=None) -> dict:
    out = {"rows_by_cell": {}, "floor": {}}
    with admit_1w(FADE, "bearish"):
        for value in values:
            reward_floor.reset()
            with params(FADE, {"m": value}):
                out["rows_by_cell"][cell_key(value)] = trade_rows(
                    FADE, frames, asof_map, "bearish", window, (HZ,),
                    progress=progress, label=f"A m={cell_key(value)}", run_fn=run_fn)
            out["floor"][cell_key(value)] = floor_counts(FADE)
    return out


def collect_b(strategy, direction, frames, asof_map, window, *, progress=None, run_fn=None) -> dict:
    reward_floor.reset()
    with admit_1w(strategy, direction):
        rows = trade_rows(strategy, frames, asof_map, direction, window, (HZ,),
                          progress=progress, label=f"B {strategy} {direction}", run_fn=run_fn)
    return {"rows": rows, "floor": floor_counts(strategy)}


def collect_d(frames, asof_map, window, *, progress=None, run_fn=None) -> list:
    rows = []
    for strategy, horizon in d_cells():
        rows.extend({**row, "strategy": strategy} for row in trade_rows(
            strategy, frames, asof_map, "bullish", window, (horizon,),
            progress=progress, label=f"D {strategy} {horizon}", run_fn=run_fn))
    return rows


# --- evaluators (Stages 1-2 on TRAIN) --------------------------------------------

def evaluate_a(collected, *, n_resamples=BOOTSTRAP_RESAMPLES, seed=BOOTSTRAP_SEED) -> dict:
    """Stage 1: standard tiers per m, plateau winner (funnel.stage1). Stage 2:
    per-fold reselection over the grid (funnel.stage2)."""
    rows_by_cell = collected["rows_by_cell"]
    stage1 = funnel.stage1(rows_by_cell, "bearish", A_GRID, n_resamples=n_resamples, seed=seed)
    stage2 = funnel.stage2(rows_by_cell, "bearish", A_GRID, fold_years=FOLD_YEARS)
    proceed = stage1["winner"] is not None and stage2["verdict"]["clears"]
    return {"part": "A", "strategy": FADE, "direction": "bearish", "horizon": HZ,
            "stage1": stage1, "stage2": stage2, "floor": collected["floor"],
            "cap_bind": {key: cap_bind_rate(rows, FADE, "bearish") for key, rows in rows_by_cell.items()},
            "proceed_to_holdout": proceed,
            "validation_cell": {"value": stage1["winner"]} if proceed else None,
            "tier": stage1["winner_tier"] if proceed else None}


def evaluate_b(strategy, direction, collected, *, n_resamples=BOOTSTRAP_RESAMPLES,
               seed=BOOTSTRAP_SEED) -> dict:
    """Stage 1: the single cell must clear strict_clauses. Stage 2: fixed folds."""
    rows = collected["rows"]
    scored = funnel.score_cell(rows, MIN_N_TRAIN, n_resamples=n_resamples, seed=seed)
    clauses = strict_clauses(scored)
    folds = funnel.fixed_folds(rows, FOLD_YEARS)
    stage2 = funnel.fold_verdict(folds)
    proceed = all(clauses.values()) and stage2["clears"]
    return {"part": "B", "strategy": strategy, "direction": direction, "horizon": HZ,
            "scored": scored, "clauses": clauses, "folds": folds, "stage2": stage2,
            "floor": collected["floor"], "cap_bind_rate": cap_bind_rate(rows, strategy, direction),
            "proceed_to_holdout": proceed, "tier": 1 if proceed else None}


def _breakdown(rows, key) -> dict:
    groups = collections.defaultdict(list)
    for row in rows:
        groups[row[key]].append(row)
    return {name: funnel.pooled(group) for name, group in sorted(groups.items())}


def evaluate_d(rows, *, n_resamples=BOOTSTRAP_RESAMPLES, seed=BOOTSTRAP_SEED) -> dict:
    """One pooled cell, standard tiers; breakdowns are reported, never used to select."""
    scored = funnel.score_cell(rows, MIN_N_TRAIN, n_resamples=n_resamples, seed=seed)
    folds = funnel.fixed_folds(rows, FOLD_YEARS)
    stage2 = funnel.fold_verdict(folds)
    proceed = scored["tier"] is not None and stage2["clears"]
    return {"part": "D", "strategy": "inverse-etf-longs", "direction": "bullish", "horizon": None,
            "cells": [list(cell) for cell in d_cells()], "scored": scored, "folds": folds,
            "stage2": stage2, "by_strategy": _breakdown(rows, "strategy"),
            "by_ticker": _breakdown(rows, "ticker"),
            "proceed_to_holdout": proceed, "tier": scored["tier"] if proceed else None}


EVALUATORS = {
    "A": lambda collected: evaluate_a(collected),
    "B": lambda collected: evaluate_b(collected["strategy"], collected["direction"], collected),
    "D": lambda collected: evaluate_d(collected["rows"]),
}


# --- commands -------------------------------------------------------------------

def _cmd_collect_a(args):
    frames, asof_map = _ab_frames(args)
    collected = collect_a(frames, asof_map, TRAIN, progress=Progress(len(A_GRID) * len(frames)))
    for rows in collected["rows_by_cell"].values():
        funnel.assert_rows_before(rows, TRAIN[1])
    _write(args.out, {"part": "A", "window": list(TRAIN), "universe_n": len(frames), **collected})


def _cmd_collect_b(args):
    if (args.strategy, args.direction) not in PART_B:
        raise SystemExit(f"{args.strategy}:{args.direction} is not a pre-registered Part B cell")
    frames, asof_map = _ab_frames(args)
    collected = collect_b(args.strategy, args.direction, frames, asof_map, TRAIN,
                          progress=Progress(len(frames)))
    funnel.assert_rows_before(collected["rows"], TRAIN[1])
    _write(args.out, {"part": "B", "strategy": args.strategy, "direction": args.direction,
                      "window": list(TRAIN), "universe_n": len(frames), **collected})


def _cmd_collect_d(args):
    frames, asof_map = _d_frames(args)
    rows = collect_d(frames, asof_map, TRAIN, progress=Progress(len(d_cells()) * len(frames)))
    funnel.assert_rows_before(rows, TRAIN[1])
    _write(args.out, {"part": "D", "window": list(TRAIN), "universe_n": len(frames),
                      "tickers": sorted(frames), "cells": [list(cell) for cell in d_cells()], "rows": rows})


def _cmd_evaluate(args):
    collected = json.loads(Path(args.rows).read_text(encoding="utf-8"))
    _write(args.out, {"universe_n": collected["universe_n"], **EVALUATORS[collected["part"]](collected)})


def _parser():
    parser = argparse.ArgumentParser(description="v113 1w horizon, fade and inverse-ETF funnel")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("collect-a", "collect-b", "collect-d"):
        command = sub.add_parser(name)
        command.add_argument("--out", required=True)
        command.add_argument("--universe")
        command.add_argument("--tickers", help="comma-separated; Part D requires exactly SH,PSQ,RWM,DOG")
    sub.choices["collect-b"].add_argument("--strategy", required=True)
    sub.choices["collect-b"].add_argument("--direction", required=True, choices=("bullish", "bearish"))
    evaluate_parser = sub.add_parser("evaluate")
    evaluate_parser.add_argument("--rows", required=True)
    evaluate_parser.add_argument("--out", required=True)
    return parser


COMMANDS = {"collect-a": _cmd_collect_a, "collect-b": _cmd_collect_b, "collect-d": _cmd_collect_d,
            "evaluate": _cmd_evaluate}


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    COMMANDS[args.cmd](args)
    print(f"v113 {args.cmd} done", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests**

Run: `python scripts/dev/testrun.py file tests/scripts/test_measure_v113.py`
Expected: all PASS. If `test_part_b_needs_tier_1_and_a_positive_lower_bound`'s first half fails on `lower_bound` at 200 resamples, print `ok["scored"]["lower_bound"]` and raise `per_year` to 30 in that test only; do not loosen the clause.

Run: `python -m radon cc -s -n C scripts/backtest/measure_v113.py`
Expected: nothing listed.

Run: `python scripts/backtest/measure_v113.py --help`
Expected: usage listing `collect-a, collect-b, collect-d, evaluate` (argparse prints the subcommand names; the command line itself contains no `eval`).

- [ ] **Step 5: Commit**

```bash
git add scripts/backtest/measure_v113.py tests/scripts/test_measure_v113.py
git commit -m "feat(v113): measure_v113 collect and Stage 1-2 scoring -- A grid m on 1w, 22 Part B cells (Tier 1 + lower bound), Part D pooled cell

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V113-11: `measure_v113.py` — holdout (one shot, thin rule) and registry rows; Phase A close

**Files:**
- Modify: `scripts/backtest/measure_v113.py` (imports; new holdout and emit functions; `_parser`; `COMMANDS`)
- Modify: `tests/scripts/test_measure_v113.py` (append)

**Interfaces:**
- Consumes: everything V113-10 produced; `measure_v104.HOLDOUT_START`, `THIN_REOPEN`, `slug`; `measure_fib_v103.require_committed(path)`; `run_backtest_range.merge_registry(path, records)`; `funnel.MIN_N_VALIDATION`, `funnel.badge_verdict`.
- Produces: `holdout_window() -> (start, end)`; `candidate_slug(evaluated) -> str` (`a-fade`, `b-<slug>-<direction>`, `d-inverse-etfs`); `check_shot_allowed(candidate, out_path)`; `holdout_clauses(scored, part, tier) -> dict`; `verdict(rows, part, tier, **kw) -> dict`; `holdout_rows(evaluated, frames, asof_map, window) -> list`; `_validate_emit(payloads) -> str`; `_registry_row(strategy, payloads, run_date) -> dict` (horizon `"1w"`); commands `holdout` and `emit-registry`.

- [ ] **Step 1: Append the failing tests** to `tests/scripts/test_measure_v113.py`:

```python


# --- V113-11: holdout and registry ---------------------------------------------

import json  # noqa: E402


@pytest.fixture
def results(tmp_path, monkeypatch):
    monkeypatch.setattr(mv, "RESULTS", tmp_path)
    monkeypatch.setattr(mv, "HOLDOUT_END", "2026-09-25")
    return tmp_path


def _prior(results, name, status):
    (results / name).write_text(json.dumps({"status": status}), encoding="utf-8")


def test_candidate_slugs():
    assert mv.candidate_slug({"part": "A"}) == "a-fade"
    assert mv.candidate_slug({"part": "B", "strategy": "Break & Retest", "direction": "bearish"}) == \
        "b-break-and-retest-bearish"
    assert mv.candidate_slug({"part": "D"}) == "d-inverse-etfs"


def test_holdout_first_shot_is_allowed(results):
    mv.check_shot_allowed("a-fade", results / "2026-09-30-v113-holdout-a-fade.json")


def test_holdout_refuses_a_spent_shot_under_any_date(results):
    _prior(results, "2026-09-30-v113-holdout-a-fade.json", "scored")
    with pytest.raises(SystemExit):
        mv.check_shot_allowed("a-fade", results / "2027-03-01-v113-holdout-a-fade.json")


def test_holdout_refuses_the_thin_retry_before_twelve_months(results):
    _prior(results, "2026-09-30-v113-holdout-d-inverse-etfs.json", "sealed-thin")
    with pytest.raises(SystemExit):
        mv.check_shot_allowed("d-inverse-etfs", results / "2026-10-30-v113-holdout-d-inverse-etfs.json")


def test_holdout_allows_exactly_one_thin_retry_after_twelve_months(results, monkeypatch):
    _prior(results, "2026-09-30-v113-holdout-d-inverse-etfs.json", "sealed-thin")
    monkeypatch.setattr(mv, "HOLDOUT_END", "2026-12-31")
    mv.check_shot_allowed("d-inverse-etfs", results / "2027-01-05-v113-holdout-d-inverse-etfs.json")
    _prior(results, "2027-01-05-v113-holdout-d-inverse-etfs.json", "sealed-thin")
    with pytest.raises(SystemExit):
        mv.check_shot_allowed("d-inverse-etfs", results / "2027-02-01-v113-holdout-d-inverse-etfs.json")


def test_holdout_refuses_an_existing_output(results):
    out = results / "2026-09-30-v113-holdout-a-fade.json"
    out.write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit):
        mv.check_shot_allowed("a-fade", out)


def test_holdout_window_refuses_until_frozen(monkeypatch):
    monkeypatch.setattr(mv, "HOLDOUT_END", None)
    with pytest.raises(SystemExit):
        mv.holdout_window()
    monkeypatch.setattr(mv, "HOLDOUT_END", "2026-09-25")
    assert mv.holdout_window() == ("2026-01-01", "2026-09-25")


def test_verdict_seals_a_thin_holdout_with_n_only():
    assert mv.verdict(_rows((2026,), 10, 0.9), "A", 1, **FAST) == {"status": "sealed-thin", "n": 10}


def test_verdict_part_b_keeps_the_lower_bound_clause():
    out = mv.verdict(_rows((2026,), 20, 0.75), "B", 1, **FAST)
    assert out["status"] == "scored" and "lower_bound" in out["clauses"] and "wr" in out["clauses"]


def test_verdict_tier_2_has_no_win_rate_clause():
    out = mv.verdict(_rows((2026,), 20, 0.75, direction="bullish"), "D", 2, **FAST)
    assert "wr" not in out["clauses"] and "lower_bound" in out["clauses"]


def _payload(tmp_path, name, **kw):
    base = {"status": "scored", "passes": True, "part": "B", "strategy": "MACD", "direction": "bearish",
            "tier": 1, "window": ["2026-01-01", "2026-09-25"], "rows": _rows((2026,), 20, 0.75)}
    base.update(kw)
    path = tmp_path / name
    path.write_text(json.dumps(base), encoding="utf-8")
    return str(path)


def _emit(tmp_path, *paths):
    registry = tmp_path / "reg.json"
    mv._cmd_emit(SimpleNamespace(holdout_json=list(paths), registry=str(registry), run_date="2026-10-01"))
    return json.loads(registry.read_text(encoding="utf-8"))


def test_emit_writes_a_1w_row_for_the_shipped_cells(tmp_path, monkeypatch):
    monkeypatch.setitem(STRATEGY_GATES, "MACD", {**STRATEGY_GATES["MACD"], "cells": {("bearish", "1w")}})
    (row,) = _emit(tmp_path, _payload(tmp_path, "h.json"))
    assert (row["source"], row["strategy"], row["horizon"], row["n"]) == ("strategy", "MACD", "1w", 20)
    assert row["status"] == "VALIDATED" and row["window"] == "2026-01-01..2026-09-25"


def test_emit_refuses_part_d_a_failure_and_an_unshipped_direction(tmp_path, monkeypatch):
    monkeypatch.setitem(STRATEGY_GATES, "MACD", {**STRATEGY_GATES["MACD"], "cells": {("bearish", "1w")}})
    for bad in ({"part": "D", "strategy": "inverse-etf-longs"}, {"passes": False},
                {"direction": "bullish"}):
        with pytest.raises(SystemExit):
            _emit(tmp_path, _payload(tmp_path, "bad.json", **bad))
```

- [ ] **Step 2: Run to confirm they fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_measure_v113.py`
Expected: the new tests FAIL — `AttributeError: module 'measure_v113' has no attribute 'candidate_slug'` (and the rest likewise); the V113-10 tests still pass.

- [ ] **Step 3: Imports.** In `scripts/backtest/measure_v113.py` change

```python
from funnel import BOOTSTRAP_SEED, MIN_N_TRAIN, cell_key  # noqa: E402
from measure_fib_confluence import Progress, _write  # noqa: E402
from measure_v104 import FOLD_YEARS, TRAIN, _frames, params, trade_rows  # noqa: E402
```

to

```python
from funnel import BOOTSTRAP_SEED, MIN_N_TRAIN, MIN_N_VALIDATION, cell_key  # noqa: E402
from measure_fib_confluence import Progress, _write  # noqa: E402
from measure_fib_v103 import require_committed  # noqa: E402
from measure_v104 import (FOLD_YEARS, HOLDOUT_START, THIN_REOPEN, TRAIN, _frames,  # noqa: E402
                          params, slug, trade_rows)
from run_backtest_range import merge_registry  # noqa: E402
```

- [ ] **Step 4: Holdout and registry functions.** Insert directly above the `# --- commands ---` banner:

```python
# --- Stage 3: holdout -------------------------------------------------------------

def holdout_window() -> tuple:
    if HOLDOUT_END is None:
        raise SystemExit("HOLDOUT_END is not frozen -- the pre-registration commit freezes it")
    return HOLDOUT_START, HOLDOUT_END


_SLUGS = {
    "A": lambda evaluated: "a-fade",
    "B": lambda evaluated: f"b-{slug(evaluated['strategy'])}-{evaluated['direction']}",
    "D": lambda evaluated: "d-inverse-etfs",
}


def candidate_slug(evaluated: dict) -> str:
    return _SLUGS[evaluated["part"]](evaluated)


def check_shot_allowed(candidate: str, out_path) -> None:
    """One shot per cell under ANY date; a single sealed-thin shot may be
    retried once, and only when the holdout reaches 12 months."""
    if Path(out_path).exists():
        raise SystemExit(f"holdout output already exists: {out_path}")
    prior = sorted(Path(RESULTS).glob(f"*-v113-holdout-{candidate}.json"))
    if not prior:
        return
    statuses = [json.loads(path.read_text(encoding="utf-8")).get("status") for path in prior]
    if statuses != ["sealed-thin"]:
        raise SystemExit(f"holdout shot for {candidate} is spent ({prior[-1].name})")
    if (HOLDOUT_END or "") < THIN_REOPEN:
        raise SystemExit(f"{candidate} is sealed-thin; its one retry waits for HOLDOUT_END >= {THIN_REOPEN}")


def holdout_clauses(scored, part, tier) -> dict:
    """Part B keeps its strict bar on the holdout; A and D use their assigned tier."""
    if part == "B":
        return strict_clauses(scored)
    return dict(scored["tier1" if tier == 1 else "tier2"]["clauses"])


def verdict(rows, part, tier, *, n_resamples=BOOTSTRAP_RESAMPLES, seed=BOOTSTRAP_SEED) -> dict:
    """N < 15 writes N only (sealed-thin, shot unspent); otherwise the cell's clauses."""
    n = funnel.pooled(rows)["n"]
    if n < MIN_N_VALIDATION:
        return {"status": "sealed-thin", "n": n}
    scored = funnel.score_cell(rows, MIN_N_VALIDATION, n_resamples=n_resamples, seed=seed)
    clauses = holdout_clauses(scored, part, tier)
    return {"status": "scored", "tier": tier, "stats": scored["stats"], "lower_bound": scored["lower_bound"],
            "clauses": clauses, "passes": all(clauses.values())}


def holdout_rows(evaluated, frames, asof_map, window) -> list:
    part = evaluated["part"]
    if part == "A":
        value = evaluated["validation_cell"]["value"]
        return collect_a(frames, asof_map, window, values=(value,))["rows_by_cell"][cell_key(value)]
    if part == "B":
        return collect_b(evaluated["strategy"], evaluated["direction"], frames, asof_map, window)["rows"]
    return collect_d(frames, asof_map, window)


# --- registry ---------------------------------------------------------------------

def _validate_emit(payloads) -> str:
    """Raise unless every payload scored and passed, none is Part D (amendment 5),
    they share one strategy, and their directions are exactly that strategy's
    shipped 1w cells (a row ships only when every admitted direction passed)."""
    if not all(p.get("status") == "scored" and p.get("passes") for p in payloads):
        raise SystemExit("refusing to emit a failing or sealed holdout")
    if any(p["part"] == "D" for p in payloads):
        raise SystemExit("Part D pools strategies on four tickers -- it writes no registry row")
    strategies = {p["strategy"] for p in payloads}
    if len(strategies) != 1:
        raise SystemExit("one strategy per registry row")
    strategy = strategies.pop()
    shipped = {d for d, hk in (STRATEGY_GATES.get(strategy) or {}).get("cells", ()) if hk == HZ}
    if {p["direction"] for p in payloads} != shipped:
        raise SystemExit(f"{strategy}: a 1w row needs exactly its shipped 1w cells {sorted(shipped)}")
    return strategy


def _registry_row(strategy, payloads, run_date) -> dict:
    rows = [row for p in payloads for row in p["rows"]]
    stats = funnel.pooled(rows)
    badge = funnel.badge_verdict(stats, MIN_N_VALIDATION)["clears"]
    status = "VALIDATED" if {p["tier"] for p in payloads} == {1} and badge else "WEAK"
    return {"source": "strategy", "strategy": strategy, "horizon": HZ, "status": status, "n": stats["n"],
            "win_rate": None if stats["win_rate"] is None else round(stats["win_rate"], 1),
            "expectancy_r": None if stats["expectancy_r"] is None else round(stats["expectancy_r"], 3),
            "window": f"{HOLDOUT_START}..{payloads[0]['window'][1]}", "run_date": run_date}
```

- [ ] **Step 5: Commands, parser, dispatch.** Directly after `_cmd_evaluate` add:

```python
def _cmd_holdout(args):
    window = holdout_window()
    require_committed(args.preregistration)
    require_committed(args.evaluate)
    evaluated = json.loads(Path(args.evaluate).read_text(encoding="utf-8"))
    candidate = candidate_slug(evaluated)
    if not evaluated.get("proceed_to_holdout"):
        raise SystemExit(f"{candidate} did not proceed to the holdout")
    check_shot_allowed(candidate, args.out)
    frames, asof_map = _d_frames(args) if evaluated["part"] == "D" else _ab_frames(args)
    rows = holdout_rows(evaluated, frames, asof_map, window)
    result = verdict(rows, evaluated["part"], evaluated["tier"])
    payload = {"candidate": candidate, "part": evaluated["part"], "strategy": evaluated["strategy"],
               "direction": evaluated["direction"], "horizon": evaluated.get("horizon"),
               "window": list(window), "universe_n": len(frames), "evaluate": str(args.evaluate),
               "preregistration": str(args.preregistration), **result}
    if result["status"] == "scored":
        payload["rows"] = rows
    _write(args.out, payload)


def _cmd_emit(args):
    payloads = [json.loads(Path(path).read_text(encoding="utf-8")) for path in args.holdout_json]
    strategy = _validate_emit(payloads)
    merge_registry(args.registry, [_registry_row(strategy, payloads, args.run_date)])
```

Replace `_parser` and `COMMANDS` with:

```python
def _parser():
    parser = argparse.ArgumentParser(description="v113 1w horizon, fade and inverse-ETF funnel")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("collect-a", "collect-b", "collect-d", "holdout"):
        command = sub.add_parser(name)
        command.add_argument("--out", required=True)
        command.add_argument("--universe")
        command.add_argument("--tickers", help="comma-separated; Part D requires exactly SH,PSQ,RWM,DOG")
    sub.choices["collect-b"].add_argument("--strategy", required=True)
    sub.choices["collect-b"].add_argument("--direction", required=True, choices=("bullish", "bearish"))
    sub.choices["holdout"].add_argument("--evaluate", required=True)
    sub.choices["holdout"].add_argument("--preregistration", required=True)
    evaluate_parser = sub.add_parser("evaluate")
    evaluate_parser.add_argument("--rows", required=True)
    evaluate_parser.add_argument("--out", required=True)
    emit = sub.add_parser("emit-registry")
    emit.add_argument("--holdout-json", nargs="+", required=True)
    emit.add_argument("--registry", required=True)
    emit.add_argument("--run-date", required=True)
    return parser


COMMANDS = {"collect-a": _cmd_collect_a, "collect-b": _cmd_collect_b, "collect-d": _cmd_collect_d,
            "evaluate": _cmd_evaluate, "holdout": _cmd_holdout, "emit-registry": _cmd_emit}
```

- [ ] **Step 6: Run the tests and complexity**

Run: `python scripts/dev/testrun.py file tests/scripts/test_measure_v113.py`
Expected: all PASS.

Run: `python -m radon cc -s -n C scripts/backtest/measure_v113.py`
Expected: nothing listed.

- [ ] **Step 7: Commit**

```bash
git add scripts/backtest/measure_v113.py tests/scripts/test_measure_v113.py
git commit -m "feat(v113): measure_v113 holdout (one shot per cell, thin rule) and 1w registry rows; Part D writes none

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 8: Close Phase A — fast tier, then merge.**
  - Run: `python scripts/dev/testrun.py fast`. Expected: `0 failed`, `0 xfailed`. Fix forward from any failure (it is this phase's regression); re-run the narrow file, then `fast` once more.
  - Run: `python scripts/dev/testrun.py file tests/market/test_v113_horizon_witness.py`. Expected: PASS (it is `slow`, so `fast` skipped it).
  - Load `worktree-lifecycle`. Run `git log --oneline main -3` and, for each file this branch touched, `git log --oneline <merge-base>..main -- <file>`; if another session changed one, rebase this branch onto `main` first and re-run the narrow files it shares.
  - Merge `2026-09-28-v113-bearish-day-coverage` into `main` (no squash). Confirm `git log --oneline main | grep "(v113)"` shows the eleven Phase A commits. A conflict-free merge needs no further test run; a merge that resolved conflicts gets one `testrun.py fast`.
