# v88 Armed Confluence Entries — Part 2: the instrument

> Header, global constraints, parallelisation and outcomes live in `2026-09-15-v88-armed-confluence-entries_0-index.md`. Every task here implicitly includes that file's Global Constraints.

# Phase 2 — Measurement instrument (worktree)

### Task AR5: Pre-registered measurement arithmetic

**Files:**
- Create: `swingbot/core/backtesting/armed_measurement.py`
- Test: `tests/backtesting/test_armed_measurement.py`

**Interfaces:**
- Consumes (AR2): `armed_replay.Cell`. From `acceptance.py`: `ArmTrade`, `NON_INFERIORITY_R`, `VOLUME_MAX_CUT_PCT`, `delta_standardised_win_rate`, `delta_expectancy_r`, `expectancy_r`. From `backtest_wf.py`: `plateau_report`.
- Produces:
  - constants `MODES`, `N_GRID = (3, 5, 10)`, `K_GRID = (0.25, 0.5)`, `B_GRID = (0.10, 0.25)`, `CELLS` (24 `Cell`s, order mode → n → k → b), `BASELINE = "baseline"`, `RUN1_WINDOW`, `SELECTION_WINDOW`, `SELECTION_OBSERVED_DAYS = 945`, `MDE_TARGET_DAYS = 730`, `FOLD_TEST_YEARS`, `VALIDATION_WINDOW`, `PERMUTATION_N = 200`, `PERMUTATION_SEED = 42`, verdicts `SELECTED`, `NO_ELIGIBLE_CELL`, `SPIKE`
  - `Row(arm: str, trade: ArmTrade, reaction: str | None = None)` with `to_dict()` / `Row.from_dict(d)`
  - `cell_by_id(cell_id) -> Cell`, `in_window(rows, window)`, `in_year(rows, year)`, `arm_trades(rows, arm) -> list[ArmTrade]`
  - `CellScore` dataclass; `score_cell(rows, cell) -> CellScore`
  - `Selection(scores, selected, best, plateaus, verdict)`; `select_cell(rows, cells=CELLS) -> Selection`
  - `arms_blob(rows, cell_id) -> dict`, `folds_blob(rows, cell_id) -> dict` (the shapes `validate_component.load_arms` / `load_folds` read)
  - `permutation_p(baseline, real_component, permuted_components) -> dict`
  - `render_selection_md(selection) -> str`

- [ ] **Step 1: Write the failing tests**

Create `tests/backtesting/test_armed_measurement.py`:

```python
import json
import sys
from pathlib import Path

import pytest

from swingbot.core.backtesting import armed_measurement as am
from swingbot.core.backtesting.acceptance import ArmTrade

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))
import validate_component as vc  # noqa: E402


def _trades(wins, losses, *, date="2019-03-01", horizon="4w", win_r=1.5):
    out = [ArmTrade("AAA", "confluence:Fibonacci", horizon, date, "win", win_r, 2.0)] * wins
    return out + [ArmTrade("AAA", "confluence:Fibonacci", horizon, date, "loss", -1.0, 2.0)] * losses


def _rows(arm, wins, losses, **kw):
    return [am.Row(arm, t, "R1" if arm != am.BASELINE else None) for t in _trades(wins, losses, **kw)]


def _grid_rows(default=(6, 3), overrides=None, baseline=(5, 5)):
    rows = _rows(am.BASELINE, *baseline)
    for cell in am.CELLS:
        rows += _rows(cell.cell_id, *(overrides or {}).get(cell.cell_id, default))
    return rows


def test_the_grid_is_the_pre_registered_24_cells():
    assert len(am.CELLS) == 24
    assert len({c.cell_id for c in am.CELLS}) == 24
    assert am.CELLS[0].cell_id == "M1-N3-k0.25-b0.10"
    assert am.CELLS[-1].cell_id == "M2-N10-k0.50-b0.25"
    # order is mode -> n -> k -> b, 4 cells per (mode, n): M2-N5 starts at 12 + 4
    assert am.cell_by_id("M2-N5-k0.25-b0.10") == am.CELLS[16]


def test_row_round_trips():
    row = _rows("M1-N3-k0.25-b0.10", 1, 0)[0]
    assert am.Row.from_dict(json.loads(json.dumps(row.to_dict()))) == row


def test_score_cell_eligible_and_its_numbers():
    rows = _grid_rows()
    score = am.score_cell(rows, am.CELLS[0])
    assert score.volume_cut_pct == pytest.approx(10.0)                 # 10 -> 9
    assert score.delta_win_rate_pp == pytest.approx(100 * 6 / 9 - 50)
    assert score.delta_expectancy_r == pytest.approx((9 - 3) / 9 - 0.25)
    assert score.eligible and score.reasons == ()


def test_score_cell_reasons():
    cut = am.score_cell(_grid_rows(default=(4, 2)), am.CELLS[0])     # 10 -> 6: 40% cut
    assert not cut.eligible and any(r.startswith("volume") for r in cut.reasons)
    worse = am.score_cell(_grid_rows(default=(3, 7)), am.CELLS[0])
    assert any(r.startswith("profit") for r in worse.reasons)
    assert any(r.startswith("win rate") for r in worse.reasons)


def test_select_picks_by_expectancy_then_smaller_n_on_a_plateau():
    selection = am.select_cell(_grid_rows())
    assert selection.verdict == am.SELECTED
    assert selection.selected == "M1-N3-k0.25-b0.10"                  # all tie -> smaller N, first in order
    assert all(p["is_plateau"] for p in selection.plateaus)
    assert [p["param"] for p in selection.plateaus] == ["ARMED_N", "ARMED_K", "ARMED_B"]


def test_a_best_cell_whose_neighbours_disagree_is_a_spike():
    selection = am.select_cell(_grid_rows(overrides={"M1-N5-k0.25-b0.10": (8, 1)}))
    assert selection.best == "M1-N5-k0.25-b0.10"
    assert selection.verdict == am.SPIKE and selection.selected is None


def test_no_eligible_cell():
    selection = am.select_cell(_grid_rows(default=(3, 7)))
    assert selection.verdict == am.NO_ELIGIBLE_CELL
    assert selection.selected is None and selection.plateaus == ()


def test_blobs_load_through_validate_component(tmp_path):
    rows = (_rows(am.BASELINE, 5, 5, date="2021-02-01") + _rows(am.BASELINE, 5, 5, date="2022-02-01")
            + _rows(am.BASELINE, 5, 5, date="2023-02-01"))
    for year in ("2021", "2022", "2023"):
        rows += _rows("M1-N3-k0.25-b0.10", 6, 3, date=f"{year}-03-01")
    arms = tmp_path / "arms.json"
    arms.write_text(json.dumps(am.arms_blob(rows, "M1-N3-k0.25-b0.10")))
    baseline, component = vc.load_arms(arms)
    assert len(baseline) == 30 and len(component) == 27
    folds = tmp_path / "folds.json"
    folds.write_text(json.dumps(am.folds_blob(rows, "M1-N3-k0.25-b0.10")))
    loaded = vc.load_folds(folds)
    assert [f["test_year"] for f in loaded] == ["2021", "2022", "2023"]
    assert all(len(f["baseline"]) == 10 and len(f["component"]) == 9 for f in loaded)


def test_permutation_p_is_the_share_of_permuted_deltas_at_or_above_the_real_one():
    baseline = _trades(5, 5)
    real = _trades(8, 2)
    permuted = [_trades(5, 5), _trades(9, 1), _trades(4, 6), _trades(8, 2)]
    result = am.permutation_p(baseline, real, permuted)
    assert result["real_delta_win_rate_pp"] == pytest.approx(30.0)
    assert result["p_value"] == pytest.approx(2 / 4)                  # 9-1 and 8-2 are >= 30pp
    assert result["n"] == 4 and result["n_valid"] == 4


def test_render_selection_md_lists_every_cell_and_the_verdict():
    md = am.render_selection_md(am.select_cell(_grid_rows()))
    assert "**Verdict: SELECTED**" in md
    assert all(cell.cell_id in md for cell in am.CELLS)
    assert "greatest" in md and "ΔExpR" in md                        # the rule is quoted
    assert am.LIMITATIONS in md                                       # spec §4.3
```

- [ ] **Step 2: Run to verify failure**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_armed_measurement.py`
Expected: FAIL — `ImportError: cannot import name 'armed_measurement'`.

- [ ] **Step 3: Write the module**

Create `swingbot/core/backtesting/armed_measurement.py`:

```python
"""Pre-registered v88 armed-entry measurement arithmetic (spec §3.5, §4).

Every stage decision is computed here from replay rows; the script
(scripts/backtest/measure_armed_entries.py) only moves rows between the
replay and disk. The constants below ARE the pre-registration. None is a
config.Field, so no search can sweep them, and none may change after a
number is seen -- a failed selection closes the measurement.
"""
from __future__ import annotations

import dataclasses
from dataclasses import asdict, dataclass

import numpy as np

from swingbot.core.backtesting.acceptance import (
    NON_INFERIORITY_R, VOLUME_MAX_CUT_PCT, ArmTrade, delta_expectancy_r,
    delta_standardised_win_rate, expectancy_r,
)
from swingbot.core.backtesting.armed_replay import Cell
from swingbot.core.backtesting.backtest_wf import plateau_report

MODES = ("M1", "M2")
N_GRID = (3, 5, 10)
K_GRID = (0.25, 0.5)
B_GRID = (0.10, 0.25)
CELLS = tuple(Cell(m, n, k, b) for m in MODES for n in N_GRID for k in K_GRID for b in B_GRID)
BASELINE = "baseline"

RUN1_WINDOW = ("2018-06-01", "2023-12-31")
SELECTION_WINDOW = ("2018-06-01", "2020-12-31")   # precedes every fold-test year
SELECTION_OBSERVED_DAYS, MDE_TARGET_DAYS = 945, 730
FOLD_TEST_YEARS = ("2021", "2022", "2023")
VALIDATION_WINDOW = ("2024-01-01", "2025-12-31")
PERMUTATION_N, PERMUTATION_SEED = 200, 42

SELECTED, NO_ELIGIBLE_CELL, SPIKE = "SELECTED", "NO_ELIGIBLE_CELL", "SPIKE"

SELECTION_RULE = (
    "A cell is eligible iff its alert-volume cut vs baseline is <= 25% (clause 4), "
    "ΔExpR >= −0.01R (clause 2's margin) and mix-standardised ΔWR > 0. Among eligible "
    "cells the greatest ΔExpR is selected; ties go to the greater ΔWR, then the smaller N. "
    "The selected cell must sit on a plateau (plateau_report, tolerance 0.03R) along each "
    "of N, k and b with the other knobs and the mode held; any spike disqualifies."
)

# Spec §4.3: quoted in every results doc this measurement writes.
LIMITATIONS = (
    "Recorded limitations: daily-bar ordering is conservative (stop before target on the "
    "same bar); the universe is today's cached tickers (survivorship); M2's market entry "
    "fills at a daily close a live reader could not have traded."
)


@dataclass(frozen=True)
class Row:
    arm: str                  # BASELINE or a Cell.cell_id
    trade: ArmTrade
    reaction: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict) -> "Row":
        return cls(value["arm"], ArmTrade(**value["trade"]), value.get("reaction"))


def cell_by_id(cell_id: str) -> Cell:
    for cell in CELLS:
        if cell.cell_id == cell_id:
            return cell
    raise KeyError(cell_id)


def in_window(rows, window):
    return [row for row in rows if window[0] <= row.trade.entry_date <= window[1]]


def in_year(rows, year):
    return [row for row in rows if row.trade.entry_date.startswith(year)]


def arm_trades(rows, arm) -> list[ArmTrade]:
    return [row.trade for row in rows if row.arm == arm]


@dataclass(frozen=True)
class CellScore:
    cell_id: str
    baseline_n: int
    component_n: int
    volume_cut_pct: float
    delta_win_rate_pp: float | None
    delta_expectancy_r: float | None
    component_expectancy_r: float | None
    eligible: bool
    reasons: tuple[str, ...]


def score_cell(rows, cell: Cell) -> CellScore:
    baseline, component = arm_trades(rows, BASELINE), arm_trades(rows, cell.cell_id)
    cut = 100.0 * (len(baseline) - len(component)) / len(baseline) if baseline else 100.0
    dwr = delta_standardised_win_rate(baseline, component)
    dexpr = delta_expectancy_r(baseline, component)
    reasons = []
    if cut > VOLUME_MAX_CUT_PCT:
        reasons.append(f"volume: cut {cut:.2f}% > {VOLUME_MAX_CUT_PCT}%")
    if dexpr is None or dexpr < NON_INFERIORITY_R:
        reasons.append(f"profit: dExpR below {NON_INFERIORITY_R}R")
    if dwr is None or dwr <= 0:
        reasons.append("win rate: standardised dWR not above 0")
    return CellScore(cell.cell_id, len(baseline), len(component), cut, dwr, dexpr,
                     expectancy_r(component), not reasons, tuple(reasons))


@dataclass(frozen=True)
class Selection:
    scores: tuple[CellScore, ...]
    selected: str | None      # the cell that goes on to Stage 0; None unless SELECTED
    best: str | None          # the rule's pick before the plateau check
    plateaus: tuple[dict, ...]
    verdict: str


def select_cell(rows, cells=CELLS) -> Selection:
    scores = {cell.cell_id: score_cell(rows, cell) for cell in cells}
    eligible = [cell for cell in cells if scores[cell.cell_id].eligible]
    if not eligible:
        return Selection(tuple(scores.values()), None, None, (), NO_ELIGIBLE_CELL)
    best = max(eligible, key=lambda c: (scores[c.cell_id].delta_expectancy_r,
                                        scores[c.cell_id].delta_win_rate_pp, -c.n))
    plateaus = []
    for knob, grid in (("n", N_GRID), ("k", K_GRID), ("b", B_GRID)):
        variants = [dataclasses.replace(best, **{knob: value}) for value in grid]
        expectancies = []
        for variant in variants:
            score = scores.get(variant.cell_id)
            value = None if score is None else score.component_expectancy_r
            expectancies.append(float("nan") if value is None else value)
        plateaus.append(plateau_report(f"ARMED_{knob.upper()}", list(grid), expectancies,
                                       getattr(best, knob)))
    on_plateau = all(p["is_plateau"] for p in plateaus)
    return Selection(tuple(scores.values()), best.cell_id if on_plateau else None,
                     best.cell_id, tuple(plateaus), SELECTED if on_plateau else SPIKE)


def arms_blob(rows, cell_id: str) -> dict:
    return {"baseline": [asdict(t) for t in arm_trades(rows, BASELINE)],
            "component": [asdict(t) for t in arm_trades(rows, cell_id)]}


def folds_blob(rows, cell_id: str) -> dict:
    return {"folds": [{"test_year": year, **arms_blob(in_year(rows, year), cell_id)}
                      for year in FOLD_TEST_YEARS]}


def permutation_p(baseline, real_component, permuted_components) -> dict:
    """Spec §4.2: p = share of permuted mix-standardised ΔWR >= the real ΔWR."""
    real = delta_standardised_win_rate(baseline, real_component)
    permuted = [delta_standardised_win_rate(baseline, c) for c in permuted_components]
    valid = [value for value in permuted if value is not None]
    p_value = None if real is None or not valid else float(np.mean([v >= real for v in valid]))
    return {"real_delta_win_rate_pp": real, "p_value": p_value,
            "n": len(permuted), "n_valid": len(valid)}


def _fmt(value, spec):
    return "n/a" if value is None else format(value, spec)


def render_selection_md(selection: Selection) -> str:
    lines = ["# v88 armed confluence entries — Stage 1 selection", "",
             f"**Verdict: {selection.verdict}**", "",
             f"Window: {SELECTION_WINDOW[0]}..{SELECTION_WINDOW[1]} (fold-train only).", "",
             "## Pre-registered rule", "", SELECTION_RULE, "", LIMITATIONS, "",
             "## All 24 cells", "",
             "| cell | baseline N | component N | cut % | ΔWR pp | ΔExpR R | ExpR R | eligible | reasons |",
             "|---|---|---|---|---|---|---|---|---|"]
    for s in selection.scores:
        lines.append(f"| {s.cell_id} | {s.baseline_n} | {s.component_n} | {s.volume_cut_pct:+.2f} | "
                     f"{_fmt(s.delta_win_rate_pp, '+.2f')} | {_fmt(s.delta_expectancy_r, '+.4f')} | "
                     f"{_fmt(s.component_expectancy_r, '+.4f')} | {'yes' if s.eligible else 'no'} | "
                     f"{'; '.join(s.reasons)} |")
    lines += ["", f"Rule's pick before the plateau check: {selection.best or 'none'}",
              f"Selected for Stage 0: {selection.selected or 'none'}", ""]
    if selection.plateaus:
        lines += ["## Plateau reports", ""]
        for p in selection.plateaus:
            lines.append(f"- {p['param']}: grid {p['grid']}, expectancies "
                         f"{[round(e, 4) for e in p['expectancies']]}, adopted {p['adopted']}, "
                         f"plateau {p['is_plateau']}")
    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Run to verify it passes**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_armed_measurement.py`
Expected: 10 PASS.

- [ ] **Step 5: Commit**

```bash
git -C <worktree> add swingbot/core/backtesting/armed_measurement.py tests/backtesting/test_armed_measurement.py
git -C <worktree> commit -m "feat(v88): pre-registered selection arithmetic for the armed grid"
```

---

### Task AR6: The random-delay permutation

**Files:**
- Modify: `swingbot/core/backtesting/armed_replay.py`
- Modify: `docs/superpowers/specs/2026-09-15-v88-armed-confluence-entries-design.md` §4.2 (Step 5)
- Test: `tests/backtesting/test_armed_replay.py`

**Interfaces:**
- Consumes (AR3–AR4): `plan_at`, `make_confluence_at`, `CellResult.confirmed`, `levels_asof`.
- Produces: `delay_permutations(ticker, df, horizon_key, cell, confirmed, *, n, seed, level_cache, params=None, level_map_at=None, confluence_at=None) -> list[list[tuple[str, str, str, str]]]` — one list per permutation of `(entry_date, strategy, horizon_key, outcome)` for every plan that issued; `strategy` is `f"confluence:{plan.strategy}"`, matching the script's rows.

- [ ] **Step 1: Write the failing tests**

Append to `tests/backtesting/test_armed_replay.py`:

```python
def _perm_setup(monkeypatch):
    monkeypatch.setattr(ar, "atr", lambda df, period=14: pd.Series(1.0, index=df.index))
    df = _frame({27: REJECTION}, n=45)
    confirmed = [(_cand(index=25), ar.ArmOutcome("confirmed", 27, rx.R1, 27))]
    res = [levels.Level(T1, ["Fibonacci"])]
    sup = [levels.Level(90.0, ["Rolling S/R"])]
    kwargs = dict(level_cache={}, params=_params(),
                  level_map_at=lambda j: (sup, res), confluence_at=lambda *a: 3)
    return df, confirmed, kwargs


def test_permutations_are_seeded_and_stay_inside_each_arm_window(monkeypatch):
    df, confirmed, kwargs = _perm_setup(monkeypatch)
    first = ar.delay_permutations("AAPL", df, "4w", CELL, confirmed, n=50, seed=42, **kwargs)
    again = ar.delay_permutations("AAPL", df, "4w", CELL, confirmed, n=50, seed=42, **kwargs)
    assert first == again and len(first) == 50
    window_dates = {df.index[j].date().isoformat() for j in range(25, 31)}
    assert all(len(perm) <= 1 for perm in first)
    assert all(row[0] in window_dates for perm in first for row in perm)
    assert all(row[1].startswith("confluence:") and row[2] == "4w" for perm in first for row in perm)


def test_permutations_memoise_one_simulation_per_arm_bar(monkeypatch):
    df, confirmed, kwargs = _perm_setup(monkeypatch)
    calls = []
    real = ar.simulate_exit
    monkeypatch.setattr(ar, "simulate_exit", lambda *a, **k: calls.append(a[1]) or real(*a, **k))
    ar.delay_permutations("AAPL", df, "4w", CELL, confirmed, n=200, seed=42, **kwargs)
    assert len(calls) == len(set(calls)) <= CELL.n + 1


def test_a_random_bar_before_any_test_anchors_the_stop_at_the_arm_bar(monkeypatch):
    df, confirmed, kwargs = _perm_setup(monkeypatch)
    seen = {}
    real = ar.plan_at
    def spy(*a, **k):
        seen[k["j"]] = (k["first_test_index"], k["kind"])
        return real(*a, **k)
    monkeypatch.setattr(ar, "plan_at", spy)
    ar.delay_permutations("AAPL", df, "4w", CELL, confirmed, n=200, seed=1, **kwargs)
    assert seen, "200 draws over 6 bars must visit some bar"
    for j, (first_test, kind) in seen.items():
        assert first_test == (27 if j >= 27 else 25)
        assert kind == rx.R1                      # the arm's REAL reaction kind
```

- [ ] **Step 2: Run to verify failure**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_armed_replay.py`
Expected: the three new tests FAIL — `AttributeError: ... 'delay_permutations'`.

- [ ] **Step 3: Implement**

In `swingbot/core/backtesting/armed_replay.py`, add to the imports:

```python
import zlib

from swingbot.core.planning.plan_engine import simulate_exit
```

(Merge `simulate_exit` into the existing `plan_engine` import line rather than adding a second one.)

Append:

```python
def delay_permutations(ticker: str, df, horizon_key: str, cell: Cell, confirmed, *,
                       n: int, seed: int, level_cache: dict,
                       params: ScanParams | None = None, level_map_at=None,
                       confluence_at=None) -> list:
    """Spec §4.2's random-delay null for one (ticker, horizon): does the
    reaction carry information beyond simply waiting?

    Each permutation keeps the arms that really confirmed (`confirmed`,
    from replay_armed -- issued or regated alike) and moves each
    confirmation to a bar drawn uniformly from its own
    [i, min(i + N, last bar)] window. The plan is built by plan_at exactly
    as at a real confirmation: the stop anchors from the first test at or
    before the drawn bar (the arm bar when nothing has tested yet), and the
    entry follows the arm's REAL reaction kind -- M2's market/stop split
    needs a kind, and a random bar has none of its own.

    `level_cache` must be the cache arm_candidates filled walking bars in
    order (see the module docstring). Plans and exits are memoised per
    (arm, bar): a window holds at most N+1 bars, so 200 permutations cost
    about N+1 simulations per arm, not 200.

    Returns one list per permutation of (entry_date, strategy, horizon_key,
    outcome) for every plan that issued.
    """
    if params is None:
        params = ScanParams.from_config()
    if level_map_at is None:
        level_map_at = lambda j: levels_asof(ticker, df, j, horizon_key, level_cache)  # noqa: E731
    if confluence_at is None:
        confluence_at = make_confluence_at(df, horizon_key)
    rng = np.random.default_rng([seed, zlib.crc32(f"{ticker}|{horizon_key}".encode())])
    bars = reaction.Bars.from_frame(df)
    atr_values = atr(df, 14).to_numpy(dtype=float)
    last_bar = len(df) - 1
    memo: dict = {}

    def row_at(arm_index: int, cand: ArmCandidate, kind: str, j: int):
        key = (arm_index, j)
        if key not in memo:
            first_test = next((t for t in range(cand.index, j + 1)
                               if reaction.is_test(bars, t, cand.level, cand.direction,
                                                   cell.k, atr_values[t])), cand.index)
            plan, _ = plan_at(ticker, df, horizon_key, cand, j=j, first_test_index=first_test,
                              kind=kind, cell=cell, bars=bars, atr_values=atr_values,
                              params=params, level_map_at=level_map_at,
                              confluence_at=confluence_at)
            if plan is None:
                memo[key] = None
            else:
                result = simulate_exit(df, j, plan, scale_out=True)
                memo[key] = (df.index[j].date().isoformat(), f"confluence:{plan.strategy}",
                             horizon_key, result.outcome)
        return memo[key]

    permutations = []
    for _ in range(n):
        rows = []
        for arm_index, (cand, outcome) in enumerate(confirmed):
            j = int(rng.integers(cand.index, min(cand.index + cell.n, last_bar) + 1))
            row = row_at(arm_index, cand, outcome.kind, j)
            if row is not None:
                rows.append(row)
        permutations.append(rows)
    return permutations
```

- [ ] **Step 4: Run to verify it passes**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_armed_replay.py`
Expected: 21 PASS.

- [ ] **Step 5: Record the null's two readings in the spec**

In the spec §4.2, after `building the stop, entry and gates by §3.3–3.4 exactly as if that bar had reacted.` insert: ` The stop anchors from the first test at or before the drawn bar, or from the arm bar when nothing has tested yet; the entry mode follows the arm's real reaction kind. The population is every arm that confirmed in the real run, issued or regated.`

- [ ] **Step 6: Commit**

```bash
git -C <worktree> add swingbot/core/backtesting/armed_replay.py tests/backtesting/test_armed_replay.py docs/superpowers/specs/2026-09-15-v88-armed-confluence-entries-design.md
git -C <worktree> commit -m "feat(v88): random-delay permutation null"
```

---

### Task AR7: The measurement script

**Files:**
- Create: `scripts/backtest/measure_armed_entries.py`
- Test: `tests/scripts/test_measure_armed_entries.py`

**Interfaces:**
- Consumes (AR4–AR6): `armed_replay.arm_candidates`, `replay_armed`, `delay_permutations`; `armed_measurement.*`; `backtest_scenarios.replay_scenarios`; `plan_engine.simulate_exit`; `acceptance.arm_trade_from_plan`.
- Produces a CLI with exit codes: `0` ok / SELECTED, `1` selection not SELECTED, `2` no rows, `3` VALIDATION locked, `4` run metadata mismatch or missing run.
  - `replay --run run1|run2 [--tickers A,B] [--horizons 4w,2m] [--workers N] [--stage2-doc PATH]` → `data/v88/<run>/<TICKER>.jsonl`, `<TICKER>.counts.json`, `run.json`, transient `progress.txt`
  - `summary --run run1|run2 --window LO..HI --out-md PATH`
  - `select --out-md PATH --out-json PATH`
  - `arms --stage mde|walkforward|validation --cell CELL_ID --out PATH`
  - `permute --cell CELL_ID --out-json PATH [--workers N]`
  - every subcommand accepts `--cache-dir` (default `data/backtest_cache`) and `--out-root` (default `data/v88`)

- [ ] **Step 1: Write the failing tests**

Create `tests/scripts/test_measure_armed_entries.py`:

```python
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))
import measure_armed_entries as mae  # noqa: E402
import validate_component as vc  # noqa: E402
from swingbot.core.backtesting import armed_measurement as am  # noqa: E402
from swingbot.core.backtesting.acceptance import ArmTrade  # noqa: E402
from tests.helpers import make_ohlcv  # noqa: E402


def _cache(tmp_path):
    rng = np.random.RandomState(7)
    trend = list(100 * np.cumprod(1 + rng.normal(0.002, 0.01, 120)))
    box = [trend[-1] * (1 + 0.05 * np.sin(i / 4)) for i in range(60)]
    cache = tmp_path / "cache"
    cache.mkdir()
    df = make_ohlcv(trend + box, start="2019-01-02")
    df.index.name = "Date"
    df.to_csv(cache / "AAA.csv")
    return cache


def _write_rows(run_dir, rows, meta=None):
    run_dir.mkdir(parents=True, exist_ok=True)
    mae.write_shard(run_dir / "AAA.jsonl", [r.to_dict() for r in rows])
    (run_dir / "run.json").write_text(json.dumps(meta or {"cells": [c.cell_id for c in am.CELLS]}))


def _synthetic_rows():
    rows = []
    for date in ("2019-03-01", "2021-03-01", "2022-03-01", "2023-03-01"):
        rows += [am.Row(am.BASELINE, ArmTrade("AAA", "confluence:Fib", "4w", date, o, r, 2.0))
                 for o, r in [("win", 1.5)] * 5 + [("loss", -1.0)] * 5]
        for cell in am.CELLS:
            rows += [am.Row(cell.cell_id, ArmTrade("AAA", "confluence:Fib", "4w", date, o, r, 2.3), "R1")
                     for o, r in [("win", 1.5)] * 6 + [("loss", -1.0)] * 3]
    return rows


def test_run2_is_locked_without_a_passing_stage2_doc(tmp_path):
    cache = _cache(tmp_path)
    out = tmp_path / "out"
    assert mae.main(["replay", "--run", "run2", "--cache-dir", str(cache), "--out-root", str(out)]) == 3
    doc = tmp_path / "stage2.md"
    doc.write_text("**Overall: FAIL**\n")
    assert mae.main(["replay", "--run", "run2", "--cache-dir", str(cache), "--out-root", str(out),
                     "--stage2-doc", str(doc)]) == 3


def test_replay_refuses_to_resume_under_different_metadata(tmp_path):
    cache = _cache(tmp_path)
    run_dir = tmp_path / "out" / "run1"
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(json.dumps({"cache_files": ["ZZZ.csv"]}))
    assert mae.main(["replay", "--run", "run1", "--cache-dir", str(cache),
                     "--out-root", str(tmp_path / "out"), "--horizons", "4w", "--workers", "1"]) == 4


@pytest.mark.slow
def test_replay_writes_shards_and_removes_its_progress_file(tmp_path, monkeypatch):
    monkeypatch.setattr(am, "CELLS", (am.Cell("M1", 10, 0.5, 0.10),))
    cache = _cache(tmp_path)
    out = tmp_path / "out"
    assert mae.main(["replay", "--run", "run1", "--cache-dir", str(cache), "--out-root", str(out),
                     "--horizons", "4w", "--workers", "1"]) == 0
    run_dir = out / "run1"
    assert (run_dir / "AAA.jsonl").exists() and (run_dir / "AAA.counts.json").exists()
    assert not (run_dir / "progress.txt").exists()
    meta = json.loads((run_dir / "run.json").read_text())
    assert meta["cells"] == ["M1-N10-k0.50-b0.10"] and meta["horizons"] == ["4w"]
    counts = json.loads((run_dir / "AAA.counts.json").read_text())
    assert "4w|M1-N10-k0.50-b0.10" in counts
    # resuming skips the finished ticker and still exits clean
    assert mae.main(["replay", "--run", "run1", "--cache-dir", str(cache), "--out-root", str(out),
                     "--horizons", "4w", "--workers", "1"]) == 0


def test_summary_select_and_arms(tmp_path):
    out = tmp_path / "out"
    _write_rows(out / "run1", _synthetic_rows())
    md = tmp_path / "summary.md"
    assert mae.main(["summary", "--run", "run1", "--window", "2018-06-01..2020-12-31",
                     "--out-root", str(out), "--out-md", str(md)]) == 0
    assert "baseline" in md.read_text() and "M1-N3-k0.25-b0.10" in md.read_text()
    assert am.LIMITATIONS in md.read_text()

    sel_md, sel_json = tmp_path / "sel.md", tmp_path / "sel.json"
    assert mae.main(["select", "--out-root", str(out), "--out-md", str(sel_md),
                     "--out-json", str(sel_json)]) == 0
    payload = json.loads(sel_json.read_text())
    assert payload["verdict"] == am.SELECTED and payload["selected"] == "M1-N3-k0.25-b0.10"
    assert "**Verdict: SELECTED**" in sel_md.read_text()

    mde = tmp_path / "mde.json"
    assert mae.main(["arms", "--stage", "mde", "--cell", "M1-N3-k0.25-b0.10",
                     "--out-root", str(out), "--out", str(mde)]) == 0
    baseline, component = vc.load_arms(mde)
    assert len(baseline) == 10 and len(component) == 9          # only the 2019 rows

    wf = tmp_path / "wf.json"
    assert mae.main(["arms", "--stage", "walkforward", "--cell", "M1-N3-k0.25-b0.10",
                     "--out-root", str(out), "--out", str(wf)]) == 0
    assert [f["test_year"] for f in vc.load_folds(wf)] == ["2021", "2022", "2023"]


def test_select_with_no_rows_exits_2(tmp_path):
    _write_rows(tmp_path / "out" / "run1", [])
    assert mae.main(["select", "--out-root", str(tmp_path / "out")]) == 2


def test_permute_needs_a_run2(tmp_path):
    assert mae.main(["permute", "--cell", "M1-N3-k0.25-b0.10", "--out-root", str(tmp_path / "out"),
                     "--out-json", str(tmp_path / "p.json")]) == 4
```

- [ ] **Step 2: Run to verify failure**

Run: `python scripts/dev/testrun.py file tests/scripts/test_measure_armed_entries.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'measure_armed_entries'`.

- [ ] **Step 3: Write the script**

Create `scripts/backtest/measure_armed_entries.py`:

```python
#!/usr/bin/env python3
"""v88 A1: build and score the pre-registered armed-confluence-entry grid.

Read docs/superpowers/specs/2026-09-15-v88-armed-confluence-entries-design.md
§4 first. The arithmetic lives in swingbot/core/backtesting/armed_measurement.py;
this script only replays frames and moves rows to and from disk. Stage
verdicts come from scripts/backtest/validate_component.py, fed by `arms`.

    replay   --run run1 | run2     sharded per ticker, resumable; run2 refused
                                   without a Stage 2 doc reading **Overall: PASS**
    summary  --run R --window LO..HI --out-md PATH
    select   (Stage 1, selection window only)
    arms     --stage mde | walkforward | validation --cell CELL_ID --out PATH
    permute  --cell CELL_ID        the random-delay null over run2

Long runs: dispatch to the backtest-runner subagent. Progress is flushed to
stdout and to <out-root>/<run>/progress.txt as "done/total tickers (pct%)";
the file is deleted when the command finishes.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from swingbot.core.backtesting import armed_measurement as am  # noqa: E402
from swingbot.core.backtesting.acceptance import ArmTrade, arm_trade_from_plan  # noqa: E402
from swingbot.core.market.strategy_types import HORIZONS  # noqa: E402

CACHE_DIR = ROOT / "data" / "backtest_cache"
OUT_ROOT = ROOT / "data" / "v88"
RUNS = {"run1": am.RUN1_WINDOW, "run2": am.VALIDATION_WINDOW}
STAGE2_PASS_MARKER = "**Overall: PASS**"


def load_frame(cache_dir, symbol):
    path = Path(cache_dir) / f"{symbol}.csv"
    return pd.read_csv(path, index_col="Date", parse_dates=True) if path.exists() else None


def _trade(frame, index, plan, date) -> ArmTrade:
    from swingbot.core.planning.plan_engine import simulate_exit
    result = simulate_exit(frame, index, plan, scale_out=True)
    trade = arm_trade_from_plan(plan, entry_date=date, outcome=result.outcome,
                                r_multiple=result.r_total)
    return dataclasses.replace(trade, strategy=f"confluence:{plan.strategy}")


def ticker_rows(ticker, frame, window, horizons):
    """Baseline rows (today's replay) and every cell's rows, in window."""
    from swingbot.core.backtesting.armed_replay import arm_candidates, replay_armed
    from swingbot.core.backtesting.backtest_scenarios import replay_scenarios
    lo, hi = window
    rows, counts = [], {}
    for horizon in horizons:
        for index, plan in replay_scenarios(ticker, frame, horizon):
            date = str(frame.index[index].date())
            if lo <= date <= hi:
                rows.append(am.Row(am.BASELINE, _trade(frame, index, plan, date)))
        cache: dict = {}
        candidates = arm_candidates(ticker, frame, horizon, level_cache=cache)
        results = replay_armed(ticker, frame, horizon, am.CELLS, candidates=candidates,
                               level_cache=cache)
        for cell_id, result in results.items():
            counts[f"{horizon}|{cell_id}"] = dict(result.counts)
            for j, plan, kind in result.issued:
                date = str(frame.index[j].date())
                if lo <= date <= hi:
                    rows.append(am.Row(cell_id, _trade(frame, j, plan, date), kind))
    return rows, counts


def _replay_worker(task):
    ticker, cache_dir, window, horizons = task
    frame = load_frame(cache_dir, ticker)
    if frame is None or frame.empty:
        return ticker, [], {}
    rows, counts = ticker_rows(ticker, frame, window, horizons)
    return ticker, [row.to_dict() for row in rows], counts


def write_shard(path, rows):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    temporary.replace(path)


def read_rows(run_dir) -> list:
    rows = []
    for shard in sorted(Path(run_dir).glob("*.jsonl")):
        rows += [am.Row.from_dict(json.loads(line))
                 for line in shard.read_text(encoding="utf-8").splitlines() if line]
    return rows


def run_meta(cache_dir, window, horizons) -> dict:
    return {"cache_files": sorted(p.name for p in Path(cache_dir).glob("*.csv")),
            "window": list(window), "horizons": list(horizons),
            "cells": [cell.cell_id for cell in am.CELLS]}


def _map(worker, tasks, workers):
    """Results in task order; the pool is shut down when iteration ends."""
    if workers == 1:
        yield from map(worker, tasks)
        return
    with ProcessPoolExecutor(max_workers=workers) as pool:
        yield from pool.map(worker, tasks)


def cmd_replay(args) -> int:
    if args.run == "run2":
        doc = Path(args.stage2_doc) if args.stage2_doc else None
        if doc is None or not doc.exists() or STAGE2_PASS_MARKER not in doc.read_text(encoding="utf-8"):
            print("REFUSED -- run2 replays VALIDATION; it needs --stage2-doc reading "
                  f"{STAGE2_PASS_MARKER}", flush=True)
            return 3
    cache = Path(args.cache_dir)
    horizons = args.horizons.split(",") if args.horizons else list(HORIZONS)
    run_dir = Path(args.out_root) / args.run
    run_dir.mkdir(parents=True, exist_ok=True)
    meta = run_meta(cache, RUNS[args.run], horizons)
    meta_path = run_dir / "run.json"
    if meta_path.exists() and json.loads(meta_path.read_text()) != meta:
        print(f"REFUSED -- {meta_path} was written for a different cache/window/horizons/grid",
              flush=True)
        return 4
    meta_path.write_text(json.dumps(meta, indent=1))
    symbols = args.tickers.split(",") if args.tickers else sorted(p.stem for p in cache.glob("*.csv"))
    todo = [s for s in symbols if not (run_dir / f"{s}.jsonl").exists()]
    tasks = [(s, str(cache), RUNS[args.run], horizons) for s in todo]
    progress = run_dir / "progress.txt"
    try:
        for done, (ticker, rows, counts) in enumerate(_map(_replay_worker, tasks, args.workers), 1):
            write_shard(run_dir / f"{ticker}.jsonl", rows)
            (run_dir / f"{ticker}.counts.json").write_text(json.dumps(counts))
            pct = 100 * done // len(todo) if todo else 100
            progress.write_text(f"{done}/{len(todo)} tickers ({pct}%)\n")
            print(f"[{done}/{len(todo)}] {ticker}: {len(rows)} rows ({pct}%)", flush=True)
    finally:
        progress.unlink(missing_ok=True)
    print(f"complete: {len(read_rows(run_dir))} rows", flush=True)
    return 0


def cmd_summary(args) -> int:
    run_dir = Path(args.out_root) / args.run
    lo, hi = args.window.split("..")
    rows = am.in_window(read_rows(run_dir), (lo, hi))
    totals: dict = {}
    for path in sorted(run_dir.glob("*.counts.json")):
        for key, counts in json.loads(path.read_text()).items():
            cell_id = key.split("|", 1)[1]
            bucket = totals.setdefault(cell_id, {})
            for name, value in counts.items():
                bucket[name] = bucket.get(name, 0) + value
    names = sorted({name for bucket in totals.values() for name in bucket})
    lines = [f"# v88 armed confluence entries — {args.run} replay", "",
             f"Rows in window {lo}..{hi}: {len(rows)} across "
             f"{len({r.trade.ticker for r in rows})} tickers.", "", am.LIMITATIONS, "",
             "| arm | rows in window |", "|---|---|",
             f"| baseline | {len(am.arm_trades(rows, am.BASELINE))} |"]
    lines += [f"| {c.cell_id} | {len(am.arm_trades(rows, c.cell_id))} |" for c in am.CELLS]
    lines += ["", "## Arm funnel, whole replayed frame (not windowed)", "",
              "| cell | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    lines += [f"| {c.cell_id} | " + " | ".join(str(totals.get(c.cell_id, {}).get(n, 0)) for n in names) + " |"
              for c in am.CELLS]
    Path(args.out_md).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_md).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


def cmd_select(args) -> int:
    rows = am.in_window(read_rows(Path(args.out_root) / "run1"), am.SELECTION_WINDOW)
    if not rows:
        print("no rows in the selection window", flush=True)
        return 2
    selection = am.select_cell(rows)
    payload = {"verdict": selection.verdict, "selected": selection.selected, "best": selection.best,
               "scores": [dataclasses.asdict(s) for s in selection.scores],
               "plateaus": list(selection.plateaus)}
    if args.out_json:
        Path(args.out_json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out_json).write_text(json.dumps(payload, indent=1), encoding="utf-8")
    if args.out_md:
        Path(args.out_md).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out_md).write_text(am.render_selection_md(selection), encoding="utf-8")
    print(f"verdict: {selection.verdict}; selected: {selection.selected}", flush=True)
    return 0 if selection.verdict == am.SELECTED else 1


def cmd_arms(args) -> int:
    root = Path(args.out_root)
    if args.stage == "validation":
        blob = am.arms_blob(am.in_window(read_rows(root / "run2"), am.VALIDATION_WINDOW), args.cell)
    elif args.stage == "walkforward":
        blob = am.folds_blob(read_rows(root / "run1"), args.cell)
    else:
        blob = am.arms_blob(am.in_window(read_rows(root / "run1"), am.SELECTION_WINDOW), args.cell)
    parts = blob["folds"] if "folds" in blob else [blob]
    if not all(part["baseline"] for part in parts):
        print("an arm has no baseline rows", flush=True)
        return 2
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(blob), encoding="utf-8")
    return 0


def _permute_worker(task):
    from swingbot.core.backtesting.armed_replay import arm_candidates, delay_permutations, replay_armed
    ticker, cache_dir, cell_id, horizons, n, seed = task
    frame = load_frame(cache_dir, ticker)
    permutations = [[] for _ in range(n)]
    if frame is None or frame.empty:
        return ticker, permutations
    cell = am.cell_by_id(cell_id)
    for horizon in horizons:
        cache: dict = {}
        candidates = arm_candidates(ticker, frame, horizon, level_cache=cache)
        result = replay_armed(ticker, frame, horizon, [cell], candidates=candidates,
                              level_cache=cache)[cell_id]
        drawn = delay_permutations(ticker, frame, horizon, cell, result.confirmed, n=n,
                                   seed=seed, level_cache=cache)
        for index, rows in enumerate(drawn):
            permutations[index] += rows
    return ticker, permutations


def cmd_permute(args) -> int:
    run_dir = Path(args.out_root) / "run2"
    meta_path = run_dir / "run.json"
    if not meta_path.exists():
        print("REFUSED -- no run2 replay to permute", flush=True)
        return 4
    meta = json.loads(meta_path.read_text())
    rows = am.in_window(read_rows(run_dir), am.VALIDATION_WINDOW)
    baseline, real = am.arm_trades(rows, am.BASELINE), am.arm_trades(rows, args.cell)
    tickers = sorted({row.trade.ticker for row in rows})
    tasks = [(t, args.cache_dir, args.cell, meta["horizons"], am.PERMUTATION_N, am.PERMUTATION_SEED)
             for t in tickers]
    lo, hi = am.VALIDATION_WINDOW
    permuted = [[] for _ in range(am.PERMUTATION_N)]
    progress = run_dir / "progress.txt"
    try:
        for done, (ticker, drawn) in enumerate(_map(_permute_worker, tasks, args.workers), 1):
            for index, perm_rows in enumerate(drawn):
                permuted[index] += [ArmTrade(ticker, strategy, horizon, date, outcome, None, None)
                                    for date, strategy, horizon, outcome in perm_rows
                                    if lo <= date <= hi]
            pct = 100 * done // len(tasks) if tasks else 100
            progress.write_text(f"{done}/{len(tasks)} tickers ({pct}%)\n")
            print(f"[{done}/{len(tasks)}] {ticker} ({pct}%)", flush=True)
    finally:
        progress.unlink(missing_ok=True)
    result = {**am.permutation_p(baseline, real, permuted), "seed": am.PERMUTATION_SEED,
              "cell": args.cell, "window": list(am.VALIDATION_WINDOW)}
    Path(args.out_json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_json).write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(f"permutation p = {result['p_value']}", flush=True)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p):
        p.add_argument("--cache-dir", default=str(CACHE_DIR))
        p.add_argument("--out-root", default=str(OUT_ROOT))

    cell_ids = [cell.cell_id for cell in am.CELLS]
    p = sub.add_parser("replay"); common(p)
    p.add_argument("--run", choices=RUNS, required=True)
    p.add_argument("--tickers"); p.add_argument("--horizons"); p.add_argument("--stage2-doc")
    p.add_argument("--workers", type=int, default=max(1, os.cpu_count() or 1))
    p = sub.add_parser("summary"); common(p)
    p.add_argument("--run", choices=RUNS, required=True)
    p.add_argument("--window", required=True); p.add_argument("--out-md", required=True)
    p = sub.add_parser("select"); common(p)
    p.add_argument("--out-md"); p.add_argument("--out-json")
    p = sub.add_parser("arms"); common(p)
    p.add_argument("--stage", choices=("mde", "walkforward", "validation"), required=True)
    p.add_argument("--cell", choices=cell_ids, required=True); p.add_argument("--out", required=True)
    p = sub.add_parser("permute"); common(p)
    p.add_argument("--cell", choices=cell_ids, required=True); p.add_argument("--out-json", required=True)
    p.add_argument("--workers", type=int, default=max(1, os.cpu_count() or 1))

    args = parser.parse_args(argv)
    handler = {"replay": cmd_replay, "summary": cmd_summary, "select": cmd_select,
               "arms": cmd_arms, "permute": cmd_permute}[args.command]
    return handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run to verify it passes**

Run: `python scripts/dev/testrun.py file tests/scripts/test_measure_armed_entries.py`
Expected: 6 PASS (the slow replay test included).

`--cell` choices are read from `am.CELLS` when `main` builds the parser, so the slow test's monkeypatched one-cell grid still accepts only that cell — the other tests use the real grid.

- [ ] **Step 5: Commit**

```bash
git -C <worktree> add scripts/backtest/measure_armed_entries.py tests/scripts/test_measure_armed_entries.py
git -C <worktree> commit -m "feat(v88): sharded measurement script for the armed grid"
```

---

### Task AR8: Full-suite verification and merge

Dispatch the `test-runner` subagent (or run `python scripts/dev/testrun.py full`) once, over AR1–AR7. Expect `0 failed`, `0 xfailed`. No `frontend/` file was touched, so no `npm test`.

**If it is not green, fix forward from those failures** — they are this plan's regressions, and the task is not done until the run is.

Then merge the worktree branch to `main` per `document-lifecycle.md`. A conflict-free merge is not re-run; a merge that resolved conflicts gets one run. Do not remove the worktree yet — Part 3 closes the plan out. `Bump: none`: no `VERSION.json` change.
