# v139 — Part 2: arm S measurement instruments

> Index, Spec corrections, Global Constraints, Review Focus and `## Parallelisation`: `2026-10-08-v139-confluence-stop-geometry_0-index.md`. Work in the worktree `.claude/worktrees/2026-10-08-v139-confluence-stop-geometry` on branch `2026-10-08-v139-confluence-stop-geometry`. Every path below is relative to that worktree's root, which is the session root. Never edit the main tree. Never `cd` in Bash.

# Phase 3 — Arm S instruments (after Phase 2)

## Parallelisation (Phase 3)

Sequential throughout: V139-8 → V139-9 → V139-10, after all of Phase 2.
- V139-8 needs plans that carry `stop_ceiling_pct` (V139-5) and `plan_stop_ceiling` reading it (V139-6).
- V139-9 imports V139-8's `C_STEPS` / `cell_key`.
- V139-10 drives both, plus V139-3's universe switch.

Arm D needs no instrument of its own: it runs through `measure_arms.py` / `validate_component.py` / `permutation_test.py` as they are (plus V139-3).

### Task V139-8: `confluence_stop_replay` — baseline and every ceiling from the same scenarios

**Files:**
- Create: `swingbot/core/backtesting/confluence_stop_replay.py`
- Create: `tests/backtesting/test_confluence_stop_replay.py`

**Interfaces:**
- Consumes:
  - `replay_scenarios` (`backtest_scenarios.py:81`) and `arms.knobs.apply_knobs`.
  - `builders.clamped_distance` / `STOP_GEOMETRY_TOL` / `CLAMP_HEADROOM_PCT` (V139-4).
  - `TradePlanV2.stop_ceiling_pct` (V139-1, set by V139-5) and `stop_scope.plan_stop_ceiling` (V139-6).
  - `acceptance_replay.UNTRIGGERED` / `_exit_mix` / `_gap_through`, reused so the exit-mix and gap-through disclosures mean exactly what they meant in v129.
  - `acceptance.arm_trade_from_plan`, `exit_sim.simulate_exit`.
- Produces (V139-9 and V139-10 consume these):
  - `C_STEPS = (3.0, 4.0, 5.0)`
  - `ARM_S_KNOB`, `ARM_D_KNOB`
  - `cell_key(c) -> str` (`"c3"`, `"c4"`, `"c5"`)
  - `paired_plans(ticker, df, horizon_key, *, cells=C_STEPS, gates=None) -> list[tuple[int, TradePlanV2, dict[str, TradePlanV2]]]`
  - `plan_distance(plan) -> float | None`
  - `census_row(df, i, base, cell_plans, cells) -> dict`. Keys: `ticker`, `horizon_key`, `entry_date`, `direction`, `clamped`, `d`, `changed{key: bool}`, `rollback{key: bool}`. **No outcome.**
  - `entry_row(df, i, base, cell_plans, cells) -> dict | None`. The census keys plus `arm`, `baseline`, `cells{key: record | None}`. A record is the `ArmTrade` fields plus `exit_mix`, `gap_through` and `fill_beyond_ceiling`.
  - `replay_entries(ticker, df, horizons, *, start=None, end=None, cells=C_STEPS, gates=None) -> list[dict]`
  - `census(ticker, df, horizons, *, start=None, end=None, cells=C_STEPS, gates=None) -> list[dict]`

Design (index, Spec correction 8): arm S never adds or removes a plan. So `replay_scenarios` run at the baseline and at each `c` yields the same `(signal index, direction)` sequence. `paired_plans` asserts that and raises instead of pairing the wrong rows. A cell whose plan did not change (`stop_ceiling_pct is None`) reuses the baseline record, because the plan and its exit are identical.

- [ ] **Step 1: Write the failing tests**

Create `tests/backtesting/test_confluence_stop_replay.py`:

```python
"""v139 arm S replay on frozen fixtures: the baseline and every ceiling come
from the same scenarios; only clamped plans within c - 0.25 change, and they
keep their level; the census reads no outcome."""
import pytest

from swingbot import config
from swingbot.core.backtesting import confluence_stop_replay as csr
from tests.backtesting.test_backtest_scenarios import GATES, _structured_df
from tests.fixtures.ohlcv_parity import load_ohlcv

pytestmark = pytest.mark.slow

KEYS = ("c3", "c4", "c5")


@pytest.fixture(scope="module")
def frame():
    return load_ohlcv("DELL").loc[:"2019-12-31"]


@pytest.fixture(scope="module")
def pairs(frame):
    return csr.paired_plans("DELL", frame, "4w", gates=GATES)


def test_grid_and_keys_are_frozen():
    assert csr.C_STEPS == (3.0, 4.0, 5.0)
    assert tuple(csr.cell_key(c) for c in csr.C_STEPS) == KEYS


def test_knobs_must_be_off_while_measuring(frame, monkeypatch):
    monkeypatch.setattr(config, "CONFLUENCE_STRUCTURAL_STOP_PCT", 3.0)
    with pytest.raises(RuntimeError, match="must be 0 while measuring"):
        csr.paired_plans("DELL", frame, "4w", gates=GATES)


def test_paired_plans_share_every_entry(pairs):
    assert len(pairs) == 40
    for _, base, cells in pairs:
        assert set(cells) == set(KEYS)
        for plan in cells.values():
            assert (plan.direction, plan.trigger_price, plan.acceptance_level) == \
                (base.direction, base.trigger_price, base.acceptance_level)


def test_only_clamped_plans_within_c_change_and_they_keep_their_level(pairs):
    moved = 0
    for _, base, cells in pairs:
        d = csr.plan_distance(base)
        assert base.stop_ceiling_pct is None
        for c in csr.C_STEPS:
            plan = cells[csr.cell_key(c)]
            if plan.stop_ceiling_pct is None:
                assert (plan.stop_loss, plan.tp1, plan.tp2) == (base.stop_loss, base.tp1, base.tp2)
                continue
            moved += 1
            assert d is not None and d <= c - 0.25 + 1e-9
            assert plan.stop_ceiling_pct == c
            assert plan.stop_loss == base.acceptance_level
    assert moved > 0, "arm S must move at least one DELL plan"


def test_census_rows_match_the_measured_fixture(frame, pairs):
    rows = [csr.census_row(frame, i, base, cells, csr.C_STEPS) for i, base, cells in pairs]
    clamped = [r for r in rows if r["clamped"]]
    assert len(rows) == 40 and len(clamped) == 9
    for c, applies in zip(csr.C_STEPS, (2, 6, 8)):     # d <= 2.75 / 3.75 / 4.75
        key = csr.cell_key(c)
        assert sum(r["changed"][key] or r["rollback"][key] for r in rows) == applies
        assert not any(r["changed"][key] and r["rollback"][key] for r in rows)
    assert not any(key in rows[0] for key in ("baseline", "cells", "outcome"))


def test_census_simulates_no_exit_and_respects_the_window(frame, pairs, monkeypatch):
    monkeypatch.setattr(csr, "paired_plans", lambda *a, **k: pairs)
    monkeypatch.setattr(csr, "simulate_exit", lambda *a, **k: pytest.fail("census read an outcome"))
    dates = sorted(str(frame.index[i].date()) for i, _, _ in pairs)
    start = dates[len(dates) // 2]
    rows = csr.census("DELL", frame, ("4w",), start=start)
    assert len(rows) == sum(date >= start for date in dates)


def test_entry_rows_reuse_the_baseline_for_unchanged_cells(frame, pairs, monkeypatch):
    monkeypatch.setattr(csr, "paired_plans", lambda *a, **k: pairs)
    rows = csr.replay_entries("DELL", frame, ("4w",))
    assert rows and all(r["arm"] == "S" for r in rows)
    for r in rows:
        for key in KEYS:
            if not r["changed"][key]:
                assert r["cells"][key] == r["baseline"]
    record = next(r["baseline"] for r in rows if r["baseline"] is not None)
    assert {"exit_mix", "gap_through", "fill_beyond_ceiling", "planned_rr"} <= set(record)


def test_paired_plans_refuses_a_changed_entry_set(monkeypatch):
    real = csr._replay

    def dropping(ticker, df, horizon_key, c, gates):
        plans = real(ticker, df, horizon_key, c, gates)
        return plans[1:] if c == 4.0 else plans

    monkeypatch.setattr(csr, "_replay", dropping)
    with pytest.raises(RuntimeError, match="changed the entry set"):
        csr.paired_plans("AAPL", _structured_df(), "4w", gates=GATES)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_confluence_stop_replay.py`
Expected: FAIL: `ModuleNotFoundError: ... confluence_stop_replay`.

- [ ] **Step 3: Implement**

Create `swingbot/core/backtesting/confluence_stop_replay.py`:

```python
"""v139 arm S replay: every confluence entry is built under today's clamp
(baseline) and under each ceiling c, from the same scenarios.

Arm S never adds or removes a plan: a target that clears the min
reward:risk floor at the wider structural risk also clears it at the clamped
risk, and a rollback IS today's plan. So the baseline and each cell carry the
same (signal index, direction) sequence and the same cooldown; paired_plans
raises if that ever breaks. They differ only in stop and targets, and
therefore in how and whether a stop-entry triggers.

Two row shapes, both plain JSON types: census_row (plans only, Stage -1 --
no exit is simulated) and entry_row (outcomes, Stages 0-3).
"""
from __future__ import annotations

import dataclasses

from swingbot import config
from swingbot.core.backtesting.acceptance import arm_trade_from_plan
from swingbot.core.backtesting.acceptance_replay import UNTRIGGERED, _exit_mix, _gap_through
from swingbot.core.backtesting.arms.knobs import apply_knobs
from swingbot.core.backtesting.backtest_scenarios import replay_scenarios
from swingbot.core.planning.builders import (CLAMP_HEADROOM_PCT, STOP_GEOMETRY_TOL,
                                             clamped_distance)
from swingbot.core.planning.exit_sim import simulate_exit
from swingbot.core.planning.stop_scope import plan_stop_ceiling
from swingbot.core.risk_limits import planned_loss_pct

#: PRE-REGISTERED grid (spec § Definitions), shared by both arms. Changing a
#: step is a new pre-registration, not a tuning step.
C_STEPS = (3.0, 4.0, 5.0)
ARM_S_KNOB = "CONFLUENCE_STRUCTURAL_STOP_PCT"
ARM_D_KNOB = "CONFLUENCE_STOP_DROP_PCT"


def cell_key(c) -> str:
    """Stable JSON key for a ceiling: 'c3', 'c4', 'c5'."""
    return f"c{float(c):g}"


def _check_knobs_off() -> None:
    if config.CONFLUENCE_STRUCTURAL_STOP_PCT or config.CONFLUENCE_STOP_DROP_PCT:
        raise RuntimeError(
            "CONFLUENCE_STRUCTURAL_STOP_PCT and CONFLUENCE_STOP_DROP_PCT must be 0 while "
            "measuring: the baseline is today's clamp and each cell is applied explicitly.")


def _replay(ticker, df, horizon_key, c, gates) -> list:
    """replay_scenarios with arm S at ceiling c (None = baseline). apply_knobs
    reaches both ScanParams.from_config() call sites inside the replay."""
    delta = {} if c is None else {ARM_S_KNOB: float(c)}
    with apply_knobs(delta):
        return replay_scenarios(ticker, df, horizon_key, gates=gates)


def _signature(plans) -> list:
    return [(int(i), plan.direction) for i, plan in plans]


def paired_plans(ticker, df, horizon_key, *, cells=C_STEPS, gates=None) -> list:
    """[(signal_index, baseline_plan, {cell_key: cell_plan})] for one horizon.
    `gates` is the replay_scenarios test seam (None = live ScanParams)."""
    _check_knobs_off()
    base = _replay(ticker, df, horizon_key, None, gates)
    by_cell = {}
    for c in cells:
        plans = _replay(ticker, df, horizon_key, c, gates)
        if _signature(plans) != _signature(base):
            raise RuntimeError(
                f"arm S changed the entry set for {ticker} {horizon_key} at c={float(c):g}; "
                "the paired design assumes it never does -- stop and report")
        by_cell[cell_key(c)] = [plan for _, plan in plans]
    return [(int(i), plan, {key: plans[n] for key, plans in by_cell.items()})
            for n, (i, plan) in enumerate(base)]


def plan_distance(plan) -> float | None:
    """d of a clamped plan, from its recorded pre-clamp level; else None."""
    return clamped_distance(plan.trigger_price, plan.acceptance_level,
                            plan.direction == "bullish")


def _rolled_back(d, c, cell_plan) -> bool:
    """Arm S applied by geometry (d <= c - headroom) but the plan is today's:
    no candidate cleared the reward:risk band at the structural risk."""
    applies = d is not None and d <= float(c) - CLAMP_HEADROOM_PCT + STOP_GEOMETRY_TOL
    return applies and cell_plan.stop_ceiling_pct is None


def _flags(base, cell_plans, cells) -> dict:
    d = plan_distance(base)
    return {"clamped": d is not None, "d": d,
            "changed": {cell_key(c): cell_plans[cell_key(c)].stop_ceiling_pct is not None
                        for c in cells},
            "rollback": {cell_key(c): _rolled_back(d, c, cell_plans[cell_key(c)])
                         for c in cells}}


def _identity(df, i, plan) -> dict:
    return {"ticker": plan.ticker, "horizon_key": plan.horizon_key,
            "entry_date": str(df.index[i].date()), "direction": plan.direction}


def census_row(df, i, base, cell_plans, cells) -> dict:
    """Plans only -- no exit is simulated, so Stage -1 reads no outcome."""
    return {**_identity(df, i, base), **_flags(base, cell_plans, cells)}


def _record(df, i, plan) -> dict | None:
    """One side's exit as ArmTrade fields plus three disclosures, or None when
    the plan never became a trade. fill_beyond_ceiling: the fill's planned
    loss is past plan_stop_ceiling -- a fill live plan_manager would have
    cancelled (cancelled_risk_cap) but the replay keeps (Spec correction 3)."""
    res = simulate_exit(df, i, plan, scale_out=True)
    if res.outcome in UNTRIGGERED:
        return None
    trade = arm_trade_from_plan(plan, entry_date=str(df.index[i].date()),
                                outcome=res.outcome, r_multiple=res.r_total)
    beyond = planned_loss_pct(res.entry_price, plan.stop_loss) > \
        plan_stop_ceiling(plan) + STOP_GEOMETRY_TOL
    return {**dataclasses.asdict(trade), "exit_mix": _exit_mix(res),
            "gap_through": _gap_through(df, plan, res), "fill_beyond_ceiling": beyond}


def entry_row(df, i, base, cell_plans, cells) -> dict | None:
    """One entry under the baseline and every cell. An unchanged cell reuses
    the baseline record (same plan, same exit). Dropped only when nothing
    triggered: a wider stop changes stop-entry invalidation, so one side can
    be None while the other traded, and those rows are disclosed."""
    baseline = _record(df, i, base)
    records = {}
    for c in cells:
        plan = cell_plans[cell_key(c)]
        records[cell_key(c)] = baseline if plan.stop_ceiling_pct is None else _record(df, i, plan)
    if baseline is None and all(record is None for record in records.values()):
        return None
    return {"arm": "S", **_identity(df, i, base), **_flags(base, cell_plans, cells),
            "baseline": baseline, "cells": records}


def _in_window(signal_date, start, end) -> bool:
    return not ((start and signal_date < start) or (end and signal_date > end))


def _rows(make, ticker, df, horizons, start, end, cells, gates) -> list:
    rows = []
    for horizon_key in horizons:
        for i, base, cell_plans in paired_plans(ticker, df, horizon_key, cells=cells, gates=gates):
            if not _in_window(str(df.index[i].date()), start, end):
                continue
            row = make(df, i, base, cell_plans, cells)
            if row is not None:
                rows.append(row)
    return rows


def replay_entries(ticker, df, horizons, *, start=None, end=None, cells=C_STEPS,
                   gates=None) -> list:
    """Outcome rows for one ticker. `start`/`end` (ISO or None) restrict the
    SIGNAL date; the exit walk may run past `end`. Stage 3 passes the one
    selected cell so VALIDATION is never read for another."""
    return _rows(entry_row, ticker, df, horizons, start, end, tuple(cells), gates)


def census(ticker, df, horizons, *, start=None, end=None, cells=C_STEPS, gates=None) -> list:
    """Plan-only rows for one ticker (Stage -1)."""
    return _rows(census_row, ticker, df, horizons, start, end, tuple(cells), gates)
```

- [ ] **Step 4: Run the tests**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_confluence_stop_replay.py`
Expected: all pass. The fixture counts (40 plans, 9 clamped, 2/6/8 applying) were measured while writing this plan (V139-0's note). The `applies` counts are pure geometry on `d`, so they cannot depend on the V139-4/5 code. If they differ, the fixture moved: compare with V139-0's golden row counts before touching the assertion.

- [ ] **Step 5: Complexity**

Run: `python -m radon cc -s -n C swingbot/core/backtesting/confluence_stop_replay.py`
Expected: nothing listed.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/backtesting/confluence_stop_replay.py tests/backtesting/test_confluence_stop_replay.py
git commit -m "feat(v139): confluence_stop_replay -- paired baseline/ceiling plans, census and entry rows

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V139-9: `confluence_stop_funnel` — Stage −1 census verdicts and Stages 0–3

**Files:**
- Create: `swingbot/core/backtesting/confluence_stop_funnel.py`
- Create: `tests/backtesting/confluence_stop_rows.py` (synthetic rows)
- Create: `tests/backtesting/test_confluence_stop_funnel.py`

**Interfaces:**
- Consumes:
  - `C_STEPS` / `cell_key` (V139-8).
  - `acceptance_harvest.evaluate_harvest(..., cluster=)`, `acceptance.bootstrap_delta(..., cluster=)`.
  - From `acceptance_exit_funnel` (v129), shared on purpose because the spec runs the gate "as v129 ran it":
    - the constants `TRAIN`, `VALIDATION`, `MDE_CEILING_R`, `MDE_POWER`, `ELIGIBILITY_CLAUSES`;
    - the cell-key-generic helpers `arm_trades`, `sign_flip_p`, `_mde_cell`, `_flips`, `_sides`, `_triggered_once`, `_pp`;
    - `stage2`.
- Produces (V139-10 consumes these):
  - `ARM = "S"`, `CLUSTER = "week"`.
  - `TRAIN` / `VALIDATION` (re-exported).
  - `stage_minus1(census_rows, cells=C_STEPS) -> dict`. Verdict `REACHABLE` or `refused:zero-diff` for arm S. Also `verdicts{"S", "D"}`, `totals`, `by_stratum`, `identical_adjacent{"arm_s", "arm_d"}`.
  - `stage0(rows, cells=C_STEPS) -> dict`: `POWERED` or `UNDERPOWERED`.
  - `stage1(rows, cells=C_STEPS, *, n_resamples, seed) -> dict`: `SELECTED` or `NO_ELIGIBLE_CELL`, plus `selected{"cell", "c"}`.
  - `stage2(rows, key) -> dict`: `PASS` or `FAIL`.
  - `stage3(rows, key, *, n_resamples, seed) -> dict`: `PASS` or `FAIL`.
  - `report(rows, key, *, n_resamples, seed) -> dict`.

The only differences from v129's funnel are the grid (one axis, `c`), the bootstrap cluster (`"week"`, instrument v2, spec § Arm S), the census stage and the arm S disclosures. Stage 0's MDE and Stage 2's fold rule are v129's own functions.

- [ ] **Step 1: The synthetic rows**

Create `tests/backtesting/confluence_stop_rows.py`:

```python
"""Synthetic v139 arm S rows (the confluence_stop_replay shapes) for the
funnel and driver tests."""
from tests.backtesting.acceptance_rows import record

KEYS = ("c3", "c4", "c5")


def s_record(ticker, date, outcome, r, **kw):
    return {**record(ticker, date, outcome, r, **kw), "fill_beyond_ceiling": False}


def s_row(baseline, cells, *, d=3.0, changed=None, rollback=None):
    """`baseline` and each `cells` value are s_record() dicts or None."""
    anchor = baseline or next(c for c in cells.values() if c is not None)
    return {"arm": "S", "ticker": anchor["ticker"], "horizon_key": anchor["horizon_key"],
            "entry_date": anchor["entry_date"], "direction": anchor["direction"],
            "clamped": d is not None, "d": d,
            "changed": changed if changed is not None else {key: True for key in cells},
            "rollback": rollback if rollback is not None else {key: False for key in cells},
            "baseline": baseline, "cells": cells}


def lifted_s_rows(lifts, *, jitter=0.0, n_tickers=20, per_ticker=4, year=2021):
    """n_tickers * per_ticker paired rows. The baseline alternates win (+2R)
    and loss (-1R); each cell keeps the outcome and adds lifts[key], plus
    +jitter on even trades and -jitter on odd ones."""
    rows = []
    for t in range(n_tickers):
        for k in range(per_ticker):
            ticker, date = f"T{t:02d}", f"{year}-{k + 1:02d}-15"
            outcome, base_r = ("win", 2.0) if k % 2 == 0 else ("loss", -1.0)
            wobble = jitter if k % 2 == 0 else -jitter
            cells = {key: s_record(ticker, date, outcome, base_r + lift + wobble)
                     for key, lift in lifts.items()}
            rows.append(s_row(s_record(ticker, date, outcome, base_r), cells))
    return rows


def census_row(d, changed=(False, False, False), *, ticker="T00", date="2021-01-15",
               horizon="4w", direction="bullish", rollback=(False, False, False)):
    return {"ticker": ticker, "horizon_key": horizon, "entry_date": date,
            "direction": direction, "clamped": d is not None, "d": d,
            "changed": dict(zip(KEYS, changed)), "rollback": dict(zip(KEYS, rollback))}
```

- [ ] **Step 2: Write the failing tests**

Create `tests/backtesting/test_confluence_stop_funnel.py`:

```python
"""v139 arm S funnel on synthetic rows: census verdicts, the paired MDE,
plateau selection over c with the ISO-week bootstrap, v129's fold rule, the
one-shot validation clauses and the disclosures."""
import pytest

from swingbot.core.backtesting import acceptance_exit_funnel as v129
from swingbot.core.backtesting import confluence_stop_funnel as funnel
from tests.backtesting.confluence_stop_rows import (KEYS, census_row, lifted_s_rows,
                                                    s_record, s_row)

N = 200
PLATEAU = {"c3": 0.1, "c4": 0.3, "c5": 0.2}


def test_frozen_constants():
    assert funnel.C_STEPS == (3.0, 4.0, 5.0)
    assert funnel.CLUSTER == "week"
    assert (funnel.TRAIN, funnel.VALIDATION) == (v129.TRAIN, v129.VALIDATION)
    assert funnel.MDE_CEILING_R == 0.10
    assert funnel.ELIGIBILITY_CLAUSES == ("expectancy_gain", "win_rate_floor", "volume")


# --- Stage -1 ---------------------------------------------------------------

def _census():
    return [census_row(None, ticker="T00"),
            census_row(2.5, (True, True, True), ticker="T01"),
            census_row(3.5, (False, True, True), ticker="T02"),
            census_row(4.5, (False, False, True), ticker="T03"),
            census_row(6.0, ticker="T04", horizon="3m", direction="bearish")]


def test_stage_minus1_counts_buckets_changes_and_drops():
    out = funnel.stage_minus1(_census())
    assert out["verdict"] == "REACHABLE"
    assert out["verdicts"] == {"S": "REACHABLE", "D": "REACHABLE"}
    totals = out["totals"]
    assert (totals["plans"], totals["clamped"]) == (5, 4)
    assert totals["d_buckets"] == {"2.5-3.0": 1, "3.5-4.0": 1, "4.5-5.0": 1, "6.0-6.5": 1}
    assert {k: v["changed"] for k, v in totals["arm_s"].items()} == {"c3": 1, "c4": 2, "c5": 3}
    assert {k: v["dropped"] for k, v in totals["arm_d"].items()} == {"c3": 3, "c4": 2, "c5": 1}
    assert set(out["by_stratum"]) == {"4w/bullish", "3m/bearish"}
    assert out["identical_adjacent"] == {"arm_s": [], "arm_d": []}


def test_stage_minus1_counts_a_rollback_as_applying_not_changing():
    out = funnel.stage_minus1([census_row(2.6, (False, True, True), ticker="T05",
                                          rollback=(True, False, False))])
    assert out["totals"]["arm_s"]["c3"] == {"applies": 1, "changed": 0, "rollback": 1}


def test_stage_minus1_zero_diff_closes_both_arms():
    out = funnel.stage_minus1([census_row(None, ticker=f"T{n}") for n in range(3)])
    assert out["verdict"] == "refused:zero-diff"
    assert out["verdicts"] == {"S": "refused:zero-diff", "D": "refused:zero-diff"}


def test_stage_minus1_flags_identical_adjacent_cells():
    out = funnel.stage_minus1([census_row(2.5, (True, True, True), ticker="T01"),
                               census_row(4.5, (False, False, True), ticker="T02")])
    assert out["identical_adjacent"] == {"arm_s": [["c3", "c4"]], "arm_d": [["c3", "c4"]]}


# --- Stage 0 ----------------------------------------------------------------

def test_stage0_powered_when_every_cell_clears_the_ceiling():
    out = funnel.stage0(lifted_s_rows(PLATEAU))
    assert out["verdict"] == "POWERED"
    assert [c["cell"] for c in out["cells"]] == list(KEYS)


def test_stage0_underpowered_when_one_cell_is_noisy():
    rows = lifted_s_rows(PLATEAU)
    noisy = lifted_s_rows(PLATEAU, jitter=2.0)
    for target, source in zip(rows, noisy):
        target["cells"]["c5"] = source["cells"]["c5"]
    out = funnel.stage0(rows)
    assert out["verdict"] == "UNDERPOWERED"
    assert {c["cell"]: c["powered"] for c in out["cells"]} == {"c3": True, "c4": True, "c5": False}


# --- Stage 1 ----------------------------------------------------------------

def test_stage1_selects_the_highest_lower_bound_on_the_plateau():
    out = funnel.stage1(lifted_s_rows(PLATEAU), n_resamples=N)
    assert out["verdict"] == "SELECTED"
    assert out["selected"] == {"cell": "c4", "c": 4.0}
    assert all(c["eligible"] and c["plateau"] for c in out["cells"])
    assert all(c["gate"]["cluster"] == "week" for c in out["cells"])


def test_stage1_a_cell_with_an_ineligible_neighbour_is_off_the_plateau():
    out = funnel.stage1(lifted_s_rows({"c3": 0.0, "c4": 0.1, "c5": 0.5}), n_resamples=N)
    by_cell = {c["cell"]: c for c in out["cells"]}
    assert by_cell["c3"]["eligible"] is False
    assert by_cell["c4"]["eligible"] is True and by_cell["c4"]["plateau"] is False
    assert by_cell["c5"]["plateau"] is True
    assert out["selected"]["cell"] == "c5"


def test_stage1_no_eligible_cell():
    out = funnel.stage1(lifted_s_rows({key: 0.0 for key in KEYS}), n_resamples=N)
    assert out["verdict"] == "NO_ELIGIBLE_CELL" and out["selected"] is None


def test_stage1_tie_goes_to_the_smaller_c():
    out = funnel.stage1(lifted_s_rows({key: 0.2 for key in KEYS}), n_resamples=N)
    assert out["selected"]["cell"] == "c3"


# --- Stage 2 ----------------------------------------------------------------

def _years(lift_by_year):
    rows = []
    for year, lift in lift_by_year.items():
        rows += lifted_s_rows({"c4": lift}, year=year)
    return rows


def test_stage2_is_v129s_fold_rule():
    out = funnel.stage2(_years({2020: 0.2, 2021: 0.2, 2022: -0.1, 2023: -0.1}), "c4")
    assert (out["verdict"], out["arm"], out["cell"]) == ("PASS", "S", "c4")
    assert funnel.stage2(_years({2020: 0.2, 2021: -0.1, 2022: -0.1, 2023: -0.1}),
                         "c4")["verdict"] == "FAIL"


# --- Stage 3 ----------------------------------------------------------------

def test_stage3_passes_a_real_lift_and_fails_a_null():
    good = funnel.stage3(lifted_s_rows({"c4": 0.3}, year=2024), "c4", n_resamples=N)
    assert good["verdict"] == "PASS" and good["permutation_p"] < 0.05
    assert good["gate"]["cluster"] == "week"
    assert {c["name"]: c["verdict"] for c in good["gate"]["clauses"]} == {
        "expectancy_gain": "PASS", "win_rate_floor": "PASS", "volume": "PASS",
        "permutation": "PASS"}
    null = funnel.stage3(lifted_s_rows({"c4": 0.0}, year=2024), "c4", n_resamples=N)
    assert null["verdict"] == "FAIL"


# --- disclosures --------------------------------------------------------------

def test_report_discloses_changes_rollbacks_fills_and_one_sided_rows():
    rows = lifted_s_rows({"c4": 0.3}, n_tickers=2, per_ticker=2)
    rows[0]["changed"]["c4"] = False
    rows[0]["rollback"]["c4"] = True
    rows[0]["cells"]["c4"] = rows[0]["baseline"]
    rows[1]["d"] = 3.5
    rows[1]["cells"]["c4"] = {**rows[1]["cells"]["c4"], "fill_beyond_ceiling": True,
                              "gap_through": True}
    rows.append(s_row(None, {"c4": s_record("T09", "2021-05-15", "win", 2.0)}))
    out = funnel.report(rows, "c4", n_resamples=N)
    assert (out["n_baseline"], out["n_component"]) == (4, 5)
    assert (out["changed"], out["rollback"]) == (4, 1)
    assert out["median_d_changed"] == pytest.approx(3.0)
    assert out["fill_beyond_ceiling"] == {"baseline": 0, "component": 1}
    assert out["gap_through"] == {"baseline": 0, "component": 1}
    assert (out["only_baseline_triggered"], out["only_cell_triggered"]) == (0, 1)
    assert out["per_horizon_n"] == {"4w": 5}
```

- [ ] **Step 3: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_confluence_stop_funnel.py`
Expected: FAIL: `ImportError: cannot import name 'confluence_stop_funnel'`.

- [ ] **Step 4: Implement**

Create `swingbot/core/backtesting/confluence_stop_funnel.py`:

```python
"""v139 arm S funnel: Stage -1 census verdicts and Stages 0-3 over
confluence_stop_replay rows.

Every constant is PRE-REGISTERED (spec § Arm S; plan index, Spec correction
10). The gate is the v92 harvest gate run exactly as v129 ran it -- its
constants and its cell-key-generic helpers are imported from
acceptance_exit_funnel on purpose -- except that the bootstrap clusters by
ISO week of entry date (instrument v2), as the v139 spec requires.
"""
from __future__ import annotations

import math
import statistics
from collections import Counter

from .acceptance import (BOOTSTRAP_RESAMPLES, bootstrap_delta, delta_expectancy_r,
                         expectancy_r, median_planned_rr, render_json, win_rate)
from .acceptance_exit_funnel import (ELIGIBILITY_CLAUSES, MDE_CEILING_R, MDE_POWER, TRAIN,
                                     VALIDATION, _flips, _mde_cell, _pp, _sides,
                                     _triggered_once, arm_trades, sign_flip_p)
from .acceptance_exit_funnel import stage2 as _v129_stage2
from .acceptance_harvest import evaluate_harvest
from .confluence_stop_replay import C_STEPS, cell_key

__all__ = ["ARM", "CLUSTER", "C_STEPS", "TRAIN", "VALIDATION", "stage_minus1", "stage0",
           "stage1", "stage2", "stage3", "report"]

ARM = "S"
#: Instrument v2 (v136 §4): the bootstrap resamples ISO weeks of entry date.
CLUSTER = "week"
D_BUCKET_PCT = 0.5


# --- Stage -1 (plans only) -------------------------------------------------------

def _bucket(d) -> str:
    lo = math.floor(d / D_BUCKET_PCT) * D_BUCKET_PCT
    return f"{lo:.1f}-{lo + D_BUCKET_PCT:.1f}"


def _row_id(row) -> tuple:
    return row["ticker"], row["horizon_key"], row["entry_date"], row["direction"]


def _dropped(row, c) -> bool:
    """Arm D's rule on the baseline plan: d > c."""
    return row["d"] is not None and row["d"] > float(c) + 1e-9


def _arm_s_counts(rows, key) -> dict:
    changed = sum(1 for r in rows if r["changed"][key])
    rollback = sum(1 for r in rows if r["rollback"][key])
    return {"applies": changed + rollback, "changed": changed, "rollback": rollback}


def _stratum(rows, cells) -> dict:
    clamped = [r for r in rows if r["clamped"]]
    buckets = Counter(_bucket(r["d"]) for r in clamped)
    return {"plans": len(rows), "clamped": len(clamped),
            "d_buckets": dict(sorted(buckets.items(), key=lambda kv: float(kv[0].split("-")[0]))),
            "arm_s": {cell_key(c): _arm_s_counts(rows, cell_key(c)) for c in cells},
            "arm_d": {cell_key(c): {"dropped": sum(1 for r in rows if _dropped(r, c))}
                      for c in cells}}


def _sets(rows, cells) -> dict:
    return {"arm_s": {cell_key(c): frozenset(_row_id(r) for r in rows if r["changed"][cell_key(c)])
                      for c in cells},
            "arm_d": {cell_key(c): frozenset(_row_id(r) for r in rows if _dropped(r, c))
                      for c in cells}}


def _identical_adjacent(by_key) -> list:
    keys = list(by_key)
    return [[a, b] for a, b in zip(keys, keys[1:]) if by_key[a] == by_key[b]]


def _strata(rows) -> dict:
    out: dict = {}
    for row in rows:
        out.setdefault(f"{row['horizon_key']}/{row['direction']}", []).append(row)
    return out


def stage_minus1(rows, cells=C_STEPS) -> dict:
    """The census verdict. An arm whose every cell changes no plan is
    refused:zero-diff (the v123 precedent). `identical_adjacent` names grid
    neighbours that change the identical plan set -- a degenerate axis is
    reported before any outcome is read, never discovered after."""
    cells = tuple(cells)
    sets = _sets(rows, cells)
    verdicts = {arm: "REACHABLE" if any(sets[name].values()) else "refused:zero-diff"
                for arm, name in (("S", "arm_s"), ("D", "arm_d"))}
    return {"stage": -1, "arm": ARM, "verdict": verdicts["S"], "verdicts": verdicts,
            "cells": [cell_key(c) for c in cells], "totals": _stratum(rows, cells),
            "by_stratum": {k: _stratum(v, cells) for k, v in sorted(_strata(rows).items())},
            "identical_adjacent": {name: _identical_adjacent(sets[name]) for name in sets}}


# --- Stage 0 -------------------------------------------------------------------

def stage0(rows, cells=C_STEPS) -> dict:
    """Paired MDE precheck on TRAIN rows (v129's _mde_cell). Any cell over the
    ceiling closes the arm UNDERPOWERED, because Stage 1 may select any cell."""
    out = [_mde_cell(rows, cell_key(c)) for c in cells]
    verdict = "POWERED" if all(cell["powered"] for cell in out) else "UNDERPOWERED"
    return {"stage": 0, "arm": ARM, "verdict": verdict,
            "mde_ceiling_r": MDE_CEILING_R, "power": MDE_POWER, "cells": out}


# --- Stage 1 -------------------------------------------------------------------

def _neighbours(c, cells) -> list:
    index = cells.index(c)
    return [cells[j] for j in (index - 1, index + 1) if 0 <= j < len(cells)]


def _selection_cell(rows, c, n_resamples, seed) -> dict:
    key = cell_key(c)
    baseline, component = arm_trades(rows, key)
    result = evaluate_harvest(baseline, component, stage="walkforward",
                              n_resamples=n_resamples, seed=seed, cluster=CLUSTER)
    boot = bootstrap_delta(baseline, component, delta_expectancy_r,
                           n_resamples=n_resamples, seed=seed, cluster=CLUSTER)
    eligible = all(result.clause(name).verdict == "PASS" for name in ELIGIBILITY_CLAUSES)
    return {"cell": key, "c": float(c), "eligible": eligible, "delta_expr": boot.point,
            "lo95": boot.lo, "hi95": boot.hi, "gate": render_json(result)}


def stage1(rows, cells=C_STEPS, *, n_resamples: int = BOOTSTRAP_RESAMPLES,
           seed: int = 42) -> dict:
    """TRAIN plateau selection: the eligible cell with the highest lower-95%
    dExpR whose +/-1-step neighbours in c are all eligible. A tie goes to the
    smaller c (max() keeps the first maximum)."""
    cells = tuple(float(c) for c in cells)
    table = {c: _selection_cell(rows, c, n_resamples, seed) for c in cells}
    for c, cell in table.items():
        cell["plateau"] = cell["eligible"] and all(
            table[other]["eligible"] for other in _neighbours(c, cells))
    pool = [cell for cell in table.values() if cell["plateau"]]
    selected = None
    if pool:
        best = max(pool, key=lambda cell: cell["lo95"])
        selected = {"cell": best["cell"], "c": best["c"]}
    return {"stage": 1, "arm": ARM, "verdict": "SELECTED" if selected else "NO_ELIGIBLE_CELL",
            "selected": selected, "cells": list(table.values())}


# --- Stage 2 -------------------------------------------------------------------

def stage2(rows, key) -> dict:
    """v129's free walk-forward folds (four TRAIN calendar years) for the
    selected cell: FAIL when more than half the measurable folds reverse."""
    return _v129_stage2(rows, ARM, key)


# --- Stage 3 -------------------------------------------------------------------

def stage3(rows, key, *, n_resamples: int = BOOTSTRAP_RESAMPLES, seed: int = 42) -> dict:
    """The one VALIDATION shot for the selected cell: all four harvest clauses,
    week-clustered, with v129's per-ticker label-swap permutation p."""
    baseline, component = arm_trades(rows, key)
    p = sign_flip_p(baseline, component)
    result = evaluate_harvest(baseline, component, stage="validation", permutation_p=p,
                              n_resamples=n_resamples, seed=seed, cluster=CLUSTER)
    return {"stage": 3, "arm": ARM, "cell": key, "verdict": result.verdict,
            "permutation_p": p, "gate": render_json(result)}


# --- disclosures (spec § Reporting) --------------------------------------------------

def _median_d_changed(rows, key):
    ds = [r["d"] for r in rows if r["changed"][key] and r["d"] is not None]
    return statistics.median(ds) if ds else None


def _sided_count(records, field) -> int:
    return sum(1 for record in records if record[field])


def _arm_s_disclosures(rows, key, base_records, cell_records) -> dict:
    only_base, only_cell = _triggered_once(rows, key)
    return {
        "changed": sum(1 for r in rows if r["changed"][key]),
        "rollback": sum(1 for r in rows if r["rollback"][key]),
        "median_d_changed": _median_d_changed(rows, key),
        "gap_through": {"baseline": _sided_count(base_records, "gap_through"),
                        "component": _sided_count(cell_records, "gap_through")},
        "fill_beyond_ceiling": {"baseline": _sided_count(base_records, "fill_beyond_ceiling"),
                                "component": _sided_count(cell_records, "fill_beyond_ceiling")},
        "only_baseline_triggered": only_base, "only_cell_triggered": only_cell,
        "per_horizon_n": dict(Counter(r["horizon_key"] for r in rows)),
    }


def report(rows, key, *, n_resamples: int = BOOTSTRAP_RESAMPLES, seed: int = 42) -> dict:
    """Everything the spec asks to be reported for one cell. Informational:
    nothing here gates."""
    baseline, component = arm_trades(rows, key)
    base_records, cell_records = _sides(rows, key)
    boot = bootstrap_delta(baseline, component, delta_expectancy_r,
                           n_resamples=n_resamples, seed=seed, cluster=CLUSTER)
    wr_base, wr_cell = win_rate(baseline), win_rate(component)
    return {
        "arm": ARM, "cell": key,
        "n_baseline": len(baseline), "n_component": len(component),
        "expr_baseline": expectancy_r(baseline), "expr_component": expectancy_r(component),
        "delta_expr": boot.point, "delta_expr_lo95": boot.lo, "delta_expr_hi95": boot.hi,
        "wr_baseline": wr_base, "wr_component": wr_cell, "delta_wr_pp": _pp(wr_cell, wr_base),
        "flips": _flips(rows, key),
        "exit_mix": {"baseline": dict(Counter(r["exit_mix"] for r in base_records)),
                     "component": dict(Counter(r["exit_mix"] for r in cell_records))},
        "median_planned_rr": {"baseline": median_planned_rr(baseline),
                              "component": median_planned_rr(component)},
        **_arm_s_disclosures(rows, key, base_records, cell_records),
    }
```

- [ ] **Step 5: Run the tests**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_confluence_stop_funnel.py`, then `python scripts/dev/testrun.py file tests/backtesting/test_acceptance_exit_funnel.py`
Expected: both pass. The v129 file is unchanged and must stay green.

- [ ] **Step 6: Complexity**

Run: `python -m radon cc -s -n C swingbot/core/backtesting/confluence_stop_funnel.py`
Expected: nothing listed.

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/backtesting/confluence_stop_funnel.py tests/backtesting/confluence_stop_rows.py tests/backtesting/test_confluence_stop_funnel.py
git commit -m "feat(v139): confluence_stop_funnel -- census verdicts, week-clustered harvest Stages 0-3

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V139-10: `measure_confluence_stop.py` — the arm S stage driver

**Files:**
- Create: `scripts/backtest/measure_confluence_stop.py`
- Create: `tests/scripts/test_measure_confluence_stop.py`

**Interfaces:**
- Consumes: `confluence_stop_replay.replay_entries` / `census` / `C_STEPS` / `cell_key` (V139-8), `confluence_stop_funnel` (V139-9), `measure_arms.cached_universe` / `load_frame` (V139-3), `backtest_scenarios._resolve_replay_workers`, `LEGACY_HORIZONS`.
- Produces: the CLI used by V139-11..13: `python scripts/backtest/measure_confluence_stop.py --stage {-1,0,1,2,3} [--out-dir D] [--preregistration P] [--tickers N] [--workers N] [--resamples N]`.
  - Outputs in `docs/superpowers/results/v139/`:
    - `2026-10-08-v139-armS-stage{M1,0,1,2,3}.json`
    - `2026-10-08-v139-armS-{census-train,train,validation}-rows.json`
  - Progress file: `logs/measure_confluence_stop.<census|rows>.progress`.
  - Exit code 0 on an advancing verdict (`REACHABLE`, `POWERED`, `SELECTED`, `PASS`), else 1.

- [ ] **Step 1: Write the failing tests**

Create `tests/scripts/test_measure_confluence_stop.py`:

```python
"""v139 arm S driver: the census before any outcome, the stage order, the
one-shot refusal and the selected-cell-only VALIDATION replay. `build` is
faked; no replay runs."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "backtest"))
import measure_confluence_stop as mcs  # noqa: E402

from swingbot.core.backtesting import confluence_stop_funnel as funnel
from tests.backtesting.confluence_stop_rows import census_row, lifted_s_rows

N = 200
PLATEAU = {"c3": 0.1, "c4": 0.3, "c5": 0.2}
CENSUS = [census_row(2.5, (True, True, True), ticker="T01"),
          census_row(3.5, (False, True, True), ticker="T02"),
          census_row(4.5, (False, False, True), ticker="T03")]


def _fake_build(calls, census=None):
    def build(kind, window, cells):
        calls.append((kind, tuple(window), [float(c) for c in cells]))
        if kind == "census":
            return CENSUS if census is None else census
        keys = [f"c{float(c):g}" for c in cells]
        return lifted_s_rows({key: PLATEAU[key] for key in keys}, year=int(window[0][:4]))
    return build


def _run(stage, out_dir, calls, **kw):
    return mcs.run_stage(stage, out_dir, build=_fake_build(calls, **kw), n_resamples=N)


def test_paths():
    assert mcs.stage_path("d", -1).name == "2026-10-08-v139-armS-stageM1.json"
    assert mcs.stage_path("d", 3).name == "2026-10-08-v139-armS-stage3.json"
    assert mcs.rows_path("d", "train").name == "2026-10-08-v139-armS-train-rows.json"


def test_stage0_refuses_without_the_census(tmp_path):
    with pytest.raises(SystemExit, match="run stage -1 first"):
        _run(0, tmp_path, [])


def test_a_zero_diff_census_closes_the_arm(tmp_path):
    calls = []
    assert _run(-1, tmp_path, calls, census=[census_row(None)])["verdict"] == "refused:zero-diff"
    with pytest.raises(SystemExit, match="closed at stage -1 with refused:zero-diff"):
        _run(0, tmp_path, calls)


def test_census_reads_plans_only_then_stage0_builds_train_rows_once(tmp_path):
    calls = []
    assert _run(-1, tmp_path, calls)["verdict"] == "REACHABLE"
    assert calls == [("census", funnel.TRAIN, [3.0, 4.0, 5.0])]
    assert _run(0, tmp_path, calls)["verdict"] == "POWERED"
    assert calls[1] == ("rows", funnel.TRAIN, [3.0, 4.0, 5.0])
    _run(0, tmp_path, calls)
    assert len(calls) == 2          # the rows file is reused, not rebuilt


def test_full_chain_replays_validation_for_the_selected_cell_only(tmp_path):
    calls = []
    for stage in (-1, 0, 1, 2):
        assert _run(stage, tmp_path, calls)["verdict"] in mcs.ADVANCING
    out = _run(3, tmp_path, calls)
    assert (out["verdict"], out["cell"]) == ("PASS", "c4")
    assert calls[-1] == ("rows", funnel.VALIDATION, [4.0])
    assert out["report"]["cell"] == "c4"


def test_stage3_refuses_when_output_exists(tmp_path):
    calls = []
    for stage in (-1, 0, 1, 2, 3):
        _run(stage, tmp_path, calls)
    with pytest.raises(SystemExit, match="one VALIDATION shot is spent"):
        _run(3, tmp_path, calls)


def test_cli_refusals(tmp_path, capsys):
    assert mcs.main(["--stage", "3", "--out-dir", str(tmp_path)]) == 1
    assert "refused:no-preregistration" in capsys.readouterr().err
    prereg = tmp_path / "prereg.md"
    prereg.write_text("x", encoding="utf-8")
    assert mcs.main(["--stage", "3", "--tickers", "3", "--out-dir", str(tmp_path),
                     "--preregistration", str(prereg)]) == 1
    assert "refused:partial-validation" in capsys.readouterr().err
    assert mcs.main(["--stage", "0", "--tickers", "3"]) == 1
    assert "refused:smoke-run" in capsys.readouterr().err


def test_cli_runs_the_census_stage(tmp_path, monkeypatch):
    monkeypatch.setattr(mcs, "build", lambda kind, window, cells, **kw: CENSUS)
    assert mcs.main(["--stage", "-1", "--out-dir", str(tmp_path)]) == 0
    assert mcs.stage_path(tmp_path, -1).exists()
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_measure_confluence_stop.py`
Expected: FAIL: `ModuleNotFoundError: No module named 'measure_confluence_stop'`.

- [ ] **Step 3: Implement**

Create `scripts/backtest/measure_confluence_stop.py`:

```python
#!/usr/bin/env python3
"""v139 arm S (confluence structural stop): Stage -1..3 driver, one stage per call.

  stage -1  census of plans on TRAIN, no outcome  -> REACHABLE | refused:zero-diff
            (the same file carries arm D's census numbers, disclosure only)
  stage 0   paired MDE precheck on TRAIN           -> POWERED | UNDERPOWERED
  stage 1   TRAIN plateau selection over c         -> SELECTED | NO_ELIGIBLE_CELL
  stage 2   TRAIN calendar-year folds              -> PASS | FAIL
  stage 3   ONE-SHOT VALIDATION, selected c only   -> PASS | FAIL

Each stage reads the previous stage's verdict JSON and refuses without the
verdict it needs, so a closed arm cannot be advanced by hand. TRAIN rows are
replayed once (stage 0) and reused. Stage 3 is refused when its output exists.
The universe is measure_arms.cached_universe(): in a worktree set
MEASURE_ARMS_UNIVERSE=cache and BACKTEST_CACHE_DIR.

PROGRESS: a flushed line per ticker, plus
logs/measure_confluence_stop.<census|rows>.progress (percent, rewritten per
ticker, deleted on completion).

Run: python scripts/backtest/measure_confluence_stop.py --stage -1
"""
from __future__ import annotations

import argparse
import functools
import json
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "scripts" / "data"), str(ROOT / "scripts" / "backtest")]

from swingbot.core.backtesting import confluence_stop_funnel as funnel  # noqa: E402
from swingbot.core.backtesting import confluence_stop_replay as csr  # noqa: E402
from swingbot.core.backtesting.acceptance import BOOTSTRAP_RESAMPLES  # noqa: E402
from swingbot.core.backtesting.backtest_scenarios import _resolve_replay_workers  # noqa: E402
from swingbot.core.market.strategy_types import LEGACY_HORIZONS  # noqa: E402

RESULTS = ROOT / "docs" / "superpowers" / "results" / "v139"
LOG_DIR = ROOT / "logs"
PREFIX = "2026-10-08-v139-armS"
#: stage -> (the stage it consumes, the verdict that stage must carry).
REQUIRES = {0: (-1, "REACHABLE"), 1: (0, "POWERED"), 2: (1, "SELECTED"), 3: (2, "PASS")}
ADVANCING = ("REACHABLE", "POWERED", "SELECTED", "PASS")
KINDS = {"rows": csr.replay_entries, "census": csr.census}


def stage_path(out_dir, stage) -> Path:
    label = "M1" if stage == -1 else str(stage)
    return Path(out_dir) / f"{PREFIX}-stage{label}.json"


def rows_path(out_dir, name) -> Path:
    return Path(out_dir) / f"{PREFIX}-{name}-rows.json"


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write(path, blob, indent=1) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(blob, indent=indent), encoding="utf-8")


def _refuse(message):
    raise SystemExit(f"refused: {message}")


# --- replay ------------------------------------------------------------------

def _worker(task):
    """One ticker, every legacy horizon -- the process-pool entry point."""
    kind, ticker, window, cells = task
    from measure_arms import load_frame
    frame = load_frame(ticker)
    if frame is None:
        return ticker, []
    return ticker, KINDS[kind](ticker, frame, LEGACY_HORIZONS,
                               start=window[0], end=window[1], cells=cells)


def _write_progress(path, done, total) -> None:
    try:
        path.write_text(f"{done}/{total} tickers ({done / total * 100:.0f}%)\n",
                        encoding="utf-8")
    except OSError:
        pass


def universe() -> list[str]:
    from measure_arms import cached_universe
    return cached_universe()


def _run_tasks(tasks, record, workers) -> None:
    n_workers = _resolve_replay_workers(workers)
    if n_workers <= 1 or len(tasks) <= 1:
        for task in tasks:
            record(*_worker(task))
        return
    with ProcessPoolExecutor(max_workers=n_workers) as pool:
        for future in as_completed([pool.submit(_worker, task) for task in tasks]):
            record(*future.result())


def build(kind, window, cells, *, tickers=None, workers=None) -> list:
    """Replay every universe ticker; rows come back in ticker order, so the
    output is identical whatever order the pool finishes in."""
    names = universe()
    names = names[:tickers] if tickers else names
    tasks = [(kind, ticker, tuple(window), tuple(float(c) for c in cells)) for ticker in names]
    LOG_DIR.mkdir(exist_ok=True)
    progress = LOG_DIR / f"measure_confluence_stop.{kind}.progress"
    by_ticker: dict = {}

    def record(ticker, rows):
        by_ticker[ticker] = rows
        print(f"  [{kind} {window[0]}..{window[1]}] {len(by_ticker)}/{len(tasks)} "
              f"{ticker}: {len(rows)} entries", flush=True)
        _write_progress(progress, len(by_ticker), len(tasks))

    _run_tasks(tasks, record, workers)
    progress.unlink(missing_ok=True)
    return [row for ticker in sorted(by_ticker) for row in by_ticker[ticker]]


# --- stages ------------------------------------------------------------------

def _previous(out_dir, stage) -> dict:
    """The verdict JSON this stage consumes, or a refusal."""
    needed_stage, needed_verdict = REQUIRES[stage]
    path = stage_path(out_dir, needed_stage)
    if not path.exists():
        _refuse(f"stage {stage} needs {path.name} -- run stage {needed_stage} first")
    previous = _load(path)
    if previous["verdict"] != needed_verdict:
        _refuse(f"arm S closed at stage {needed_stage} with {previous['verdict']} "
                f"-- stage {stage} does not run")
    return previous


def _saved(out_dir, name, kind, window, cells, build_fn) -> list:
    """Rows from the rows file, building (and saving) them when absent."""
    path = rows_path(out_dir, name)
    if not path.exists():
        _write(path, build_fn(kind, window, cells), indent=None)
    return _load(path)


def _train_rows(out_dir, build_fn) -> list:
    return _saved(out_dir, "train", "rows", funnel.TRAIN, csr.C_STEPS, build_fn)


def _stage_m1(out_dir, build_fn, n_resamples) -> dict:
    rows = _saved(out_dir, "census-train", "census", funnel.TRAIN, csr.C_STEPS, build_fn)
    return funnel.stage_minus1(rows)


def _stage0(out_dir, build_fn, n_resamples) -> dict:
    _previous(out_dir, 0)
    return funnel.stage0(_train_rows(out_dir, build_fn))


def _stage1(out_dir, build_fn, n_resamples) -> dict:
    _previous(out_dir, 1)
    rows = _train_rows(out_dir, build_fn)
    out = funnel.stage1(rows, n_resamples=n_resamples)
    out["reports"] = [funnel.report(rows, csr.cell_key(c), n_resamples=n_resamples)
                      for c in csr.C_STEPS]
    return out


def _stage2(out_dir, build_fn, n_resamples) -> dict:
    selected = _previous(out_dir, 2)["selected"]
    return funnel.stage2(_train_rows(out_dir, build_fn), selected["cell"])


def _stage3(out_dir, build_fn, n_resamples) -> dict:
    _previous(out_dir, 3)
    selected = _load(stage_path(out_dir, 1))["selected"]
    rows = _saved(out_dir, "validation", "rows", funnel.VALIDATION, [selected["c"]], build_fn)
    out = funnel.stage3(rows, selected["cell"], n_resamples=n_resamples)
    out["report"] = funnel.report(rows, selected["cell"], n_resamples=n_resamples)
    return out


_STAGES = {-1: _stage_m1, 0: _stage0, 1: _stage1, 2: _stage2, 3: _stage3}


def run_stage(stage, out_dir, *, build, n_resamples: int = BOOTSTRAP_RESAMPLES) -> dict:
    """Run one stage and write its verdict JSON. Stages -1..2 are TRAIN-only
    and deterministic, so they may be re-run; stage 3 may not."""
    out_dir = Path(out_dir)
    target = stage_path(out_dir, stage)
    if stage == 3 and target.exists():
        _refuse(f"{target.name} exists -- arm S's one VALIDATION shot is spent")
    out = _STAGES[stage](out_dir, build, n_resamples)
    _write(target, out)
    return out


# --- CLI ---------------------------------------------------------------------

def _cli_refusal(args) -> str | None:
    if args.tickers and args.stage == 3:
        return ("refused:partial-validation -- stage 3 is the one shot and runs "
                "the full universe; drop --tickers")
    if args.tickers and args.out_dir.resolve() == RESULTS.resolve():
        return ("refused:smoke-run -- --tickers needs a scratch --out-dir, never "
                "the committed results directory")
    if args.stage == 3 and not (args.preregistration and args.preregistration.exists()):
        return ("refused:no-preregistration -- stage 3 needs --preregistration "
                "<committed doc>. This is the one shot.")
    return None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stage", required=True, type=int, choices=sorted(_STAGES))
    parser.add_argument("--out-dir", type=Path, default=RESULTS)
    parser.add_argument("--preregistration", type=Path, default=None)
    parser.add_argument("--tickers", type=int, default=None)
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--resamples", type=int, default=BOOTSTRAP_RESAMPLES)
    args = parser.parse_args(argv)
    refusal = _cli_refusal(args)
    if refusal:
        print(refusal, file=sys.stderr)
        return 1
    build_fn = functools.partial(build, tickers=args.tickers, workers=args.workers)
    out = run_stage(args.stage, args.out_dir, build=build_fn, n_resamples=args.resamples)
    print(f"arm S stage {args.stage}: {out['verdict']} -> {stage_path(args.out_dir, args.stage)}",
          flush=True)
    return 0 if out["verdict"] in ADVANCING else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests**

Run: `python scripts/dev/testrun.py file tests/scripts/test_measure_confluence_stop.py`
Expected: all pass. If argparse rejects `--stage -1` as an option, the parser gained an option string that looks like a negative number. Keep every option non-numeric. Do not switch to a string choice: the tests pin `-1`.

- [ ] **Step 5: Smoke-time the census (plans only, no outcome) to size the real runs**

Invoke `backtest-gate` first. This reads no outcome: the census simulates no exit (pinned in V139-8).

```bash
export BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache
export MEASURE_ARMS_UNIVERSE=cache
time python scripts/backtest/measure_confluence_stop.py --stage -1 --tickers 3 --out-dir logs/v139-smoke
```

Record the wall time per ticker and the universe size (`python -c "import sys; sys.path[:0]=['scripts/backtest','scripts/data']; import measure_arms as m; print(len(m.cached_universe()))"` with the same two variables set). The full census runs about that per-ticker time × universe size ÷ workers. The stage 0 rows run adds the exit walks, roughly 1.2–1.5× the census. Note both estimates in the commit body: V139-11 and V139-12 hand them to `backtest-runner`. Then `rm -r logs/v139-smoke`. Do **not** run stage 0 here: that would read TRAIN outcomes before the pre-registration is committed.

- [ ] **Step 6: Complexity**

Run: `python -m radon cc -s -n C scripts/backtest/measure_confluence_stop.py`
Expected: nothing listed.

- [ ] **Step 7: Commit**

```bash
git add scripts/backtest/measure_confluence_stop.py tests/scripts/test_measure_confluence_stop.py
git commit -m "feat(v139): measure_confluence_stop stage driver (census, Stages 0-3, one-shot guard)

Census smoke: <s/ticker> on 3 tickers; universe <N>; est. census <min>, train rows <min>.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
