# Pullback volume dry-up gate -- part 2: funnel tooling and measurement

> Part of `2026-10-02-v122-pullback-volume-dryup-gate_0-index.md`. The header, global constraints, file map, review focus and `## Parallelisation` live in that index; read its Global constraints with every task. Steps use `- [ ]` for tracking.

**Spec:** `docs/superpowers/specs/implemented/2026-10-02-v122-pullback-volume-dryup-gate-design.md`. Read its two frozen amendments, "Clause 6 reading" and "Clause 5 instrument", before any task here.

# Phase 3 — Funnel tooling, pre-registration, measurement

### Task V122-8: Stage 1 judge in `validate_component.py`

**Files:**
- Create: `swingbot/core/backtesting/arms/selection.py`
- Modify: `swingbot/core/backtesting/arms/windows.py` (`FUNNEL_TO_PRODUCER_STAGE["selection"] = "selection"`)
- Modify: `scripts/backtest/validate_component.py`: add `--stage selection`, `--grid-arms` and `--mde-refused`; `--arms` becomes stage-conditional; the reachability output also prints the population split
- Create: `tests/backtesting/arms/test_selection.py`, `tests/backtesting/test_validate_component_selection.py`

**Interfaces:**
- Consumes: `acceptance.evaluate(..., stage="walkforward")` (permutation is SKIPPED at that stage), `population_split`, `delta_standardised_win_rate`, `delta_expectancy_r`, `expectancy_r`, `ClauseResult`, `backtest_wf.plateau_report`, `provenance.check_stamp`.
- Produces (`swingbot.core.backtesting.arms.selection`):
  - `CellEval(value, eligible, delta_win_rate_pp, expectancy_r, failed, disclosure)` and `Selection(cells, selected, plateau, verdict)`.
  - `evaluate_cell(value, baseline, component, *, resolvable, n_resamples, seed, mechanism=None) -> CellEval`. When given, `mechanism` (a `ClauseResult`) replaces the evaluated mechanism clause. V122-9 passes the v122 baseline reading through this argument.
  - `with_clause(result: AcceptanceResult, clause: ClauseResult) -> AcceptanceResult`: swaps the same-named clause and recomputes the verdict.
  - `select_cell(cells, param_name) -> Selection` and `removed_disclosure(baseline, component) -> dict`.
  - Constants: `SELECTED="selected"`, `NO_ELIGIBLE="no-eligible-cell"`, `SPIKE="spike"`, `ELIGIBILITY_CLAUSES=("profit_floor", "geometry", "volume", "mechanism")`.
- The spec's rule, verbatim: a cell is eligible when clauses 2–4 and 6 **PASS** (SKIPPED is not a pass) and its Stage 0 MDE is resolvable. The chosen `d` needs an eligible grid neighbour **and** `plateau_report()` `is_plateau`. Among those, take the largest ΔWR; on a tie, the larger value.

- [ ] **Step 1: Write the failing tests**

```python
# tests/backtesting/arms/test_selection.py
import pandas as pd

from swingbot.core.backtesting.acceptance import ArmTrade, ClauseResult, evaluate
from swingbot.core.backtesting.arms import selection as sel

DATES = [d.date().isoformat() for d in pd.bdate_range("2019-01-01", periods=100)]


def _baseline():
    """25 tickers x 100 trades: 40 wins (+2R), 60 losses (-1R)."""
    return [ArmTrade(f"T{t}", "MACD", "3m", DATES[i], "win" if i < 40 else "loss",
                     2.0 if i < 40 else -1.0, 2.0, "strategy", "bullish" if i % 2 else "bearish")
            for t in range(25) for i in range(100)]


def _remove(baseline, *, losses=0, wins=0):
    """Drop the first `losses` losses and `wins` wins of every ticker."""
    out, dropped = [], {}
    for trade in baseline:
        limit = losses if trade.outcome == "loss" else wins
        seen = dropped.get((trade.ticker, trade.outcome), 0)
        if seen < limit:
            dropped[(trade.ticker, trade.outcome)] = seen + 1
            continue
        out.append(trade)
    return out


def _cell(value, mechanism=None, **removal):
    base = _baseline()
    return sel.evaluate_cell(value, base, _remove(base, **removal), resolvable=True,
                             n_resamples=200, seed=42, mechanism=mechanism)


def test_largest_dwr_on_a_plateau_is_selected():
    cells = [_cell(0.60, losses=3), _cell(0.75, losses=2), _cell(0.90, losses=1)]
    assert all(cell.eligible for cell in cells)
    result = sel.select_cell(cells, "PULLBACK_DRYUP_MAX_RATIO")
    assert (result.verdict, result.selected) == (sel.SELECTED, 0.60)
    assert result.plateau["is_plateau"] is True


def test_tie_goes_to_the_larger_value():
    cells = [_cell(0.60, losses=1), _cell(0.75, losses=2), _cell(0.90, losses=2)]
    assert sel.select_cell(cells, "d").selected == 0.90


def test_removing_winners_fails_the_mechanism_clause():
    cell = _cell(0.60, wins=2)
    assert not cell.eligible and "mechanism" in cell.failed


def test_a_supplied_mechanism_clause_replaces_the_evaluated_one():
    failing = ClauseResult("mechanism", "FAIL", "injected", None, None)
    assert "mechanism" in _cell(0.60, mechanism=failing, losses=2).failed
    passing = ClauseResult("mechanism", "PASS", "injected", None, None)
    assert "mechanism" not in _cell(0.60, mechanism=passing, wins=2).failed


def test_with_clause_recomputes_the_verdict():
    base = _baseline()
    result = evaluate(base, _remove(base, losses=2), stage="walkforward", n_resamples=200)
    swapped = sel.with_clause(result, ClauseResult("mechanism", "FAIL", "x", None, None))
    assert swapped.clause("mechanism").verdict == "FAIL" and swapped.verdict == "FAIL"
    assert [c.name for c in swapped.clauses] == [c.name for c in result.clauses]


def test_an_isolated_eligible_cell_is_a_spike():
    cells = [_cell(0.60, losses=2), _cell(0.75, wins=2), _cell(0.90, wins=1)]
    assert sel.select_cell(cells, "d").verdict == sel.SPIKE


def test_no_eligible_cell():
    assert sel.select_cell([_cell(v, wins=2) for v in (0.60, 0.75, 0.90)], "d").verdict == sel.NO_ELIGIBLE


def test_a_stage0_refusal_makes_a_cell_ineligible():
    base = _baseline()
    cell = sel.evaluate_cell(0.60, base, _remove(base, losses=2), resolvable=False,
                             n_resamples=200, seed=42)
    assert not cell.eligible and "mde" in cell.failed


def test_disclosure_counts_direction_horizon_and_replacements():
    base = _baseline()
    component = [t for t in base if not (t.outcome == "loss" and t.direction == "bullish"
                                         and t.ticker == "T0")]
    component.append(ArmTrade("T0", "MACD", "3m", "2019-09-02", "win", 2.0, 2.0, "strategy", "bullish"))
    info = sel.removed_disclosure(base, component)
    assert (info["removed"], info["added"], info["is_subset"]) == (30, 1, False)
    assert info["one_direction"] == "bullish" and info["top2_horizon_share"] == 1.0
    assert set(info["per_direction"]) == {"bullish", "bearish"}
```

```python
# tests/backtesting/test_validate_component_selection.py
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))
import validate_component as vc  # noqa: E402
from swingbot.core.backtesting.arms.provenance import build_stamp  # noqa: E402
from swingbot.core.backtesting.arms.windows import ALL_HORIZONS  # noqa: E402
from tests.backtesting.test_validate_component_stamps import UNIVERSE, rows  # noqa: E402

WINDOWS = {"pilot": ("2018-06-01", "2020-12-31"), "selection": ("2018-06-01", "2022-12-31"),
           "validation": ("2024-01-01", "2025-12-31")}


@pytest.fixture(autouse=True)
def universe(monkeypatch):
    monkeypatch.setattr(vc, "_full_universe", lambda: UNIVERSE)


def write_arms(tmp_path, name, stage, baseline, component, knobs=None):
    stamp = build_stamp(stage=stage, signal_window=WINDOWS[stage], universe=UNIVERSE,
                        horizons=ALL_HORIZONS, engines=("strategy",),
                        knob_delta=knobs or {"PULLBACK_DRYUP_MAX_RATIO": 0.6},
                        engine_hash_baseline="h", engine_hash_component="h", changed_outcomes=1)
    path = tmp_path / f"{name}.json"
    path.write_text(json.dumps({"provenance": stamp, "baseline": baseline, "component": component}))
    return path


def test_selection_stage_judges_a_stamped_grid(tmp_path, capsys):
    argv = ["--stage", "selection", "--title", "d", "--window", "w", "--resamples", "200"]
    for value, drop in ((0.60, 9), (0.75, 9), (0.90, 10)):
        argv += ["--grid-arms", f"{value}={write_arms(tmp_path, str(value), 'selection', *rows(drop_from=drop))}"]
    code = vc.main(argv)
    out = capsys.readouterr().out
    assert "d=0.60" in out and "d=0.90" in out
    assert any(token in out for token in ("selected", "spike", "no-eligible-cell")) and code in (0, 1)


def test_selection_refuses_a_wrong_stage_stamp(tmp_path, capsys):
    path = write_arms(tmp_path, "p", "pilot", *rows(drop_from=9))
    assert vc.main(["--stage", "selection", "--grid-arms", f"0.6={path}", "--title", "d", "--window", "w"]) == 1
    assert "refused:stage-mismatch" in capsys.readouterr().err


def test_reachability_prints_the_population_split(tmp_path, capsys):
    path = write_arms(tmp_path, "pilot", "pilot", *rows(drop_from=8))
    vc.main(["--stage", "reachability", "--arms", str(path), "--title", "t", "--window", "pilot"])
    assert "split removed=" in capsys.readouterr().out


def test_other_stages_still_need_arms():
    with pytest.raises(SystemExit):
        vc.main(["--stage", "mde", "--title", "t", "--window", "w"])
```

In `rows()` (verified, `tests/backtesting/test_validate_component_stamps.py`), `drop_from=9` removes each ticker's last trade, which is a loss (`win = index < 4`). `drop_from=10` removes nothing. The CLI test checks the wiring and the output shape; the selection rule itself is pinned in `test_selection.py`.

- [ ] **Step 2: Run them to confirm they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/arms/test_selection.py` then `... file tests/backtesting/test_validate_component_selection.py`
Expected: FAIL with `ModuleNotFoundError: swingbot.core.backtesting.arms.selection`, and `argparse` rejecting `selection`.

- [ ] **Step 3: Implement `selection.py`**

```python
"""Stage 1 grid selection for a pre-registered filter knob (v122).

Eligible = clauses 2-4 and 6 PASS on fold-train (a SKIPPED clause is not a pass)
and the Stage 0 MDE resolved. The pick needs an eligible grid neighbour AND a
plateau_report() plateau; among those, the largest dWR wins, and on a tie the
larger value. A caller may supply its own mechanism clause (v122's frozen
baseline reading); it replaces the evaluated one.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace

from swingbot.core.backtesting.acceptance import (delta_expectancy_r, delta_standardised_win_rate,
                                                  evaluate, expectancy_r, population_split)
from swingbot.core.backtesting.backtest_wf import plateau_report

ELIGIBILITY_CLAUSES = ("profit_floor", "geometry", "volume", "mechanism")
SELECTED, NO_ELIGIBLE, SPIKE = "selected", "no-eligible-cell", "spike"
ONE_DIRECTION_SHARE = 0.80


@dataclass(frozen=True)
class CellEval:
    value: float
    eligible: bool
    delta_win_rate_pp: float | None
    expectancy_r: float | None
    failed: tuple
    disclosure: dict


@dataclass(frozen=True)
class Selection:
    cells: tuple
    selected: float | None
    plateau: dict | None
    verdict: str


def with_clause(result, clause):
    """Swap the same-named clause into an AcceptanceResult and recompute the verdict."""
    clauses = tuple(clause if c.name == clause.name else c for c in result.clauses)
    verdict = "FAIL" if any(c.verdict == "FAIL" for c in clauses) else "PASS"
    return replace(result, clauses=clauses, verdict=verdict)


def _share(part, whole):
    return part / whole if whole else None


def _dominant(counts: Counter, n: int):
    if not n:
        return None
    direction, count = counts.most_common(1)[0]
    return direction if count / n > ONE_DIRECTION_SHARE else None


def _per_direction(baseline, component) -> dict:
    out = {}
    for direction in sorted({t.direction for t in baseline if t.direction}):
        b = [t for t in baseline if t.direction == direction]
        c = [t for t in component if t.direction == direction]
        out[direction] = {"n_baseline": len(b), "n_component": len(c),
                          "delta_win_rate_pp": delta_standardised_win_rate(b, c),
                          "delta_expectancy_r": delta_expectancy_r(b, c)}
    return out


def removed_disclosure(baseline, component) -> dict:
    """The spec's disclosure: per-direction results, the top-2 horizon share of the
    removed trades, a >80%-one-direction flag, and the replacement (added) count."""
    split = population_split(baseline, component)
    removed = split["removed"]
    directions = Counter(t.direction for t in removed)
    horizons = Counter(t.horizon_key for t in removed)
    return {"removed": len(removed), "added": len(split["added"]),
            "changed": len(split["changed"]), "is_subset": split["is_subset"],
            "removed_by_direction": dict(directions),
            "top2_horizon_share": _share(sum(c for _, c in horizons.most_common(2)), len(removed)),
            "one_direction": _dominant(directions, len(removed)),
            "per_direction": _per_direction(baseline, component)}


def evaluate_cell(value, baseline, component, *, resolvable, n_resamples, seed,
                  mechanism=None) -> CellEval:
    result = evaluate(baseline, component, stage="walkforward",
                      n_resamples=n_resamples, seed=seed)
    if mechanism is not None:
        result = with_clause(result, mechanism)
    failed = tuple(name for name in ELIGIBILITY_CLAUSES if result.clause(name).verdict != "PASS")
    if not resolvable:
        failed += ("mde",)
    return CellEval(value, not failed, delta_standardised_win_rate(baseline, component),
                    expectancy_r(component), failed, removed_disclosure(baseline, component))


def _neighbour_eligible(cells, i) -> bool:
    return any(cells[j].eligible for j in (i - 1, i + 1) if 0 <= j < len(cells))


def _rank(cell):
    dwr = cell.delta_win_rate_pp
    return (float("-inf") if dwr is None else dwr, cell.value)


def select_cell(cells, param_name) -> Selection:
    cells = tuple(sorted(cells, key=lambda cell: cell.value))
    if not any(cell.eligible for cell in cells):
        return Selection(cells, None, None, NO_ELIGIBLE)
    grid = [cell.value for cell in cells]
    expectancies = [float("nan") if c.expectancy_r is None else c.expectancy_r for c in cells]
    plateaus = {i: plateau_report(param_name, grid, expectancies, grid[i])
                for i, cell in enumerate(cells) if cell.eligible and _neighbour_eligible(cells, i)}
    candidates = [i for i, report in plateaus.items() if report["is_plateau"]]
    if not candidates:
        return Selection(cells, None, None, SPIKE)
    best = max(candidates, key=lambda i: _rank(cells[i]))
    return Selection(cells, grid[best], plateaus[best], SELECTED)
```

- [ ] **Step 4: Wire `validate_component.py` and `windows.py`**

In `windows.py`, add `"selection": "selection",` to `FUNNEL_TO_PRODUCER_STAGE`. In `validate_component.py`, add below the existing imports:

```python
import dataclasses  # noqa: E402
from swingbot.core.backtesting.acceptance import population_split  # noqa: E402
from swingbot.core.backtesting.arms.selection import SELECTED, evaluate_cell, select_cell  # noqa: E402


def _parse_grid(texts):
    cells = []
    for text in texts or []:
        value, separator, path = text.partition("=")
        if not separator:
            raise ValueError(f"--grid-arms must be VALUE=PATH, got {text!r}")
        cells.append((float(value), Path(path)))
    return cells


def _cell_mechanism(args, path, value, baseline):
    """Hook for V122-9's --dryup-mechanism; until then no clause is supplied."""
    return None


def _selection_cells(args):
    refused, cells = set(args.mde_refused or []), []
    for value, path in _parse_grid(args.grid_arms):
        token = check_stamp(json.loads(path.read_text()), funnel_stage="selection",
                            full_universe=_full_universe())
        if token:
            print(f"{token} -- {path}. Budget intact.", file=sys.stderr)
            return None
        baseline, component = load_arms(path)
        cells.append(evaluate_cell(value, baseline, component, resolvable=value not in refused,
                                   n_resamples=args.resamples, seed=args.seed,
                                   mechanism=_cell_mechanism(args, path, value, baseline)))
    return cells


def stage_selection(args):
    try:
        cells = _selection_cells(args)
    except ValueError as exc:
        print(f"refused:bad-grid -- {exc}", file=sys.stderr); return 1
    if not cells:
        print("refused:no-grid -- --stage selection needs stamped --grid-arms VALUE=PATH.", file=sys.stderr); return 1
    selection = select_cell(cells, args.title)
    for cell in selection.cells:
        print(f"d={cell.value:.2f} eligible={cell.eligible} dWR={cell.delta_win_rate_pp} "
              f"ExpR={cell.expectancy_r} failed={list(cell.failed)} disclosure={json.dumps(cell.disclosure)}")
    print(f"{selection.verdict} -- selected {selection.selected}")
    if args.out_json:
        Path(args.out_json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out_json).write_text(json.dumps(dataclasses.asdict(selection), indent=1), encoding="utf-8")
    return 0 if selection.verdict == SELECTED else 1
```

In `stage_reachability`, directly after the line that prints `changed outcomes`, add:

```python
    split = population_split(baseline, component)
    print(f"split removed={len(split['removed'])} added={len(split['added'])} "
          f"changed={len(split['changed'])} is_subset={split['is_subset']}")
```

Replace `main` with the version below. It keeps every existing argument, makes `--arms` stage-conditional, and adds three arguments:

```python
STAGE_FNS = {"reachability": stage_reachability, "mde": stage_mde,
             "walkforward": stage_walkforward, "validation": stage_validation}


def _parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", required=True, choices=("reachability", "mde", "selection", "walkforward", "validation"))
    parser.add_argument("--arms", type=Path, default=None)
    parser.add_argument("--grid-arms", action="append", default=None)
    parser.add_argument("--mde-refused", action="append", type=float, default=None)
    parser.add_argument("--title", required=True); parser.add_argument("--window", required=True)
    parser.add_argument("--permutation-p", type=float, default=None); parser.add_argument("--train-effect-pp", type=float, default=0.0); parser.add_argument("--train-effect-r", type=float, default=0.0); parser.add_argument("--observed-days", type=int, default=None); parser.add_argument("--target-days", type=int, default=730); parser.add_argument("--resamples", type=int, default=BOOTSTRAP_RESAMPLES); parser.add_argument("--seed", type=int, default=42); parser.add_argument("--notes", default=None); parser.add_argument("--out-md", default=None); parser.add_argument("--out-json", default=None); parser.add_argument("--bespoke-instrument", default=None); parser.add_argument("--mde-method", choices=("paired", "unpaired"), default="paired"); parser.add_argument("--gate", choices=("win_rate", "harvest"), default="win_rate")
    return parser


def main(argv=None):
    parser = _parser()
    args = parser.parse_args(argv)
    if args.stage == "selection":
        return stage_selection(args)
    if args.arms is None:
        parser.error("--arms is required for this stage")
    refused = _stamp_gate(args)
    if refused is not None:
        return refused
    return STAGE_FNS[args.stage](args)
```

**Cross-plan note:** v123 also edits `validate_component.py`, to add harvest walk-forward and validation gates. Before editing, run `git log --oneline -3 -- scripts/backtest/validate_component.py`. If v123 has landed, rebase this change onto its `main`/parser shape; keep its arguments and add these three.

- [ ] **Step 5: Run the narrow tests and radon**

Run: `python scripts/dev/testrun.py file tests/backtesting/arms/test_selection.py`, `... file tests/backtesting/test_validate_component_selection.py`, `... file tests/backtesting/test_validate_component_stamps.py`, `... file tests/backtesting/arms/test_windows.py`, then `python -m radon cc -s -n C swingbot/core/backtesting/arms/selection.py scripts/backtest/validate_component.py`
Expected: all PASS, and radon prints no new block at C or above.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/backtesting/arms/selection.py swingbot/core/backtesting/arms/windows.py scripts/backtest/validate_component.py tests/backtesting/arms/test_selection.py tests/backtesting/test_validate_component_selection.py
git commit -m "feat(v122): validate_component --stage selection (eligible neighbour + plateau) and removal disclosure"
```

### Task V122-9: The frozen clause-6 reading, the `None` share, and `--dryup-mechanism`

**Files:**
- Create: `swingbot/core/backtesting/arms/dryup_clauses.py`
- Modify: `scripts/backtest/validate_component.py`: add a `--dryup-mechanism` flag, replace the `_cell_mechanism` hook with a real one, and apply the reading in `_run_gate`, used by `--stage validation`
- Create: `tests/backtesting/arms/test_dryup_clauses.py`, `tests/backtesting/test_validate_component_dryup.py`

**Interfaces:**
- Consumes: `gates.ratio_exceeds` and `gates.strategy_in_dryup_scope` (V122-2), `structure.pullback_vol_ratio` (v121), `selection.with_clause` and `evaluate_cell(mechanism=)` (V122-8), `acceptance.win_rate`/`expectancy_r`/`ClauseResult`, and `measure_arms.load_frame` (verified).
- Produces (`swingbot.core.backtesting.arms.dryup_clauses`):
  - `in_scope(trade, scope) -> bool`.
  - `scoped_ratios(trades, frame_for, scope, cache=None) -> dict[key, float | None]`. Each ratio is computed on `frame.loc[:trade.entry_date]`, the completed as-of slice both replay engines hand the gate, because `entry_date` is the signal bar's date in both.
  - `none_share(ratios, scope) -> dict` and `flagged_keys(ratios, max_ratio) -> set`.
  - `baseline_mechanism(baseline, flagged, scope) -> ClauseResult` named `"mechanism"`; removed and retained are both restricted to `in_scope(t, scope)` trades.
  - `knob_context(blob) -> tuple[str, float] | None`, which reads scope and `d` from a stamp's `knob_delta`.
- Spec amendment, verbatim: the mechanism clause is scored on the **baseline** arm. Trades the predicate flags at `d` are the removed population; in-scope baseline trades it does not flag are the retained population (out-of-scope trades are in neither group). It passes iff removed WR < retained WR **and** removed ExpR ≤ 0. Replacement trades count fully in clauses 1–5, and their count is disclosed.

- [ ] **Step 1: Write the failing tests**

```python
# tests/backtesting/arms/test_dryup_clauses.py
"""v122 frozen clause-6 reading: mechanism on the BASELINE arm, flagged vs unflagged."""
from swingbot.core.backtesting.acceptance import ArmTrade
from swingbot.core.backtesting.arms import dryup_clauses as dc
from tests.edge.pullback_frames import IMPULSE_VOLUME, pullback_frame


def _t(i, outcome, strategy="Fibonacci", source="strategy"):
    return ArmTrade("T", strategy, "4w", f"2019-02-{i + 1:02d}", outcome,
                    2.0 if outcome == "win" else -1.0, 2.0, source, "bullish")


def test_flagged_losers_pass_flagged_winners_fail():
    baseline = [_t(i, "win" if i < 4 else "loss") for i in range(10)]
    losers = {t.key for t in baseline[8:]}
    winners = {t.key for t in baseline[:2]}
    assert dc.baseline_mechanism(baseline, losers, "strategy").verdict == "PASS"
    assert dc.baseline_mechanism(baseline, winners, "strategy").verdict == "FAIL"
    assert dc.baseline_mechanism(baseline, set(), "strategy").verdict == "FAIL"     # nothing flagged


def test_out_of_scope_trades_are_in_neither_group():
    # Flagged in-scope trades are 1 win + 1 loss (WR 50%). In-scope unflagged are
    # all losses, so the in-scope reading FAILS (removed WR 50% > retained 0%).
    # If out-of-scope confluence winners leaked into "retained" they would lift
    # retained WR above 50% and flip it to a (wrong) PASS.
    flagged_pair = [_t(0, "win"), _t(1, "loss")]
    unflagged = [_t(i, "loss") for i in range(2, 6)]
    confluence = [_t(i, "win", strategy="confluence", source="confluence") for i in range(6, 26)]
    baseline = flagged_pair + unflagged + confluence
    flagged = {t.key for t in flagged_pair}
    assert dc.baseline_mechanism(baseline, flagged, "strategy").verdict == "FAIL"


def test_flags_use_the_gate_comparison_strictly():
    ratios = {"a": 0.75, "b": 0.7500001, "c": None, "d": 0.2}
    assert dc.flagged_keys(ratios, 0.75) == {"b"}
    assert dc.flagged_keys(ratios, 0.0) == set()


def test_scoped_ratios_respect_scope_and_cache():
    frame = pullback_frame(0.5 * IMPULSE_VOLUME)
    last = frame.index[-1].date().isoformat()
    flat = frame.index[40].date().isoformat()
    trades = [ArmTrade("T", "Fibonacci", "4w", last, "win", 2.0, 2.0, "strategy", "bullish"),
              ArmTrade("T", "Fibonacci", "4w", flat, "loss", -1.0, 2.0, "strategy", "bullish"),
              ArmTrade("T", "MACD", "4w", flat, "loss", -1.0, 2.0, "strategy", "bullish"),
              ArmTrade("T", "Fibonacci", "4w", flat, "loss", -1.0, 2.0, "confluence", "bullish")]
    loads, cache = [], {}

    def frame_for(ticker):
        loads.append(ticker)
        return frame
    ratios = dc.scoped_ratios(trades, frame_for, "strategy", cache=cache)
    assert list(ratios.values()) == [0.5, None]
    assert dc.none_share(ratios, "strategy") == {"scope": "strategy", "n": 2, "none": 1, "share": 0.5}
    dc.scoped_ratios(trades, frame_for, "strategy", cache=cache)
    assert loads == ["T"]                                  # second call served from the cache
    assert len(dc.scoped_ratios(trades, frame_for, "confluence")) == 1


def test_knob_context_reads_the_stamp():
    blob = {"provenance": {"knob_delta": {"PULLBACK_DRYUP_SCOPE": "confluence",
                                          "PULLBACK_DRYUP_MAX_RATIO": 0.9}}}
    assert dc.knob_context(blob) == ("confluence", 0.9)
    assert dc.knob_context({"provenance": {"knob_delta": {"MIN_REWARD_PCT": 4.0}}}) is None


def test_empty_scope_has_no_share():
    assert dc.none_share({}, "strategy")["share"] is None
```

```python
# tests/backtesting/test_validate_component_dryup.py
"""--dryup-mechanism: the v122 baseline reading replaces acceptance.py's SKIPPED
mechanism clause when replacements make the component arm a non-subset."""
import json

import pytest

from tests.backtesting.test_validate_component_selection import vc, write_arms  # noqa: F401
from tests.backtesting.test_validate_component_stamps import UNIVERSE, rows

KNOBS = {"PULLBACK_DRYUP_SCOPE": "strategy", "PULLBACK_DRYUP_MAX_RATIO": 0.75}


@pytest.fixture(autouse=True)
def universe(monkeypatch):
    monkeypatch.setattr(vc, "_full_universe", lambda: UNIVERSE)


@pytest.fixture
def non_subset_arms():
    baseline, component = rows(drop_from=8)              # indices 8, 9 (losses) removed per ticker
    component = component + [dict(component[0], entry_date="2019-03-20")]   # one replacement trade
    flagged_dates = {"2019-03-09", "2019-03-10"}
    return baseline, component, flagged_dates


def _ratios(flagged_dates):
    return lambda baseline, scope: {t.key: (0.95 if t.entry_date in flagged_dates else 0.30)
                                    for t in baseline}


def _mechanism(path):
    blob = json.loads(path.read_text())
    return next(c for c in blob["clauses"] if c["name"] == "mechanism")["verdict"]


def test_validation_uses_the_baseline_reading(tmp_path, monkeypatch, non_subset_arms):
    baseline, component, flagged = non_subset_arms
    monkeypatch.setattr(vc, "_baseline_ratios", _ratios(flagged))
    arms = write_arms(tmp_path, "v", "validation", baseline, component, KNOBS)
    plain, dry = tmp_path / "plain.json", tmp_path / "dry.json"
    common = ["--stage", "validation", "--arms", str(arms), "--title", "t", "--window", "w",
              "--permutation-p", "0.01", "--resamples", "200"]
    vc.main(common + ["--out-json", str(plain)])
    vc.main(common + ["--dryup-mechanism", "--out-json", str(dry)])
    assert _mechanism(plain) == "SKIPPED" and _mechanism(dry) == "PASS"


def test_dryup_mechanism_refuses_an_arm_without_dryup_knobs(tmp_path, capsys, non_subset_arms):
    baseline, component, _ = non_subset_arms
    arms = write_arms(tmp_path, "v", "validation", baseline, component, {"MIN_REWARD_PCT": 4.0})
    assert vc.main(["--stage", "validation", "--arms", str(arms), "--title", "t", "--window", "w",
                    "--permutation-p", "0.01", "--dryup-mechanism"]) == 1
    assert "refused:not-a-dryup-arm" in capsys.readouterr().err
```

- [ ] **Step 2: Run them to confirm they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/arms/test_dryup_clauses.py` then `... file tests/backtesting/test_validate_component_dryup.py`
Expected: FAIL with `ModuleNotFoundError`, and an unknown `--dryup-mechanism` argument.

- [ ] **Step 3: Implement `dryup_clauses.py`**

```python
"""v122 frozen clause-6 reading and disclosures (spec amendment, 2026-10-02).

A rejected entry frees the one-position slot (strategy) or the 5-bar cooldown
(confluence), so the component arm is not a subset of baseline and acceptance.py
reports mechanism SKIPPED. For v122 the mechanism clause is scored on the BASELINE
arm: trades the predicate flags at d ("removed") against baseline trades it does not
flag ("retained"). Replacement trades stay in the component arm for clauses 1-5.
"""
from __future__ import annotations

from swingbot.core.backtesting.acceptance import ClauseResult, expectancy_r, win_rate
from swingbot.core.edge.gates import ratio_exceeds, strategy_in_dryup_scope
from swingbot.core.market.structure import pullback_vol_ratio

SCOPES = ("strategy", "confluence")


def in_scope(trade, scope: str) -> bool:
    if trade.source != scope:
        return False
    return scope == "confluence" or strategy_in_dryup_scope(trade.strategy)


def scoped_ratios(trades, frame_for, scope: str, cache: dict | None = None) -> dict:
    """pullback_vol_ratio per in-scope trade, on the completed as-of slice."""
    cache = {} if cache is None else cache
    frames: dict = {}
    out: dict = {}
    for trade in trades:
        if not in_scope(trade, scope):
            continue
        if trade.key not in cache:
            if trade.ticker not in frames:
                frames[trade.ticker] = frame_for(trade.ticker)
            # Slice ends at the SIGNAL bar the live gate saw. Verify against the
            # ArmTrade schema: if entry_date is the next-session fill date, use the
            # signal/decision date field instead, or the flag reads one bar the gate
            # never had (lookahead vs the live predicate).
            window = frames[trade.ticker].loc[:trade.entry_date]
            cache[trade.key] = pullback_vol_ratio(window, trade.direction)
        out[trade.key] = cache[trade.key]
    return out


def none_share(ratios: dict, scope: str) -> dict:
    nones = sum(ratio is None for ratio in ratios.values())
    return {"scope": scope, "n": len(ratios), "none": nones,
            "share": nones / len(ratios) if ratios else None}


def flagged_keys(ratios: dict, max_ratio: float) -> set:
    return {key for key, ratio in ratios.items() if ratio_exceeds(ratio, max_ratio)}


def baseline_mechanism(baseline, flagged: set, scope: str) -> ClauseResult:
    # "retained" = IN-SCOPE baseline trades the predicate does not flag; trades the
    # gate can never touch (other source, strategy outside the frozen list) are in
    # neither group, so they cannot dilute the comparison.
    scoped = [t for t in baseline if in_scope(t, scope)]
    removed = [t for t in scoped if t.key in flagged]
    retained = [t for t in scoped if t.key not in flagged]
    r_wr, k_wr, r_exp = win_rate(removed), win_rate(retained), expectancy_r(removed)
    if r_wr is None or k_wr is None or r_exp is None:
        return ClauseResult("mechanism", "FAIL",
                            "v122 baseline reading: flagged or unflagged baseline population "
                            "has no decided trades", None, None)
    ok = r_wr < k_wr and r_exp <= 0.0
    return ClauseResult("mechanism", "PASS" if ok else "FAIL",
                        f"v122 baseline reading: flagged WR {r_wr:.2f}% (n={len(removed)}) vs "
                        f"unflagged {k_wr:.2f}%, flagged ExpR {r_exp:+.4f}R (must be <= 0)",
                        r_wr, k_wr)


def knob_context(blob: dict):
    delta = (blob.get("provenance") or {}).get("knob_delta") or {}
    scope, max_ratio = delta.get("PULLBACK_DRYUP_SCOPE"), delta.get("PULLBACK_DRYUP_MAX_RATIO")
    if scope not in SCOPES or not max_ratio:
        return None
    return scope, float(max_ratio)
```

- [ ] **Step 4: Wire `--dryup-mechanism` into `validate_component.py`**

Add `parser.add_argument("--dryup-mechanism", action="store_true")` to `_parser()`. Add the import and the helpers, and replace V122-8's `_cell_mechanism` hook:

```python
from swingbot.core.backtesting.arms import dryup_clauses as dry  # noqa: E402
from swingbot.core.backtesting.arms.selection import with_clause  # noqa: E402

_RATIO_CACHE: dict = {}


class NotADryupArm(ValueError):
    pass


def _frame_for(ticker):
    from measure_arms import load_frame
    return load_frame(ticker)


def _baseline_ratios(baseline, scope):
    return dry.scoped_ratios(baseline, _frame_for, scope, cache=_RATIO_CACHE)


def _dryup_mechanism_for(path, baseline):
    """The frozen v122 clause-6 reading for one stamped arm file, plus its None share."""
    context = dry.knob_context(json.loads(Path(path).read_text()))
    if context is None:
        raise NotADryupArm(f"{path} carries no PULLBACK_DRYUP_SCOPE/PULLBACK_DRYUP_MAX_RATIO delta")
    scope, max_ratio = context
    ratios = _baseline_ratios(baseline, scope)
    print(f"dry-up none share: {json.dumps(dry.none_share(ratios, scope))}")
    return dry.baseline_mechanism(baseline, dry.flagged_keys(ratios, max_ratio), scope)


def _cell_mechanism(args, path, value, baseline):
    return _dryup_mechanism_for(path, baseline) if args.dryup_mechanism else None
```

In `stage_selection`, extend the existing `except ValueError` so a `NotADryupArm` prints `refused:not-a-dryup-arm -- <message>` instead of `refused:bad-grid`:

```python
    except NotADryupArm as exc:
        print(f"refused:not-a-dryup-arm -- {exc}", file=sys.stderr); return 1
    except ValueError as exc:
        print(f"refused:bad-grid -- {exc}", file=sys.stderr); return 1
```

Replace `_run_gate` with:

```python
def _run_gate(args, stage):
    baseline, component = load_arms(args.arms); _write_skeleton(args, stage)
    result = evaluate(baseline, component, stage=stage, permutation_p=args.permutation_p, n_resamples=args.resamples, seed=args.seed)
    if args.dryup_mechanism:
        try:
            result = with_clause(result, _dryup_mechanism_for(args.arms, baseline))
        except NotADryupArm as exc:
            print(f"refused:not-a-dryup-arm -- {exc}", file=sys.stderr); return 1
    markdown = render_markdown(result, title=args.title, window=args.window, notes=_notes(args)); print(markdown)
    if args.out_md: Path(args.out_md).parent.mkdir(parents=True, exist_ok=True); Path(args.out_md).write_text(markdown, encoding="utf-8")
    if args.out_json: Path(args.out_json).parent.mkdir(parents=True, exist_ok=True); Path(args.out_json).write_text(json.dumps(render_json(result), indent=1), encoding="utf-8")
    return 0 if result.verdict == "PASS" else 1
```

- [ ] **Step 5: Run the narrow tests and radon**

Run: `python scripts/dev/testrun.py file tests/backtesting/arms/test_dryup_clauses.py`, `... file tests/backtesting/test_validate_component_dryup.py`, `... file tests/backtesting/test_validate_component_selection.py`, `... file tests/backtesting/test_validate_component_stamps.py`, then `python -m radon cc -s -n C swingbot/core/backtesting/arms/dryup_clauses.py scripts/backtest/validate_component.py`
Expected: all PASS, and no block at C or above.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/backtesting/arms/dryup_clauses.py scripts/backtest/validate_component.py tests/backtesting/arms/test_dryup_clauses.py tests/backtesting/test_validate_component_dryup.py
git commit -m "feat(v122): frozen clause-6 baseline reading and None share behind --dryup-mechanism"
```

### Task V122-10: Extend `permutation_test.py` to stamped arm pairs (the clause-5 instrument)

**Files:**
- Modify: `scripts/backtest/permutation_test.py`
- Create: `tests/backtesting/test_permutation_test_arms.py`
- Create: `tests/fixtures/v122/permutation_fold_witness.json` (generated on the unchanged script)

**Interfaces:**
- Consumes: the existing `permuted_expectancies(run_fn, n_perm=200, seed=42)`, `p_value(real, permuted)` and `_fold_run_fn(overrides)` (verified). Also `acceptance.ArmTrade`, `population_split` and `delta_standardised_win_rate`.
- Produces:
  - `main(argv=None) -> int`. The `__main__` block calls `sys.exit(main())`.
  - A new `--arms PATH` mode that prints JSON with `observed_delta_win_rate_pp`, `p_value`, `n`, `n_valid`, `seed`, `shift_range`, `removed`, `added`, `changed` and `verdict`.
  - `arm_pair_permutation(baseline, component, n_perm=200, seed=42) -> dict`.
  - The existing `--component-json` fold path prints byte-identical JSON.
- Instrument, per the partner's decision in the spec: it extends this script and is not a new instrument. For each ticker, baseline trades in date order carry a "removed" label (absent from the component arm). Each permutation circularly shifts those labels by one seeded integer in [20, 200), the same range the existing fold path uses for entry shifts. That keeps each ticker's removal count and run structure while severing the link between label and trade. Each null arm is `baseline − shifted-removed + the arm's replacement trades`, so replacements sit on the same footing in the observed arm and every null arm. The p-value is the share of null ΔWR ≥ the observed ΔWR. Defaults are n = 200 and seed = 42. The mode covers confluence and strategy rows alike, because it reads only the arm rows.

- [ ] **Step 1: Write the witness test and capture it on the unchanged script**

```python
# tests/backtesting/test_permutation_test_arms.py
"""v122 extension of scripts/backtest/permutation_test.py: the fold path's output is
unchanged (witness), and the new --arms mode reports a seeded p-value on dWR."""
import json
import runpy
import sys
from pathlib import Path

import numpy as np
import pytest

from swingbot.core.backtesting import backtest_wf
from swingbot.core.backtesting.acceptance import ArmTrade
from swingbot.core.backtesting.arms.provenance import build_stamp

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = ROOT / "scripts" / "backtest" / "permutation_test.py"
WITNESS = ROOT / "tests" / "fixtures" / "v122" / "permutation_fold_witness.json"
FOLD_ARGV = ["permutation_test.py", "--component-json", '{"X": 1}', "--n", "50"]


def fake_run_folds(overrides):
    from swingbot.core.backtesting import backtest as bt
    shift = bt.ENTRY_SHIFT
    return {"folds": [{"component": {"expectancy_r": 0.10 if shift == 0 else 0.001 * shift}},
                      {"component": {"expectancy_r": None}}]}


def run_script(argv) -> str:
    """Run the script as __main__ and return its stdout. A SystemExit(0) is accepted
    because only the post-change script raises it."""
    import contextlib
    import io
    buffer = io.StringIO()
    saved = sys.argv
    sys.argv = list(argv)
    try:
        with contextlib.redirect_stdout(buffer):
            try:
                runpy.run_path(str(SCRIPT), run_name="__main__")
            except SystemExit as exc:
                assert exc.code in (0, None), exc.code
    finally:
        sys.argv = saved
    return buffer.getvalue()


def test_fold_path_output_is_unchanged(monkeypatch):
    monkeypatch.setattr(backtest_wf, "run_folds", fake_run_folds)
    assert json.loads(run_script(FOLD_ARGV)) == json.loads(WITNESS.read_text(encoding="utf-8"))
```

Capture the witness **before touching the script**, after confirming `git diff --stat -- scripts/backtest/permutation_test.py` prints nothing:

```bash
python -c "import json; from unittest import mock; from swingbot.core.backtesting import backtest_wf; from tests.backtesting import test_permutation_test_arms as t; t.WITNESS.parent.mkdir(parents=True, exist_ok=True); p = mock.patch.object(backtest_wf, 'run_folds', t.fake_run_folds); p.start(); out = t.run_script(t.FOLD_ARGV); p.stop(); t.WITNESS.write_text(json.dumps(json.loads(out), indent=1), encoding='utf-8')"
python scripts/dev/testrun.py file tests/backtesting/test_permutation_test_arms.py
```
Expected: PASS on the unchanged script. Commit the witness alone:

```bash
git add tests/backtesting/test_permutation_test_arms.py tests/fixtures/v122/permutation_fold_witness.json
git commit -m "test(v122): permutation_test.py fold-path witness captured before the extension"
```

- [ ] **Step 2: Behaviour-preserving refactor into `main(argv)`**

Replace the `if __name__ == "__main__":` block with the following. The fold path is unchanged; `--arms` dispatch arrives in Step 4.

```python
def _parser():
    p = argparse.ArgumentParser()
    p.add_argument("--component-json", default="{}")
    p.add_argument("--n", type=int, default=200)
    return p


def _fold_main(args) -> int:
    run = _fold_run_fn(json.loads(args.component_json))
    real = run(0)
    permuted = permuted_expectancies(run, n_perm=args.n)
    pv = p_value(real, permuted)
    print(json.dumps({"real_expectancy": real, "p_value": pv,
                      "verdict": "REAL" if pv <= 0.05 else "INDISTINGUISHABLE FROM LUCK"},
                     indent=1))
    return 0


def main(argv=None) -> int:
    return _fold_main(_parser().parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
```

Run: `python scripts/dev/testrun.py file tests/backtesting/test_permutation_test_arms.py`
Expected: PASS, the witness unchanged. Commit:

```bash
git add scripts/backtest/permutation_test.py
git commit -m "refactor(v122): permutation_test.py main(argv), fold path byte-identical"
```

- [ ] **Step 3: Write the failing `--arms` tests** (append to the same test file)

```python
def _arm_pair(remove_outcome):
    """25 tickers x 40 trades with an aperiodic win pattern; the component drops every
    `remove_outcome` trade in the second half and admits one replacement per ticker."""
    baseline, component = [], []
    for t in range(25):
        wins = np.random.default_rng(t).random(40) < 0.4
        for i in range(40):
            outcome = "win" if wins[i] else "loss"
            trade = ArmTrade(f"T{t}", "Fibonacci", "4w", f"2024-{1 + i // 28:02d}-{1 + i % 28:02d}",
                             outcome, 2.0 if wins[i] else -1.0, 2.0, "strategy", "bullish")
            baseline.append(trade)
            if not (i >= 20 and outcome == remove_outcome):
                component.append(trade)
        component.append(ArmTrade(f"T{t}", "Fibonacci", "4w", "2024-03-20", "win", 2.0, 2.0,
                                  "confluence", "bullish"))
    return baseline, component


def _write(tmp_path, baseline, component, stamped=True):
    from dataclasses import asdict
    blob = {"baseline": [asdict(t) for t in baseline], "component": [asdict(t) for t in component]}
    if stamped:
        blob["provenance"] = build_stamp(stage="validation", signal_window=("2024-01-01", "2025-12-31"),
                                         universe=["T0"], horizons=("4w",), engines=("strategy",),
                                         knob_delta={}, engine_hash_baseline="h",
                                         engine_hash_component="h", changed_outcomes=1)
    path = tmp_path / "arms.json"
    path.write_text(json.dumps(blob))
    return path


def _load_script():
    return runpy.run_path(str(SCRIPT))       # module namespace without running __main__


def test_removing_losers_is_distinguishable_from_luck():
    ns = _load_script()
    out = ns["arm_pair_permutation"](*_arm_pair("loss"), n_perm=200, seed=42)
    assert out["observed_delta_win_rate_pp"] > 0 and out["p_value"] < 0.05
    assert (out["n"], out["seed"], out["added"]) == (200, 42, 25)


def test_removing_winners_is_not():
    ns = _load_script()
    assert ns["arm_pair_permutation"](*_arm_pair("win"), n_perm=200, seed=42)["p_value"] > 0.05


def test_seeded_and_reproducible():
    ns = _load_script()
    pair = _arm_pair("loss")
    assert ns["arm_pair_permutation"](*pair) == ns["arm_pair_permutation"](*pair)


def test_cli_arms_mode(tmp_path):
    out = json.loads(run_script(["permutation_test.py", "--arms", str(_write(tmp_path, *_arm_pair("loss")))]))
    assert out["verdict"] == "REAL" and out["n"] == 200


def test_cli_refuses_unstamped_arms(tmp_path, capsys):
    ns = _load_script()
    assert ns["main"](["--arms", str(_write(tmp_path, *_arm_pair("loss"), stamped=False))]) == 1
    assert "refused:unstamped" in capsys.readouterr().err
```

Run: `python scripts/dev/testrun.py file tests/backtesting/test_permutation_test_arms.py`
Expected: the new tests FAIL with `KeyError: 'arm_pair_permutation'`, and the witness still passes.

- [ ] **Step 4: Implement the `--arms` mode**

Add above `_parser` in `permutation_test.py`:

```python
SHIFT_RANGE = (20, 200)


def _sort_key(trade):
    return (trade.entry_date, trade.strategy, trade.horizon_key, trade.source or "", trade.direction or "")


def _labelled_by_ticker(baseline, removed_keys) -> list:
    groups: dict = {}
    for trade in sorted(baseline, key=lambda t: (t.ticker, _sort_key(t))):
        groups.setdefault(trade.ticker, []).append(trade)
    return [(trades, np.array([t.key in removed_keys for t in trades])) for trades in groups.values()]


def _null_component(groups, added, shift) -> list:
    kept = []
    for trades, labels in groups:
        rolled = np.roll(labels, shift % len(labels))
        kept.extend(trade for trade, gone in zip(trades, rolled) if not gone)
    return kept + list(added)


def arm_pair_permutation(baseline, component, n_perm: int = 200, seed: int = 42) -> dict:
    """p-value on standardised dWR for a stamped arm pair (v122 clause-5 instrument)."""
    from swingbot.core.backtesting.acceptance import delta_standardised_win_rate, population_split
    split = population_split(baseline, component)
    groups = _labelled_by_ticker(baseline, {t.key for t in split["removed"]})
    observed = delta_standardised_win_rate(baseline, component)
    shifts = np.random.default_rng(seed).integers(*SHIFT_RANGE, size=n_perm)
    null = [delta_standardised_win_rate(baseline, _null_component(groups, split["added"], int(s)))
            for s in shifts]
    valid = [value for value in null if value is not None]
    p = None if observed is None or not valid else float(np.mean([v >= observed for v in valid]))
    return {"observed_delta_win_rate_pp": observed, "p_value": p, "n": int(n_perm),
            "n_valid": len(valid), "seed": seed, "shift_range": list(SHIFT_RANGE),
            "removed": len(split["removed"]), "added": len(split["added"]),
            "changed": len(split["changed"])}


def _arms_main(args) -> int:
    from swingbot.core.backtesting.acceptance import ArmTrade
    blob = json.loads(open(args.arms, encoding="utf-8").read())
    if not blob.get("provenance"):
        print("refused:unstamped -- --arms needs a measure_arms.py stamped file.", file=sys.stderr)
        return 1
    baseline = [ArmTrade(**row) for row in blob["baseline"]]
    component = [ArmTrade(**row) for row in blob["component"]]
    out = arm_pair_permutation(baseline, component, n_perm=args.n, seed=args.seed)
    out["verdict"] = ("REAL" if out["p_value"] is not None and out["p_value"] < 0.05
                      else "INDISTINGUISHABLE FROM LUCK")
    print(json.dumps(out, indent=1))
    return 0
```

Extend `_parser()` with `p.add_argument("--arms", default=None)` and `p.add_argument("--seed", type=int, default=42)`. Change `main`:

```python
def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    return _arms_main(args) if args.arms else _fold_main(args)
```

The fold path keeps calling `permuted_expectancies(run, n_perm=args.n)` with its own default seed (42), so its output does not move. Update the module docstring's `Run:` line to show both modes.

- [ ] **Step 5: Run the narrow tests and radon**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_permutation_test_arms.py` then `python -m radon cc -s -n C scripts/backtest/permutation_test.py`
Expected: all PASS, the witness included, and radon prints nothing.

- [ ] **Step 6: Commit**

```bash
git add scripts/backtest/permutation_test.py tests/backtesting/test_permutation_test_arms.py
git commit -m "feat(v122): permutation_test.py --arms -- seeded dWR p for stamped confluence/strategy arm pairs"
```

### Task V122-11: Pre-registration record, committed before any outcome is read

**Files:**
- Create: `docs/superpowers/results/2026-10-02-v122-preregistration.md` (the date prefix is the commit date)

**Interfaces:**
- Consumes: every code task merged into this branch (V122-1..10), and a clean `git status -- swingbot/ scripts/backtest/`.
- Produces: the frozen rule that V122-12 and V122-13 execute and quote. It is committed before any arm file exists.

- [ ] **Step 1: Invoke `backtest-gate`, then write the record**

```markdown
# v122 pre-registration — pullback volume dry-up gate

**Committed before any v122 outcome is read and before any VALIDATION arm exists.** Spec: `docs/superpowers/specs/implemented/2026-10-02-v122-pullback-volume-dryup-gate-design.md` (including its two frozen amendments). Plan: `docs/superpowers/plans/implemented/2026-10-02-v122-pullback-volume-dryup-gate_0-index.md` (parts `_1`, `_2`).

## Claim
Removing pullback entries whose pullback leg averaged more than `d` × the impulse leg's volume raises win rate without costing expectancy, under the standard v72 funnel.

## Instrument
`structure.pullback_vol_ratio` (v121), evaluated on **completed daily bars only**. The live sites drop today's forming bar through `strategy_pass.completed_frame`; replay slices are completed by construction. The rule rejects iff the ratio is not None and > d (`gates.ratio_exceeds`); None and NaN pass. Call sites: `strategy_pass._emit_signal` / `StrategyEngine._gated_plan` for strategy entries, and `analyze._apply_pullback_dryup` / `backtest_scenarios._dryup_kept` for confluence entries. Parity, including a forming-bar frame, is pinned by `tests/backtesting/test_pullback_dryup_parity.py`.

## Components (separate budgets, never pooled)
| Component | Knob delta | Population |
|---|---|---|
| strategy | `PULLBACK_DRYUP_SCOPE=strategy`, `PULLBACK_DRYUP_MAX_RATIO=d` | Fibonacci, EMA Crossover (pullback mode), Break & Retest, RSI, RSI Divergence, MA Ribbon, VWAP |
| confluence | `PULLBACK_DRYUP_SCOPE=confluence`, `PULLBACK_DRYUP_MAX_RATIO=d` | every confluence-sourced entry |

Arms come from `measure_arms.py` with both default engines (confluence + strategy), so each component is judged against the whole replayed book it would ship into. Order: strategy first, then confluence, one shot at a time.

## Frozen grid and selection rule (verbatim from the spec)
`d ∈ {0.60, 0.75, 0.90}`.
1. **Stage −1 reachability** (pilot, `d = 0.60`, the widest cut): refuse if there are zero changed outcomes. The population split is disclosed; replacements are expected and do not halt the run.
2. **Stage 0 MDE** (fold-train `selection` arms, paired bootstrap): run per cell, with `--train-effect-pp` set to that cell's fold-train standardised ΔWR. A refused cell is ineligible at Stage 1. If all three are refused, the shot is refused with the budget intact.
3. **Stage 1 selection** (fold-train only): a cell is eligible when it PASSES clauses 2–4 and 6 (SKIPPED is not a pass), with clause 6 read as below. The chosen `d` needs an eligible grid neighbour and `plateau_report()` `is_plateau`. Among those, take the largest ΔWR; on a tie, the larger `d`. Judge: `validate_component.py --stage selection --dryup-mechanism`.
4. **Stage 2 walk-forward**: `gate_win_rate`. It needs ≥ 2 of 3 folds improving, no fold worse than −1.0pp, and per-fold N ≥ 30.
5. **Stage 3 VALIDATION** 2024-01-01..2025-12-31: one shot per component. All six v72 clauses must pass, and a missing permutation p is a FAIL. Judge: `validate_component.py --stage validation --dryup-mechanism --permutation-p <p>`.

## Clause 6 reading (frozen amendment)
Mechanism is scored on the **baseline** arm. Baseline trades the predicate flags at `d` form the removed population, and baseline trades it does not flag form the retained population. The clause passes iff removed WR < retained WR **and** removed ExpR ≤ 0. Replacement trades admitted by freed slots or cooldowns are part of the component arm and count fully in clauses 1–5; their count (`added`) is disclosed. Implementation: `swingbot/core/backtesting/arms/dryup_clauses.py`, wired as `validate_component.py --dryup-mechanism`.

## Clause 5 instrument (partner decision, 2026-10-02)
`python scripts/backtest/permutation_test.py --arms <the stamped VALIDATION arm file> --n 200 --seed 42`. This extends the existing script (V122-10; its fold path's output is pinned unchanged by a witness test). It circularly shifts each ticker's baseline "removed" labels by seeded integers in [20, 200), keeps replacement trades in every null arm, and reports p = the share of null standardised ΔWR ≥ the observed. It reads arm rows only, so it covers confluence and strategy entries alike. Its `p_value` is passed as `--permutation-p`.

## Disclosure (every stage)
Removed / added (replacements) / changed counts, per-direction ΔWR and ΔExpR, the top-2 horizon share of the removed trades, a statement when > 80% of the removed trades are one direction, and the `None` share of the scoped baseline population (`dry-up none share` line).

## Stop rules
A failure at any stage closes that component in `docs/claude/backtest-methodology.md`'s closed-pre-registrations table with its numbers. The code stays merged and inert (defaults off). Reopening needs a mechanism other than "pullback-leg over impulse-leg mean volume above d ∈ {0.60, 0.75, 0.90}".
```

- [ ] **Step 2: Commit the record alone**

```bash
git add docs/superpowers/results/2026-10-02-v122-preregistration.md
git commit -m "docs(v122): pre-registration -- dry-up gate, two components, frozen grid, clause-5/6 instruments"
```

Record the commit hash; every later results doc quotes it.

### Task V122-12: Strategy component funnel (Stage −1 → 0 → 1 → 2 → 3)

**Files:**
- Create: `docs/superpowers/results/2026-10-02-v122-strategy.md` (appended at every stage), `docs/superpowers/results/2026-10-02-v122-strategy-stage1.json`
- Create on Stage 2/3 only: `docs/superpowers/results/2026-10-02-v122-strategy-walkforward.json`, `docs/superpowers/results/2026-10-02-v122-strategy-validation.md` / `.json`
- Modify on any failure: `docs/claude/backtest-methodology.md` (one closed-table row)
- Arms (not committed): `logs/v122/strategy-*.json`

**Interfaces:**
- Consumes: the V122-11 record. Commands use only the verified and extended flags:
  - `measure_arms.py --stage {pilot,selection,walkforward,validation} --knob A=v --out P [--preregistration P] [--workers N]`
  - `validate_component.py --stage {reachability,mde,selection,walkforward,validation} [--arms P] --title T --window W [--train-effect-pp X] [--grid-arms V=P] [--mde-refused V] [--dryup-mechanism] [--permutation-p P] [--out-md P] [--out-json P]`
  - `permutation_test.py --arms P --n 200 --seed 42`
- Produces: a verdict for the strategy component, either `ship candidate d=<x>` or a closed row.

**Rules for every step:** invoke `backtest-gate` before the command. Make no edit under `swingbot/` while a step's arms are being produced; the code hash is checked. Dispatch every full-universe run (`selection`, `walkforward`, `validation`) to the `backtest-runner` subagent; flushed progress goes to `logs/measure_arms.*.progress`. **Stop on the first failing stage**, append the numbers to the results doc, add the closed-table row (Step 7), commit, and go to V122-13.

- [ ] **Step 1: Stage −1 reachability (pilot)**

```bash
python scripts/backtest/measure_arms.py --stage pilot --knob PULLBACK_DRYUP_SCOPE=strategy --knob PULLBACK_DRYUP_MAX_RATIO=0.60 --preregistration docs/superpowers/results/2026-10-02-v122-preregistration.md --out logs/v122/strategy-pilot-0.60.json
python scripts/backtest/validate_component.py --stage reachability --arms logs/v122/strategy-pilot-0.60.json --title "v122 strategy d=0.60 pilot" --window "2018-06-01..2020-12-31"
```
Pass: `REACHABLE`. Copy the `split` line (removed / added / changed) into the results doc as disclosure; replacements do not halt the run. `refused:zero-diff` closes the component as unreachable, budget intact.

- [ ] **Step 2: Fold-train arms for all three cells, then Stage 0 MDE per cell**

```bash
for d in 0.60 0.75 0.90; do python scripts/backtest/measure_arms.py --stage selection --knob PULLBACK_DRYUP_SCOPE=strategy --knob PULLBACK_DRYUP_MAX_RATIO=$d --preregistration docs/superpowers/results/2026-10-02-v122-preregistration.md --out logs/v122/strategy-selection-$d.json; done
for d in 0.60 0.75 0.90; do python -c "import sys; sys.path.insert(0,'scripts/backtest'); import validate_component as vc; from swingbot.core.backtesting.acceptance import delta_standardised_win_rate as dwr; b, c = vc.load_arms('logs/v122/strategy-selection-$d.json'); print('$d', dwr(b, c))"; done
python scripts/backtest/validate_component.py --stage mde --arms logs/v122/strategy-selection-0.60.json --train-effect-pp <dWR printed for 0.60> --title "v122 strategy d=0.60 MDE" --window "2018-06-01..2022-12-31"
```
Repeat the `--stage mde` line for 0.75 and 0.90, each with its own printed ΔWR. A zero or negative ΔWR is passed as printed; it is refused, which is correct. Record `RESOLVABLE` or `REFUSED` per cell. If all three are refused, close at Stage 0.

- [ ] **Step 3: Stage 1 selection (fold-train only, clause 6 per the frozen reading)**

```bash
python scripts/backtest/validate_component.py --stage selection --dryup-mechanism --grid-arms 0.60=logs/v122/strategy-selection-0.60.json --grid-arms 0.75=logs/v122/strategy-selection-0.75.json --grid-arms 0.90=logs/v122/strategy-selection-0.90.json [--mde-refused <each refused d>] --title PULLBACK_DRYUP_MAX_RATIO --window "2018-06-01..2022-12-31" --out-json docs/superpowers/results/2026-10-02-v122-strategy-stage1.json
```
Pass: verdict `selected`; that `d` goes to Stage 2. `no-eligible-cell` or `spike` closes the component at Stage 1. Copy into the results doc every cell's line (eligibility, failed clauses, ΔWR, ExpR, and disclosure including `added`, the replacement count) and the `dry-up none share` line.

- [ ] **Step 4: Stage 2 walk-forward (free, repeatable)**

```bash
python scripts/backtest/measure_arms.py --stage walkforward --knob PULLBACK_DRYUP_SCOPE=strategy --knob PULLBACK_DRYUP_MAX_RATIO=<selected d> --preregistration docs/superpowers/results/2026-10-02-v122-preregistration.md --out logs/v122/strategy-walkforward.json
python scripts/backtest/validate_component.py --stage walkforward --arms logs/v122/strategy-walkforward.json --title "v122 strategy d=<selected d> walk-forward" --window "2021..2023 folds" --out-json docs/superpowers/results/2026-10-02-v122-strategy-walkforward.json
```
Pass: `PASS`. Anything else closes the component at Stage 2, VALIDATION budget unspent.

- [ ] **Step 5: Stage 3 VALIDATION, the one shot**

Before running, re-read the record and confirm `git status -- swingbot/ scripts/backtest/` is clean.

```bash
python scripts/backtest/measure_arms.py --stage validation --knob PULLBACK_DRYUP_SCOPE=strategy --knob PULLBACK_DRYUP_MAX_RATIO=<selected d> --preregistration docs/superpowers/results/2026-10-02-v122-preregistration.md --out logs/v122/strategy-validation.json
python scripts/backtest/permutation_test.py --arms logs/v122/strategy-validation.json --n 200 --seed 42
python scripts/backtest/validate_component.py --stage validation --dryup-mechanism --arms logs/v122/strategy-validation.json --permutation-p <p_value printed above> --title "v122 strategy d=<selected d> VALIDATION" --window "2024-01-01..2025-12-31" --out-md docs/superpowers/results/2026-10-02-v122-strategy-validation.md --out-json docs/superpowers/results/2026-10-02-v122-strategy-validation.json
python -c "import sys, json; sys.path.insert(0,'scripts/backtest'); import validate_component as vc; from swingbot.core.backtesting.arms.selection import removed_disclosure; b, c = vc.load_arms('logs/v122/strategy-validation.json'); print(json.dumps(removed_disclosure(b, c), indent=1))"
```
If `permutation_test.py` prints `p_value: null`, pass nothing; the missing p is a FAIL, as pre-registered. Record the result as it stands and never rerun or retune it. `PASS` makes the component a ship candidate for V122-14; `FAIL` closes it, budget spent.

- [ ] **Step 6: Write the results doc's observations**

Include the full per-stage table, the pre-registered rule quoted verbatim, the record's commit hash, the per-direction lines, the top-2 horizon share, the one-direction flag, the replacement count, the `None` share, and the permutation JSON. Write an honest observations section: failures are recorded, not fixed.

- [ ] **Step 7: On failure, close the component in the methodology table**

Append one row to `docs/claude/backtest-methodology.md` § "Closed pre-registrations", in this shape, with the measured numbers:

```markdown
| Pullback volume dry-up gate, strategy scope (7 pullback strategies), `d ∈ {0.60, 0.75, 0.90}` (v122) | **<NO-LIFT / FAILED> at Stage <n>; VALIDATION <not spent, remains available / spent>.** <per-cell N, ΔWR, ΔExpR, flagged WR vs unflagged (baseline reading), flagged ExpR, cut %, replacements, None share, per-direction, top-2 horizon share>. `PULLBACK_DRYUP_SCOPE` stays `off`, code merged inert. Reopening needs a mechanism other than "pullback-leg over impulse-leg mean volume above d ∈ {0.60, 0.75, 0.90}" | `results/2026-10-02-v122-preregistration.md`, `results/2026-10-02-v122-strategy.md` |
```

- [ ] **Step 8: Commit**

```bash
git add docs/superpowers/results/2026-10-02-v122-strategy*.md docs/superpowers/results/2026-10-02-v122-strategy*.json docs/claude/backtest-methodology.md
git commit -m "docs(v122): strategy component funnel result"
```

### Task V122-13: Confluence component funnel (Stage −1 → 0 → 1 → 2 → 3)

**Files:**
- Create: `docs/superpowers/results/2026-10-02-v122-confluence.md`, `docs/superpowers/results/2026-10-02-v122-confluence-stage1.json`
- Create on Stage 2/3 only: `docs/superpowers/results/2026-10-02-v122-confluence-walkforward.json`, `docs/superpowers/results/2026-10-02-v122-confluence-validation.md` / `.json`
- Modify on any failure: `docs/claude/backtest-methodology.md` (one closed-table row)
- Arms (not committed): `logs/v122/confluence-*.json`

**Interfaces:**
- Consumes: the V122-11 record. This task starts only after V122-12's commit, never while a strategy shot runs. The strategy component's result changes no rule here; the budgets are separate and never pooled.
- Produces: a verdict for the confluence component.

**Rules for every step:** the same as V122-12. Invoke `backtest-gate` before each command, make no edits during a run, send full-universe runs to `backtest-runner`, and stop on the first failing stage.

- [ ] **Step 1: Stage −1 reachability (pilot)**

```bash
python scripts/backtest/measure_arms.py --stage pilot --knob PULLBACK_DRYUP_SCOPE=confluence --knob PULLBACK_DRYUP_MAX_RATIO=0.60 --preregistration docs/superpowers/results/2026-10-02-v122-preregistration.md --out logs/v122/confluence-pilot-0.60.json
python scripts/backtest/validate_component.py --stage reachability --arms logs/v122/confluence-pilot-0.60.json --title "v122 confluence d=0.60 pilot" --window "2018-06-01..2020-12-31"
```
Pass: `REACHABLE`. Disclose the `split` line. `refused:zero-diff` closes the component, budget intact.

- [ ] **Step 2: Fold-train arms and Stage 0 MDE per cell**

```bash
for d in 0.60 0.75 0.90; do python scripts/backtest/measure_arms.py --stage selection --knob PULLBACK_DRYUP_SCOPE=confluence --knob PULLBACK_DRYUP_MAX_RATIO=$d --preregistration docs/superpowers/results/2026-10-02-v122-preregistration.md --out logs/v122/confluence-selection-$d.json; done
for d in 0.60 0.75 0.90; do python -c "import sys; sys.path.insert(0,'scripts/backtest'); import validate_component as vc; from swingbot.core.backtesting.acceptance import delta_standardised_win_rate as dwr; b, c = vc.load_arms('logs/v122/confluence-selection-$d.json'); print('$d', dwr(b, c))"; done
python scripts/backtest/validate_component.py --stage mde --arms logs/v122/confluence-selection-0.60.json --train-effect-pp <dWR printed for 0.60> --title "v122 confluence d=0.60 MDE" --window "2018-06-01..2022-12-31"
```
Repeat `--stage mde` for 0.75 and 0.90. If all three are refused, close at Stage 0.

- [ ] **Step 3: Stage 1 selection**

```bash
python scripts/backtest/validate_component.py --stage selection --dryup-mechanism --grid-arms 0.60=logs/v122/confluence-selection-0.60.json --grid-arms 0.75=logs/v122/confluence-selection-0.75.json --grid-arms 0.90=logs/v122/confluence-selection-0.90.json [--mde-refused <each refused d>] --title PULLBACK_DRYUP_MAX_RATIO --window "2018-06-01..2022-12-31" --out-json docs/superpowers/results/2026-10-02-v122-confluence-stage1.json
```
Pass: `selected`. Otherwise close at Stage 1.

- [ ] **Step 4: Stage 2 walk-forward**

```bash
python scripts/backtest/measure_arms.py --stage walkforward --knob PULLBACK_DRYUP_SCOPE=confluence --knob PULLBACK_DRYUP_MAX_RATIO=<selected d> --preregistration docs/superpowers/results/2026-10-02-v122-preregistration.md --out logs/v122/confluence-walkforward.json
python scripts/backtest/validate_component.py --stage walkforward --arms logs/v122/confluence-walkforward.json --title "v122 confluence d=<selected d> walk-forward" --window "2021..2023 folds" --out-json docs/superpowers/results/2026-10-02-v122-confluence-walkforward.json
```

- [ ] **Step 5: Stage 3 VALIDATION, the one shot**

Make the same pre-checks as V122-12 Step 5, then:

```bash
python scripts/backtest/measure_arms.py --stage validation --knob PULLBACK_DRYUP_SCOPE=confluence --knob PULLBACK_DRYUP_MAX_RATIO=<selected d> --preregistration docs/superpowers/results/2026-10-02-v122-preregistration.md --out logs/v122/confluence-validation.json
python scripts/backtest/permutation_test.py --arms logs/v122/confluence-validation.json --n 200 --seed 42
python scripts/backtest/validate_component.py --stage validation --dryup-mechanism --arms logs/v122/confluence-validation.json --permutation-p <p_value printed above> --title "v122 confluence d=<selected d> VALIDATION" --window "2024-01-01..2025-12-31" --out-md docs/superpowers/results/2026-10-02-v122-confluence-validation.md --out-json docs/superpowers/results/2026-10-02-v122-confluence-validation.json
python -c "import sys, json; sys.path.insert(0,'scripts/backtest'); import validate_component as vc; from swingbot.core.backtesting.arms.selection import removed_disclosure; b, c = vc.load_arms('logs/v122/confluence-validation.json'); print(json.dumps(removed_disclosure(b, c), indent=1))"
```

- [ ] **Step 6: Observations, the closed row on failure, and the commit**

The results doc follows V122-12 Step 6. On failure, add the closed-table row in V122-12 Step 7's shape, naming the component "confluence scope (all confluence entries)" and citing `results/2026-10-02-v122-confluence.md` as the record.

```bash
git add docs/superpowers/results/2026-10-02-v122-confluence*.md docs/superpowers/results/2026-10-02-v122-confluence*.json docs/claude/backtest-methodology.md
git commit -m "docs(v122): confluence component funnel result"
```

### Task V122-14: Ship or close

**Files:**
- Modify only if exactly one component passed VALIDATION: `swingbot/config.py` (the two Field defaults and their `help`), `.env.example`, `tests/test_config_pullback_dryup.py`, `tests/backtesting/test_pullback_dryup_witness.py`

**Interfaces:**
- Consumes: the V122-12 and V122-13 verdicts.
- Produces: shipped defaults, or nothing (inert).

- [ ] **Step 1: Branch on the verdicts**

- **Neither passed:** confirm both closed rows are in the methodology table. The defaults stay `off`/`0`. Skip to V122-15. The plan closes as implemented-inert, and the closing commit amends `Bump:` to `none` with a one-clause reason.
- **Both passed:** stop and ask the partner (`AskUserQuestion`). The spec defers the "scope becomes a set" type change to that point; do not change the field type in this plan.
- **Exactly one passed:** do Steps 2–4.

- [ ] **Step 2: Rewrite the witness test so it pins "off" explicitly, since "off" is no longer the default**

```python
@pytest.mark.slow
def test_scope_off_replay_matches_the_pre_gate_witness(monkeypatch):
    monkeypatch.setattr(config, "PULLBACK_DRYUP_SCOPE", "off")
    monkeypatch.setattr(config, "PULLBACK_DRYUP_MAX_RATIO", 0.0)
    current = json.loads(json.dumps(witness_rows()))
    assert current, "fixture must produce trades or the witness proves nothing"
    assert current == json.loads(WITNESS.read_text(encoding="utf-8"))
```

In `tests/test_config_pullback_dryup.py`, change the two default assertions to the shipped values: `f.default == "<scope>"` with `config.PULLBACK_DRYUP_SCOPE == "<scope>"`, and `config._cast(f, f.default) == <d>` with `config.PULLBACK_DRYUP_MAX_RATIO == <d>`.

- [ ] **Step 3: Flip the defaults**

In `config.py`, set `default="<scope>"` on `PULLBACK_DRYUP_SCOPE` and `default="<d>"` on `PULLBACK_DRYUP_MAX_RATIO`. Replace the scope help's "Ships OFF ..." sentence with "ON since v122's VALIDATION (`results/2026-10-02-v122-<scope>-validation.md`)". Set the same two values in `.env.example`.

- [ ] **Step 4: Run the narrow tests and commit**

Run: `python scripts/dev/testrun.py file tests/test_config_pullback_dryup.py`, `... file tests/backtesting/test_pullback_dryup_witness.py`, `... file tests/test_env_example_sync.py`
Expected: all PASS.

```bash
git add swingbot/config.py .env.example tests/test_config_pullback_dryup.py tests/backtesting/test_pullback_dryup_witness.py
git commit -m "feat(v122): pullback dry-up gate on for the <scope> scope at d=<d> after VALIDATION PASS"
```

This plan does not touch production `.env` overrides. If production pins either key, mirroring that is a `mirror-prod` task after merge.

### Task V122-15: Full-suite verification

**Files:** No new feature files. Fix only failures attributable to this plan, along with their narrow tests.

- [ ] **Step 1:** Run `python scripts/dev/testrun.py full` once, or dispatch the `test-runner` subagent. Green means `0 failed` and `0 xfailed`. If red, fix forward from the named failures. Before blaming this plan, check the diff scope and run the failing file alone; the shared-DB suite is known to flake.
- [ ] **Step 2:** Run `python -m radon cc -s -n C` over every `.py` file this plan touched. No new or changed block may score 15 or above; `replay_scenarios` stays at 15 and `_scan_one` at 39.
- [ ] **Step 3:** Close the plan per `docs/claude/document-lifecycle.md`. The code ships merged in either outcome, so the plan files move to `implemented/`. Amend `Edge:` and `Bump:` in the closing commit if the outcome differs from the prediction. Only a shipped scope takes the spec's bot patch, resolved from the `VERSION.json` on disk at that moment; this plan fixes no release number.
