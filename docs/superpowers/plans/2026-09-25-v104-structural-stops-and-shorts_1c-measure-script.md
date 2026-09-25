# v104 Part 1c — Measurement script (same worktree branch)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Global Constraints, Review Focus and Parallelisation live in `2026-09-25-v104-structural-stops-and-shorts_0-index.md` and bind every task here.

**Spec:** `docs/superpowers/specs/2026-09-25-v104-structural-stops-and-shorts-design.md` §5, §6

---

### Task V104-12: `measure_v104.py` — counts, collect, evaluate, holdout, registry

**Files:**
- Create: `scripts/backtest/measure_v104.py`
- Test: `tests/scripts/test_measure_v104.py`

**Interfaces:**
- Consumes:
  - `funnel.pooled`, `score_cell`, `stage1`, `stage2(..., fold_years=)`, `fixed_folds`, `fold_verdict`, `badge_verdict`, `assert_rows_before`, `cell_key`, `MIN_N_TRAIN`, `MIN_N_VALIDATION`, `BOOTSTRAP_SEED` (V104-6)
  - `earnings_context.attach` (V104-8); `SHORT_STRATEGIES` (V104-1)
  - Existing script helpers: `measure_fib_confluence.Progress`, `_load_frames`, `_write`, `require_ext_cache`; `measure_fib_v103.require_committed`; `measure_bearish_arms.apply_laggard_rule`; `run_backtest_range._build_asof_map`, `merge_registry`, `window_trades`
- Produces the CLI used by Part 2:
  - `count --mechanism B1|B2|B3 --out <json>`
  - `collect-a --strategy <name> --direction bullish|bearish --out <json>`
  - `collect-b --mechanism B1|B2|B3 --stage0 <json> --out <json>`
  - `evaluate --rows <collect json> --out <json>`
  - `holdout --evaluate <json> --preregistration <md> --out <json>`
  - `emit-registry --holdout-json <json...> --registry <path> --run-date YYYY-MM-DD`
  - Every frame command also takes `--tickers` and `--universe`.
- Module constants that Part 2 edits exactly once (V104-15): `HOLDOUT_END: str | None = None`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/scripts/test_measure_v104.py
"""v104 funnel logic -- no market data: synthetic rows and fake backtests."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "backtest"))
import measure_v104 as mv  # noqa: E402

from swingbot import config  # noqa: E402
from swingbot.core.market.entry_filters import DEFAULT_PARAMS  # noqa: E402
from swingbot.core.market.strategy_types import HORIZONS  # noqa: E402

FAST = dict(n_resamples=200, seed=42)


def _rows(years, per_year, win_share, *, direction="bullish", tickers=8):
    rows = []
    for year in years:
        wins = round(per_year * win_share)
        for i in range(per_year):
            win = i < wins
            rows.append({"ticker": f"T{i % tickers}", "horizon_key": "4w", "direction": direction,
                         "entry_date": f"{year}-06-01", "outcome": "win" if win else "loss",
                         "r_multiple": 1.0 if win else -1.0, "risk_pct": 3.0})
    return rows


YEARS = (2013, 2014, 2015, 2016)


def test_admitted_horizons_follow_the_live_gate():
    assert mv.admitted_horizons("VWAP", "bullish") == ("4w",)
    assert mv.admitted_horizons("MACD", "bullish") == ("3m", "4m", "7m", "8m", "9m")
    assert mv.admitted_horizons("Break & Retest", "bearish") == ("2m", "3m", "4m")
    assert mv.admitted_horizons("Fibonacci", "bullish") == tuple(HORIZONS)


def test_part_a_has_fifteen_cells_matching_the_live_gates():
    assert len(mv.PART_A) == 15 and len(set(mv.PART_A)) == 15
    for strategy, direction in mv.PART_A:
        assert direction in mv.admitted_directions(strategy)


def test_scope_and_params_restore(monkeypatch):
    monkeypatch.setattr(config, "STRUCTURAL_STOP_SCOPE", "", raising=False)
    with mv.scope("Fibonacci:bullish"):
        assert config.STRUCTURAL_STOP_SCOPE == "Fibonacci:bullish"
    assert config.STRUCTURAL_STOP_SCOPE == ""
    before = dict(DEFAULT_PARAMS["Bull Trap"])
    with mv.params("Bull Trap", {"k": 1, "earnings": "exit_before"}):
        assert DEFAULT_PARAMS["Bull Trap"] == {"k": 1, "earnings": "exit_before"}
    assert DEFAULT_PARAMS["Bull Trap"] == before


def test_evaluate_a_proceeds_only_when_the_in_arm_beats_the_baseline():
    arms = {"in": _rows(YEARS, 16, 0.625), "out": _rows(YEARS, 16, 0.5)}
    ok = mv.evaluate_a("Fibonacci", "bullish", arms, **FAST)
    assert ok["beats_baseline"] and ok["stage2"]["clears"] and ok["proceed_to_holdout"] and ok["tier"] == 1
    arms["out"] = _rows(YEARS, 16, 0.75)
    worse = mv.evaluate_a("Fibonacci", "bullish", arms, **FAST)
    assert not worse["beats_baseline"] and not worse["proceed_to_holdout"] and worse["tier"] is None


def test_cell_values_skip_the_earnings_axis_for_b3():
    assert mv.cell_values(mv.MECHANISMS["B1"], 2, "exit_before") == {"k": 2, "earnings": "exit_before"}
    assert mv.cell_values(mv.MECHANISMS["B3"], 0.08, "hold") == {"g": 0.08}


def test_stage0_closes_an_earnings_setting_below_thirty():
    counts = {mv.b_key(3, "hold"): {"total": 45}, mv.b_key(3, "exit_before"): {"total": 12}}
    assert mv.stage0_closures("B1", counts) == ["exit_before"]


def test_evaluate_b_picks_tier_then_expectancy_across_earnings(monkeypatch):
    def fake_stage1(by_value, direction, grid, **kw):
        exp = by_value["marker"]
        return {"winner": 2, "winner_tier": 2, "cells": {"2": {"stats": {"expectancy_r": exp}}}}
    monkeypatch.setattr(mv.funnel, "stage1", fake_stage1)
    monkeypatch.setattr(mv.funnel, "stage2", lambda *a, **k: {"verdict": {"clears": True}})
    # measure_v104 imported cell_key by name, so patch ITS binding (b_key uses it too).
    monkeypatch.setattr(mv, "cell_key", lambda v: "marker" if v == 1 else str(v))
    rows = {mv.b_key(v, e): (0.1 if e == "hold" else 0.3) for v in (1, 2, 3) for e in ("hold", "exit_before")}
    result = mv.evaluate_b("B1", rows, closed=(), **FAST)
    assert result["validation_cell"] == {"value": 2, "earnings": "exit_before", "tier": 2}


def test_verdict_seals_a_thin_holdout_with_n_only():
    sealed = mv.verdict(_rows((2026,), 10, 0.9), None, tier=1, **FAST)
    assert sealed == {"status": "sealed-thin", "n": 10}


def test_verdict_part_a_needs_the_baseline_clause():
    rows_in = _rows((2026,), 20, 0.6)
    passes = mv.verdict(rows_in, _rows((2026,), 20, 0.5), tier=1, **FAST)
    fails = mv.verdict(rows_in, _rows((2026,), 20, 0.8), tier=1, **FAST)
    assert passes["passes"] and passes["clauses"]["beats_baseline"]
    assert not fails["passes"] and not fails["clauses"]["beats_baseline"]


@pytest.fixture
def results(tmp_path, monkeypatch):
    monkeypatch.setattr(mv, "RESULTS", tmp_path)
    monkeypatch.setattr(mv, "HOLDOUT_END", "2026-09-24")
    return tmp_path


def _prior(results, name, status):
    (results / name).write_text(json.dumps({"status": status}), encoding="utf-8")


def test_holdout_first_shot_is_allowed(results):
    mv.check_shot_allowed("b-b1", results / "2026-09-30-v104-holdout-b-b1.json")


def test_holdout_refuses_a_spent_shot_under_any_date(results):
    _prior(results, "2026-09-01-v104-holdout-b-b1.json", "scored")
    with pytest.raises(SystemExit):
        mv.check_shot_allowed("b-b1", results / "2026-12-31-v104-holdout-b-b1.json")


def test_holdout_refuses_the_thin_retry_before_twelve_months(results):
    _prior(results, "2026-09-01-v104-holdout-b-b1.json", "sealed-thin")
    with pytest.raises(SystemExit):
        mv.check_shot_allowed("b-b1", results / "2026-10-01-v104-holdout-b-b1.json")


def test_holdout_allows_exactly_one_thin_retry_after_twelve_months(results, monkeypatch):
    _prior(results, "2026-09-01-v104-holdout-b-b1.json", "sealed-thin")
    monkeypatch.setattr(mv, "HOLDOUT_END", "2026-12-31")
    mv.check_shot_allowed("b-b1", results / "2027-01-05-v104-holdout-b-b1.json")
    _prior(results, "2027-01-05-v104-holdout-b-b1.json", "sealed-thin")
    with pytest.raises(SystemExit):
        mv.check_shot_allowed("b-b1", results / "2027-02-01-v104-holdout-b-b1.json")


def test_holdout_refuses_an_existing_output(results):
    out = results / "2026-09-30-v104-holdout-b-b1.json"
    out.write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit):
        mv.check_shot_allowed("b-b1", out)


def test_holdout_window_refuses_until_frozen(monkeypatch):
    monkeypatch.setattr(mv, "HOLDOUT_END", None)
    with pytest.raises(SystemExit):
        mv.holdout_window()


def test_trade_rows_filters_direction_window_and_applies_the_laggard_rule(monkeypatch):
    trade = lambda d, date: SimpleNamespace(direction=d, entry_date=date, outcome="win", r_multiple=1.0,
                                            entry=100.0, stop_loss=97.0)
    summary = SimpleNamespace(trades=[trade("bearish", "2015-01-05"), trade("bullish", "2015-01-06"),
                                      trade("bearish", "2026-02-01")])
    calls = []
    monkeypatch.setattr(mv, "window_trades", lambda s, a, b: [t for t in s.trades if a <= t.entry_date <= b])
    monkeypatch.setattr(mv, "apply_laggard_rule", lambda raw: calls.append(len(raw)) or raw)
    rows = mv.trade_rows("Bull Trap", {"AAA": None}, {}, "bearish", mv.TRAIN, ("2w",),
                         run_fn=lambda *a, **k: summary)
    assert [r["entry_date"] for r in rows] == ["2015-01-05"] and calls == [1]
    assert rows[0]["risk_pct"] == pytest.approx(3.0)


def test_emit_refuses_a_row_missing_an_admitted_direction(tmp_path):
    payload = {"status": "scored", "passes": True, "strategy": "Break & Retest", "direction": "bullish",
               "tier": 1, "rows": _rows((2026,), 20, 0.6)}
    path = tmp_path / "h.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    args = SimpleNamespace(holdout_json=[str(path)], registry=str(tmp_path / "reg.json"), run_date="2026-10-01")
    with pytest.raises(SystemExit):
        mv._cmd_emit(args)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_measure_v104.py`
Expected: FAIL at import (`measure_v104` is missing).

- [ ] **Step 3: Implement `scripts/backtest/measure_v104.py`**

```python
#!/usr/bin/env python3
"""v104 measurement: Part A structural stops (15 cells) and Part B shorts (B1-B3).

Stages (spec §5): count (B Stage 0) -> collect -> evaluate (Stages 1-2 on
TRAIN) -> holdout (Stage 3: one shot per candidate, thin-holdout rule) ->
emit-registry. Reads the EXTENDED cache only:
  BACKTEST_CACHE_DIR=data/backtest_cache_ext python scripts/backtest/measure_v104.py <command> ...
"""
from __future__ import annotations

import argparse
import collections
import contextlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(Path(__file__).resolve().parent)]

import funnel  # noqa: E402
from funnel import BOOTSTRAP_SEED, MIN_N_TRAIN, MIN_N_VALIDATION, cell_key  # noqa: E402
from measure_bearish_arms import apply_laggard_rule  # noqa: E402
from measure_fib_confluence import Progress, _load_frames, _write, require_ext_cache  # noqa: E402
from measure_fib_v103 import require_committed  # noqa: E402
from run_backtest_range import _build_asof_map, merge_registry, window_trades  # noqa: E402
from swingbot import config  # noqa: E402
from swingbot.core.backtesting.acceptance import BOOTSTRAP_RESAMPLES  # noqa: E402
from swingbot.core.backtesting.backtest import run_backtest  # noqa: E402
from swingbot.core.market import earnings_context  # noqa: E402
from swingbot.core.market.entry_filters import DEFAULT_PARAMS, entries_for, gate_override  # noqa: E402
from swingbot.core.market.strategy_types import HORIZONS, SHORT_STRATEGIES, STRATEGY_GATES  # noqa: E402

# --- pre-registered constants (spec §5.1) ---
TRAIN = ("2010-01-01", "2025-12-31")
HOLDOUT_START = "2026-01-01"
HOLDOUT_END: str | None = None     # frozen ONCE by V104-15 and committed before any Stage 3 run
THIN_REOPEN = "2026-12-31"         # spec §5.4
FOLD_YEARS = tuple(range(2013, 2026))
ALL_HZ = tuple(HORIZONS)
RESULTS = ROOT / "docs" / "superpowers" / "results"

PART_A = (
    ("Fibonacci", "bullish"), ("RSI", "bullish"), ("MA Ribbon", "bullish"), ("VWAP", "bullish"),
    ("Support/Resistance", "bullish"), ("MACD", "bullish"), ("Volume Profile", "bullish"),
    ("Break & Retest", "bullish"), ("Break & Retest", "bearish"),
    ("EMA Crossover", "bullish"), ("EMA Crossover", "bearish"),
    ("RSI Divergence", "bullish"), ("RSI Divergence", "bearish"),
    ("Elliott Wave", "bullish"), ("Elliott Wave", "bearish"),
)
BULL_TRAP, VOL_BREAKDOWN, GAP_DRIFT = SHORT_STRATEGIES
MECHANISMS = {
    "B1": SimpleNamespace(strategy=BULL_TRAP, knob="k", grid=(1, 2, 3), loosest=3,
                          earnings=("hold", "exit_before")),
    "B2": SimpleNamespace(strategy=VOL_BREAKDOWN, knob="m", grid=(1.0, 1.2, 1.4), loosest=1.0,
                          earnings=("hold", "exit_before")),
    "B3": SimpleNamespace(strategy=GAP_DRIFT, knob="g", grid=(0.05, 0.08, 0.12), loosest=0.05,
                          earnings=("hold",)),
}


# --- small helpers ------------------------------------------------------------

def slug(text: str) -> str:
    return text.lower().replace(" & ", "-and-").replace("/", "-").replace(" ", "-")


def admitted_directions(strategy: str) -> tuple:
    directions = (STRATEGY_GATES.get(strategy) or {}).get("directions")
    return tuple(directions) if directions is not None else ("bullish", "bearish")


def admitted_horizons(strategy: str, direction: str) -> tuple:
    gates = STRATEGY_GATES.get(strategy) or {}
    by_direction = gates.get("horizons_by_direction") or {}
    horizons = by_direction.get(direction, gates.get("horizons"))
    return tuple(horizons) if horizons else ALL_HZ


@contextlib.contextmanager
def scope(raw: str):
    saved = getattr(config, "STRUCTURAL_STOP_SCOPE", "")
    config.STRUCTURAL_STOP_SCOPE = raw
    try:
        yield
    finally:
        config.STRUCTURAL_STOP_SCOPE = saved


@contextlib.contextmanager
def params(strategy: str, values: dict):
    current = DEFAULT_PARAMS[strategy]
    saved = dict(current)
    current.update(values)
    try:
        yield
    finally:
        current.clear()
        current.update(saved)


def cell_values(spec, value, earnings) -> dict:
    values = {spec.knob: value}
    if spec.strategy != GAP_DRIFT:
        values["earnings"] = earnings
    return values


def b_key(value, earnings) -> str:
    return f"{cell_key(value)}|{earnings}"


def _row(ticker, horizon_key, trade) -> dict:
    return {"ticker": ticker, "horizon_key": horizon_key, "direction": trade.direction,
            "entry_date": trade.entry_date, "outcome": trade.outcome, "r_multiple": trade.r_multiple,
            "risk_pct": round(abs(trade.entry - trade.stop_loss) / trade.entry * 100, 4)}


def trade_rows(strategy, frames, asof_map, direction, window, horizons, *,
               progress=None, label="", run_fn=None) -> list:
    """Every decided trade of `strategy` x `direction` inside `window`, v2 exits,
    scale-out, TP2 levels, frictions on -- the live arithmetic. Bearish
    populations pass the live laggard rule (backtest == live)."""
    run_fn = run_fn or run_backtest
    raw = []
    for ticker, frame in sorted(frames.items()):
        if progress is not None:
            progress.tick(f"{label} {ticker}")
        for horizon in horizons:
            summary = run_fn(ticker, frame, strategy, horizon, one_at_a_time=True, exit_model="v2",
                             scale_out=True, tp2_mode="levels", frictions=True, asof=asof_map.get(ticker))
            raw.extend({"ticker": ticker, "horizon_key": horizon, "trade": trade}
                       for trade in window_trades(summary, *window) if trade.direction == direction)
    if direction == "bearish":
        raw = apply_laggard_rule(raw)
    return [_row(item["ticker"], item["horizon_key"], item["trade"]) for item in raw]


def _frames(args):
    require_ext_cache()
    frames = _load_frames(args.universe, args.tickers)
    frames = {ticker: earnings_context.attach(frame, ticker) for ticker, frame in frames.items()}
    return frames, _build_asof_map(list(frames), frames, args.universe)


# --- Part A -------------------------------------------------------------------

def part_a_arms(strategy, direction, frames, asof_map, window, progress=None):
    horizons = admitted_horizons(strategy, direction)
    arms = {}
    for arm, raw in (("out", ""), ("in", f"{strategy}:{direction}")):
        with scope(raw):
            arms[arm] = trade_rows(strategy, frames, asof_map, direction, window, horizons,
                                   progress=progress, label=f"A {strategy} {direction} {arm}")
    return arms, horizons


def evaluate_a(strategy, direction, arms, *, n_resamples=BOOTSTRAP_RESAMPLES, seed=BOOTSTRAP_SEED):
    baseline = funnel.pooled(arms["out"])
    scored = funnel.score_cell(arms["in"], MIN_N_TRAIN, n_resamples=n_resamples, seed=seed)
    in_exp, out_exp = scored["stats"]["expectancy_r"], baseline["expectancy_r"]
    beats = in_exp is not None and out_exp is not None and in_exp > out_exp
    folds = funnel.fixed_folds(arms["in"], FOLD_YEARS)
    stage2 = funnel.fold_verdict(folds)
    proceed = scored["tier"] is not None and beats and stage2["clears"]
    return {"part": "A", "strategy": strategy, "direction": direction, "baseline": baseline,
            "in_scope": scored, "beats_baseline": beats, "folds": folds, "stage2": stage2,
            "proceed_to_holdout": proceed, "tier": scored["tier"] if proceed else None}


# --- Part B -------------------------------------------------------------------

def _count(strategy, frames) -> dict:
    by_year, by_horizon = collections.Counter(), collections.Counter()
    for frame in frames.values():
        for horizon in ALL_HZ:
            _, bearish = entries_for(strategy, frame, horizon)
            dates = frame.index[bearish.to_numpy(dtype=bool)].strftime("%Y-%m-%d")
            years = [date[:4] for date in dates if TRAIN[0] <= date <= TRAIN[1]]
            by_year.update(years)
            by_horizon[horizon] += len(years)
    return {"total": sum(by_year.values()), "by_year": dict(sorted(by_year.items())),
            "by_horizon": {horizon: by_horizon[horizon] for horizon in ALL_HZ}}


def count_b(mech, frames) -> dict:
    spec, counts = MECHANISMS[mech], {}
    with gate_override(spec.strategy, {"directions": ("bearish",)}):
        for earnings in spec.earnings:
            for value in spec.grid:
                with params(spec.strategy, cell_values(spec, value, earnings)):
                    counts[b_key(value, earnings)] = _count(spec.strategy, frames)
    return counts


def stage0_closures(mech, counts) -> list:
    spec = MECHANISMS[mech]
    return [e for e in spec.earnings if counts[b_key(spec.loosest, e)]["total"] < MIN_N_TRAIN]


def collect_b(mech, frames, asof_map, window, earnings_settings, *, values=None, progress=None) -> dict:
    spec, rows = MECHANISMS[mech], {}
    with gate_override(spec.strategy, {"directions": ("bearish",)}):
        for earnings in earnings_settings:
            for value in (values or spec.grid):
                with params(spec.strategy, cell_values(spec, value, earnings)):
                    rows[b_key(value, earnings)] = trade_rows(
                        spec.strategy, frames, asof_map, "bearish", window, ALL_HZ,
                        progress=progress, label=f"{mech} {b_key(value, earnings)}")
    return rows


def _earnings_result(spec, rows_by_cell, earnings, n_resamples, seed):
    by_value = {cell_key(v): rows_by_cell[b_key(v, earnings)] for v in spec.grid}
    stage1 = funnel.stage1(by_value, "bearish", spec.grid, n_resamples=n_resamples, seed=seed)
    stage2 = funnel.stage2(by_value, "bearish", spec.grid, fold_years=FOLD_YEARS)
    proceed = stage1["winner"] is not None and stage2["verdict"]["clears"]
    return {"stage1": stage1, "stage2": stage2, "proceed": proceed}


def evaluate_b(mech, rows_by_cell, closed=(), *, n_resamples=BOOTSTRAP_RESAMPLES, seed=BOOTSTRAP_SEED):
    """Per earnings setting: Stage 1 plateau + Stage 2 folds. Across settings the
    proceeding winner with the better tier, then the higher ExpR, is the cell."""
    spec, per_setting, best = MECHANISMS[mech], {}, None
    for earnings in spec.earnings:
        if earnings in closed:
            per_setting[earnings] = {"closed_at": "stage0"}
            continue
        result = _earnings_result(spec, rows_by_cell, earnings, n_resamples, seed)
        per_setting[earnings] = result
        if not result["proceed"]:
            continue
        winner = result["stage1"]["winner"]
        exp = result["stage1"]["cells"][cell_key(winner)]["stats"]["expectancy_r"]
        rank = (result["stage1"]["winner_tier"], -exp)
        if best is None or rank < best[0]:
            best = (rank, {"value": winner, "earnings": earnings, "tier": result["stage1"]["winner_tier"]})
    cell = best[1] if best else None
    return {"part": "B", "mechanism": mech, "strategy": spec.strategy, "direction": "bearish",
            "by_earnings": per_setting, "proceed_to_holdout": cell is not None,
            "validation_cell": cell, "tier": cell["tier"] if cell else None}


# --- Stage 3: holdout -----------------------------------------------------------

def holdout_window() -> tuple:
    if HOLDOUT_END is None:
        raise SystemExit("HOLDOUT_END is not frozen -- V104-15 sets and commits it before any Stage 3 run")
    return HOLDOUT_START, HOLDOUT_END


def candidate_slug(evaluated: dict) -> str:
    if evaluated["part"] == "A":
        return f"a-{slug(evaluated['strategy'])}-{evaluated['direction']}"
    return f"b-{evaluated['mechanism'].lower()}"


def check_shot_allowed(candidate: str, out_path) -> None:
    """One shot per candidate under ANY date; a single sealed-thin shot may be
    retried once, and only when the holdout reaches 12 months (spec §5.4)."""
    if Path(out_path).exists():
        raise SystemExit(f"holdout output already exists: {out_path}")
    prior = sorted(Path(RESULTS).glob(f"*-v104-holdout-{candidate}.json"))
    if not prior:
        return
    statuses = [json.loads(path.read_text(encoding="utf-8")).get("status") for path in prior]
    if statuses != ["sealed-thin"]:
        raise SystemExit(f"holdout shot for {candidate} is spent ({prior[-1].name})")
    if (HOLDOUT_END or "") < THIN_REOPEN:
        raise SystemExit(f"{candidate} is sealed-thin; its one retry waits for HOLDOUT_END >= {THIN_REOPEN}")


def verdict(rows_in, rows_out, tier, *, n_resamples=BOOTSTRAP_RESAMPLES, seed=BOOTSTRAP_SEED) -> dict:
    """Stage 3: N < 15 writes N only (sealed-thin, shot unspent); otherwise the
    assigned tier's clauses, plus beats_baseline for Part A."""
    n = funnel.pooled(rows_in)["n"]
    if n < MIN_N_VALIDATION:
        return {"status": "sealed-thin", "n": n}
    scored = funnel.score_cell(rows_in, MIN_N_VALIDATION, n_resamples=n_resamples, seed=seed)
    clauses = dict(scored["tier1" if tier == 1 else "tier2"]["clauses"])
    baseline = None
    if rows_out is not None:
        baseline = funnel.pooled(rows_out)
        in_exp, out_exp = scored["stats"]["expectancy_r"], baseline["expectancy_r"]
        clauses["beats_baseline"] = out_exp is None or (in_exp is not None and in_exp >= out_exp)
    return {"status": "scored", "tier": tier, "stats": scored["stats"], "lower_bound": scored["lower_bound"],
            "baseline": baseline, "clauses": clauses, "passes": all(clauses.values())}


def _holdout_rows(evaluated, frames, asof_map, window):
    if evaluated["part"] == "A":
        arms, _ = part_a_arms(evaluated["strategy"], evaluated["direction"], frames, asof_map, window)
        return arms["in"], arms["out"]
    cell = evaluated["validation_cell"]
    rows = collect_b(evaluated["mechanism"], frames, asof_map, window, (cell["earnings"],), values=(cell["value"],))
    return rows[b_key(cell["value"], cell["earnings"])], None


# --- commands -------------------------------------------------------------------

def _cmd_count(args):
    frames, _ = _frames(args)
    counts = count_b(args.mechanism, frames)
    _write(args.out, {"mechanism": args.mechanism, "universe_n": len(frames), "counts": counts,
                      "closed_at_stage0": stage0_closures(args.mechanism, counts)})


def _cmd_collect_a(args):
    if (args.strategy, args.direction) not in PART_A:
        raise SystemExit(f"{args.strategy}:{args.direction} is not a pre-registered Part A cell")
    frames, asof_map = _frames(args)
    progress = Progress(2 * len(frames))
    arms, horizons = part_a_arms(args.strategy, args.direction, frames, asof_map, TRAIN, progress)
    for rows in arms.values():
        funnel.assert_rows_before(rows, TRAIN[1])
    _write(args.out, {"part": "A", "strategy": args.strategy, "direction": args.direction,
                      "horizons": list(horizons), "window": list(TRAIN), "universe_n": len(frames), "arms": arms})


def _cmd_collect_b(args):
    closed = json.loads(Path(args.stage0).read_text(encoding="utf-8"))["closed_at_stage0"]
    spec = MECHANISMS[args.mechanism]
    open_settings = tuple(e for e in spec.earnings if e not in closed)
    if not open_settings:
        raise SystemExit(f"{args.mechanism}: every earnings setting closed at Stage 0")
    frames, asof_map = _frames(args)
    progress = Progress(len(open_settings) * len(spec.grid) * len(frames))
    rows = collect_b(args.mechanism, frames, asof_map, TRAIN, open_settings, progress=progress)
    for cell_rows in rows.values():
        funnel.assert_rows_before(cell_rows, TRAIN[1])
    _write(args.out, {"part": "B", "mechanism": args.mechanism, "window": list(TRAIN),
                      "universe_n": len(frames), "closed_at_stage0": closed, "rows_by_cell": rows})


def _cmd_evaluate(args):
    collected = json.loads(Path(args.rows).read_text(encoding="utf-8"))
    if collected["part"] == "A":
        result = evaluate_a(collected["strategy"], collected["direction"], collected["arms"])
    else:
        result = evaluate_b(collected["mechanism"], collected["rows_by_cell"],
                            closed=tuple(collected["closed_at_stage0"]))
    _write(args.out, result)


def _cmd_holdout(args):
    window = holdout_window()
    require_committed(args.preregistration)
    require_committed(args.evaluate)
    evaluated = json.loads(Path(args.evaluate).read_text(encoding="utf-8"))
    if not evaluated.get("proceed_to_holdout"):
        raise SystemExit(f"{candidate_slug(evaluated)} did not proceed to the holdout")
    candidate = candidate_slug(evaluated)
    check_shot_allowed(candidate, args.out)
    frames, asof_map = _frames(args)
    rows_in, rows_out = _holdout_rows(evaluated, frames, asof_map, window)
    result = verdict(rows_in, rows_out, evaluated["tier"])
    payload = {"candidate": candidate, "part": evaluated["part"], "strategy": evaluated["strategy"],
               "direction": evaluated["direction"], "window": list(window), "evaluate": str(args.evaluate),
               "preregistration": str(args.preregistration), **result}
    if result["status"] == "scored":
        payload["rows"] = rows_in
    _write(args.out, payload)


def _cmd_emit(args):
    payloads = [json.loads(Path(path).read_text(encoding="utf-8")) for path in args.holdout_json]
    if not all(p.get("status") == "scored" and p.get("passes") for p in payloads):
        raise SystemExit("refusing to emit a failing or sealed holdout")
    strategies = {p["strategy"] for p in payloads}
    if len(strategies) != 1:
        raise SystemExit("one strategy per registry row")
    strategy = strategies.pop()
    directions = {p["direction"] for p in payloads}
    required = set(admitted_directions(strategy))
    if directions != required:
        raise SystemExit(f"{strategy}: a registry row needs every admitted direction {sorted(required)}, "
                         f"have {sorted(directions)} (plan index amendment 2)")
    rows = [row for p in payloads for row in p["rows"]]
    stats = funnel.pooled(rows)
    badge = funnel.badge_verdict(stats, MIN_N_VALIDATION)["clears"]
    status = "VALIDATED" if {p["tier"] for p in payloads} == {1} and badge else "WEAK"
    merge_registry(args.registry, [{
        "source": "strategy", "strategy": strategy, "horizon": None, "status": status, "n": stats["n"],
        "win_rate": None if stats["win_rate"] is None else round(stats["win_rate"], 1),
        "expectancy_r": None if stats["expectancy_r"] is None else round(stats["expectancy_r"], 3),
        "window": f"{HOLDOUT_START}..{payloads[0]['window'][1]}", "run_date": args.run_date}])


def _parser():
    parser = argparse.ArgumentParser(description="v104 structural stops and shorts funnel")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("count", "collect-a", "collect-b", "holdout"):
        command = sub.add_parser(name)
        command.add_argument("--out", required=True)
        command.add_argument("--universe")
        command.add_argument("--tickers", help="comma-separated; the pre-registered universe list")
    for name in ("count", "collect-b"):
        sub.choices[name].add_argument("--mechanism", required=True, choices=tuple(MECHANISMS))
    sub.choices["collect-b"].add_argument("--stage0", required=True)
    sub.choices["collect-a"].add_argument("--strategy", required=True)
    sub.choices["collect-a"].add_argument("--direction", required=True, choices=("bullish", "bearish"))
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


COMMANDS = {"count": _cmd_count, "collect-a": _cmd_collect_a, "collect-b": _cmd_collect_b,
            "evaluate": _cmd_evaluate, "holdout": _cmd_holdout, "emit-registry": _cmd_emit}


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    COMMANDS[args.cmd](args)
    print(f"v104 {args.cmd} done", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scripts/test_measure_v104.py`
Expected: PASS (18).

Check two helper assumptions the tests rely on:
- `grep -n "def pooled_stats" -A 20 swingbot/core/backtesting/arm_rule.py`: it must read `outcome` and `r_multiple` and report `n`, `win_rate`, `expectancy_r` and `scratch_timeout_share`.
- `grep -n "def window_trades" -A 8 scripts/backtest/run_backtest_range.py`: it must filter `summary.trades` by `entry_date`.

If either differs, adapt the **test fixtures**, never the script's contract, and note it in the commit body.

- [ ] **Step 5: Smoke run on two tickers (real data, seconds, not a measurement)**

The worktree has no extended cache. Copy it from the main tree once:

```powershell
Copy-Item -Recurse "E:\Documents\Private\Projects\Discord-Bot\data\backtest_cache_ext" data\backtest_cache_ext
```

Then run:

```bash
BACKTEST_CACHE_DIR=data/backtest_cache_ext python scripts/backtest/measure_v104.py count --mechanism B1 --tickers AAPL,MSFT --out <scratchpad>/smoke_b1.json
```

Expected: `v104 count done`, with `universe_n` 2 in the JSON. This checks the wiring end to end: frames, earnings context, the gate override and entries. **It is not Stage 0:** the numbers are not recorded anywhere. Delete the file.

- [ ] **Step 6: Complexity and commit**

Run: `python -m radon cc -s -n C scripts/backtest/measure_v104.py`. Expected: no output.

```bash
git add scripts/backtest/measure_v104.py tests/scripts/test_measure_v104.py
git commit -m "feat(v104): measure_v104 -- Part A two-arm and Part B grid funnels, holdout with the one-shot and thin rules

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

**End of the code parts.** Merge the branch to `main` per the `worktree-lifecycle` skill: `git fetch`, check `git log main` for other sessions' commits, fast-forward or merge. Part 2 then runs on `main`.
