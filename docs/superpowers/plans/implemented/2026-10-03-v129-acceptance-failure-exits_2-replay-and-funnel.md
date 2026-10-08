# v129 — Part 2: replay library, funnel, driver script

> Index, Global Constraints, Review Focus and `## Parallelisation`: `2026-10-03-v129-acceptance-failure-exits_0-index.md`. Work in the worktree `.claude/worktrees/2026-10-03-v129-acceptance-failure-exits` on branch `2026-10-03-v129-acceptance-failure-exits`. Every path below is relative to that worktree. Never edit the main tree.

# Phase 3 — Measurement instruments (Group D, sequential)

### Task V129-7: `acceptance_replay` — build each entry once, re-simulate it per cell

**Files:**
- Create: `swingbot/core/backtesting/acceptance_replay.py`
- Create: `tests/backtesting/test_acceptance_replay.py`

**Interfaces:**
- Consumes:
  - `acceptance_levels.apply_arm_z(plan, atr_val, m, b) -> bool`, `apply_arm_b(plan, atr_val, b) -> bool`, `atr_at(df, index, entry) -> float`, `enabled_arms() -> frozenset`, `ARM_Z`, `ARM_B`, `BREAK_RETEST` (V129-4/5).
  - `exit_sim.simulate_exit(df, signal_index, plan, *, scale_out)` with the `"acceptance_exit"` leg reason (V129-6).
  - `backtest_scenarios.replay_scenarios(ticker, df, horizon_key, *, gates=None)`, `backtest.run_backtest`, `backtest._bt_plan`, `acceptance.arm_trade_from_plan`.
- Produces (V129-8 and V129-9 consume all of these):
  - `M_STEPS = (0.5, 1.0, 1.5)`, `B_STEPS = (0.0, 0.25)`.
  - `CELLS = {"Z": ((0.5, 0.0), (0.5, 0.25), (1.0, 0.0), (1.0, 0.25), (1.5, 0.0), (1.5, 0.25)), "B": ((None, 0.0), (None, 0.25))}`.
  - `cell_key(m, b) -> str`: `"m0.5_b0"`, `"m1_b0.25"`, `"m1.5_b0"` for Z; `"b0"`, `"b0.25"` for B.
  - `UNTRIGGERED = ("not_triggered", "no_trade")`.
  - `entry_row(arm, df, i, plan, atr_val, cells) -> dict | None`.
  - `replay_entries(arm, ticker, df, horizons, *, start=None, end=None, cells=None, gates=None) -> list[dict]`.
- **Row shape** (plain JSON types, so a row survives `json.dumps`/`loads` unchanged):

```python
{"arm": "Z", "ticker": "AAPL", "horizon_key": "4w", "entry_date": "2021-05-03",
 "direction": "bullish", "eligible": True,
 "baseline": RECORD_OR_NONE,
 "cells": {"m0.5_b0": RECORD_OR_NONE, ...}}
# RECORD = the nine ArmTrade fields (ticker, strategy, horizon_key, entry_date,
# outcome, r_multiple, planned_rr, source, direction) plus
# "exit_mix": str and "gap_through": bool. None = that side never triggered.
```

Design rules this task fixes:
- **Entries are built once, with the flag off.** `replay_entries` raises if `enabled_arms()` is non-empty. A plan built with the flag on would already carry one cell's stop.
- **Arm Z entries** are `replay_scenarios(ticker, df, horizon_key)` with live `ScanParams` (`gates=None`; the `gates` argument exists only so tests can use a small fixture).
- **Arm B entries** are the plans `run_backtest(..., "Break & Retest", exit_model="v2", scale_out=True, tp2_mode="levels")` builds. They are captured by wrapping `backtest._bt_plan` for the duration of that one call, so the plan is exactly the one the backtest simulated (same `tp2`, same one-at-a-time population). Reconstructing it would re-derive `tp2` from a different level-map cache bucket.
- **A not-eligible Z plan stays in both arms unchanged.** Its cell record is the baseline record (ΔR = 0). The spec counts these plans, never drops them.
- **A row is dropped only when neither the baseline nor any cell triggered** (Review Focus 1). A wider Z stop changes stop-entry invalidation, so one side can be `None` while the other traded.
- `exit_mix` is the last leg's reason for a one-leg exit (`stop`, `tp1`, `breakeven_stop`, `acceptance_exit`, `stall_exit`, `timeout`, `gap_through_stop`) and `"tp1+" + reason` for a two-leg exit.
- `gap_through` is true when the exit leg's reason is `"stop"` and that bar's open was already at or beyond `plan.stop_loss`.

- [ ] **Step 1: Write the failing tests**

```python
"""v129 replay: one entry, simulated under today's exit (baseline) and under
each grid cell. Hand-built bars; ATR is passed in as 2.0 so every number is
checkable by hand. entry 100 (market, bar 0), level 99, tp1 104.
Cell m0.5_b0: disaster stop max(99 - 1, 98) = 98, close threshold 99."""
import pytest

from swingbot import config
from swingbot.core.backtesting import backtest_scenarios as bs
from swingbot.core.backtesting.acceptance_replay import (
    B_STEPS, CELLS, M_STEPS, UNTRIGGERED, cell_key, entry_row, replay_entries,
)
from swingbot.core.backtesting.backtest import run_backtest
from swingbot.core.planning.exit_sim import simulate_exit
from tests.backtesting.test_backtest_scenarios import GATES, _structured_df
from tests.fixtures.ohlcv_parity import load_ohlcv
from tests.helpers import make_ohlcv
from tests.planning.test_exit_sim_single import _plan

ATR = 2.0


def _zplan(**kw):
    base = dict(source="confluence", direction="bullish", stop_loss=99.0, tp1=104.0,
                acceptance_level=99.0)
    base.update(kw)
    return _plan(**base)


def test_grid_and_cell_keys():
    assert M_STEPS == (0.5, 1.0, 1.5) and B_STEPS == (0.0, 0.25)
    assert [cell_key(m, b) for m, b in CELLS["Z"]] == [
        "m0.5_b0", "m0.5_b0.25", "m1_b0", "m1_b0.25", "m1.5_b0", "m1.5_b0.25"]
    assert [cell_key(m, b) for m, b in CELLS["B"]] == ["b0", "b0.25"]


def test_sweep_and_reclaim_flips_a_baseline_loss():
    # Bar 1 wicks to 98.6 (through the level, not the disaster stop) and
    # closes back above 99. Bar 2 reaches TP1.
    df = make_ohlcv([100.0, (99.5, 100.0, 98.6, 99.6), (99.6, 104.5, 99.5, 104.2)])
    row = entry_row("Z", df, 0, _zplan(), ATR, CELLS["Z"])
    assert row["eligible"] is True
    assert row["baseline"]["outcome"] == "loss"
    assert row["baseline"]["r_multiple"] == -1.0
    assert row["baseline"]["exit_mix"] == "stop"
    assert row["baseline"]["planned_rr"] == pytest.approx(4.0)
    cell = row["cells"]["m0.5_b0"]
    assert cell["outcome"] == "win"
    assert cell["exit_mix"].startswith("tp1+")
    assert cell["planned_rr"] == pytest.approx(2.0)   # 1R is entry -> disaster stop


def test_close_through_exits_with_the_acceptance_reason_and_buffer_defers_it():
    df = make_ohlcv([100.0, (99.5, 99.8, 98.4, 98.7)])
    row = entry_row("Z", df, 0, _zplan(), ATR, CELLS["Z"])
    tight = row["cells"]["m0.5_b0"]            # threshold 99: 98.7 closes through
    assert tight["outcome"] == "loss"
    assert tight["exit_mix"] == "acceptance_exit"
    assert tight["r_multiple"] == pytest.approx(-0.65)
    buffered = row["cells"]["m0.5_b0.25"]      # threshold 98.5: 98.7 does not
    assert buffered["exit_mix"] == "timeout"
    assert buffered["r_multiple"] == pytest.approx(-0.65)


def test_not_eligible_plan_keeps_todays_exit_in_every_cell():
    # Level 97 is 3% from entry: beyond the 2% cap, so the clamp moved the stop.
    df = make_ohlcv([100.0, (99.5, 99.8, 98.0, 98.4)])
    row = entry_row("Z", df, 0, _zplan(stop_loss=98.25, acceptance_level=97.0), ATR, CELLS["Z"])
    assert row["eligible"] is False
    assert all(record == row["baseline"] for record in row["cells"].values())
    assert row["baseline"]["exit_mix"] == "stop"


def test_gap_through_the_disaster_stop_is_flagged_and_still_books_minus_one():
    df = make_ohlcv([100.0, (97.0, 97.5, 96.5, 97.2)])
    row = entry_row("Z", df, 0, _zplan(), ATR, CELLS["Z"])
    cell = row["cells"]["m0.5_b0"]
    assert cell["r_multiple"] == -1.0
    assert cell["gap_through"] is True
    assert row["baseline"]["gap_through"] is True


def _stop_entry_plan():
    return _zplan(entry_type="stop_entry", trigger_price=100.0, expiry_bars=3)


def test_replay_keeps_rows_where_only_a_cell_triggered():
    # Bar 1 closes at 98.7: through today's stop (99, pending invalidated) but
    # not through the disaster stop (98). Bar 2 triggers, bar 3 reaches TP1.
    df = make_ohlcv([(99.5, 99.8, 99.3, 99.6), (99.5, 99.7, 98.5, 98.7),
                     (98.8, 100.6, 98.7, 100.4), (100.4, 104.5, 100.2, 104.2)])
    row = entry_row("Z", df, 0, _stop_entry_plan(), ATR, CELLS["Z"])
    assert row is not None
    assert row["baseline"] is None
    assert row["cells"]["m0.5_b0"]["outcome"] == "win"


def test_entry_row_is_none_when_nothing_triggered():
    df = make_ohlcv([(99.5, 99.8, 99.3, 99.6), (99.5, 99.7, 98.5, 98.7)])
    assert entry_row("Z", df, 0, _stop_entry_plan(), ATR, CELLS["Z"]) is None


def test_arm_b_adds_the_close_exit_and_leaves_the_stop_alone():
    plan = _plan(strategy="Break & Retest", direction="bullish", stop_loss=96.0,
                 tp1=108.0, acceptance_level=99.0)
    df = make_ohlcv([100.0, (99.5, 99.8, 98.4, 98.7)])
    row = entry_row("B", df, 0, plan, ATR, CELLS["B"])
    assert set(row["cells"]) == {"b0", "b0.25"}
    assert row["baseline"]["exit_mix"] == "timeout"
    assert row["cells"]["b0"]["exit_mix"] == "acceptance_exit"
    assert row["cells"]["b0"]["outcome"] == "loss"
    assert row["cells"]["b0"]["r_multiple"] == pytest.approx(-0.325)
    assert row["cells"]["b0.25"] == row["baseline"]          # 98.7 is above 98.5
    assert row["cells"]["b0"]["planned_rr"] == row["baseline"]["planned_rr"] == pytest.approx(2.0)


def test_entry_row_does_not_mutate_the_shared_plan():
    plan = _zplan()
    entry_row("Z", make_ohlcv([100.0, (99.5, 100.0, 98.6, 99.6)]), 0, plan, ATR, CELLS["Z"])
    assert plan.stop_loss == 99.0 and plan.acceptance_close_below is None


def test_replay_refuses_to_run_with_the_flag_on(monkeypatch):
    monkeypatch.setattr(config, "ACCEPTANCE_EXIT_ENABLED", True)
    monkeypatch.setattr(config, "ACCEPTANCE_EXIT_ARMS", "Z,B")
    with pytest.raises(RuntimeError, match="ACCEPTANCE_EXIT_ENABLED"):
        replay_entries("Z", "AAPL", make_ohlcv([100.0] * 5), ("4w",))


@pytest.mark.slow
def test_confluence_replay_baseline_is_todays_exit():
    df = _structured_df()
    rows = replay_entries("Z", "AAPL", df, ("4w",), gates=GATES)
    assert rows
    by_key = {(row["entry_date"], row["direction"]): row for row in rows}
    keys = {cell_key(m, b) for m, b in CELLS["Z"]}
    for i, plan in bs.replay_scenarios("AAPL", df, "4w", gates=GATES):
        res = simulate_exit(df, i, plan, scale_out=True)
        row = by_key.get((str(df.index[i].date()), plan.direction))
        if res.outcome in UNTRIGGERED:
            assert row is None or row["baseline"] is None
            continue
        assert row["baseline"]["outcome"] == res.outcome
        assert row["baseline"]["r_multiple"] == res.r_total
        assert set(row["cells"]) == keys


@pytest.mark.slow
def test_break_retest_replay_baseline_matches_run_backtest():
    df = load_ohlcv("DELL")
    summary = run_backtest("DELL", df, "Break & Retest", "2m",
                           exit_model="v2", scale_out=True, tp2_mode="levels")
    rows = replay_entries("B", "DELL", df, ("2m",))
    assert summary.trades, "fixture must trade"
    assert [(r["entry_date"], r["baseline"]["outcome"], round(r["baseline"]["r_multiple"], 3))
            for r in rows] == [(t.entry_date, t.outcome, t.r_multiple) for t in summary.trades]
    assert all(set(r["cells"]) == {"b0", "b0.25"} for r in rows)


def test_window_filters_on_the_signal_date():
    df = load_ohlcv("DELL")
    everything = replay_entries("B", "DELL", df, ("2m",))
    first = everything[0]["entry_date"]
    only_first = replay_entries("B", "DELL", df, ("2m",), start=first, end=first)
    assert [r["entry_date"] for r in only_first] == [first]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_acceptance_replay.py`
Expected: FAIL, `ModuleNotFoundError: No module named 'swingbot.core.backtesting.acceptance_replay'`.

- [ ] **Step 3: Implement**

```python
"""v129 acceptance-exit replay: every entry is built ONCE, with the flag off,
then simulated under today's exit (baseline) and under each grid cell.

Sharing the entry is what makes the design paired: the baseline and a cell
differ only in how the same plan exits. Arm Z entries are the confluence
replay's plans; arm B entries are the plans the Break & Retest backtest
builds, captured from backtest._bt_plan so they are the exact plans that
backtest simulated.

A row is plain JSON types -- see `entry_row`.
"""
from __future__ import annotations

import copy
import dataclasses

from swingbot.core.backtesting import backtest
from swingbot.core.backtesting.acceptance import arm_trade_from_plan
from swingbot.core.backtesting.backtest_scenarios import replay_scenarios
from swingbot.core.planning.acceptance_levels import (
    ARM_Z, BREAK_RETEST, apply_arm_b, apply_arm_z, atr_at, enabled_arms,
)
from swingbot.core.planning.exit_sim import simulate_exit

#: PRE-REGISTERED grid (spec § Pre-registered claim). Changing a step is a
#: new pre-registration, not a tuning step.
M_STEPS = (0.5, 1.0, 1.5)
B_STEPS = (0.0, 0.25)
CELLS = {
    "Z": tuple((m, b) for m in M_STEPS for b in B_STEPS),
    "B": tuple((None, b) for b in B_STEPS),
}
#: Exit outcomes that are not a trade: nothing to pair, nothing to count.
UNTRIGGERED = ("not_triggered", "no_trade")


def cell_key(m, b) -> str:
    """Stable JSON key for a grid cell: 'm1_b0.25' (arm Z), 'b0.25' (arm B)."""
    return f"b{b:g}" if m is None else f"m{m:g}_b{b:g}"


def _exit_mix(res) -> str:
    reason = res.legs[-1]["reason"]
    return reason if len(res.legs) == 1 else f"tp1+{reason}"


def _gap_through(df, plan, res) -> bool:
    """The stop-hit bar OPENED at or beyond the stop. The trade still books
    -1.0R (spec § Exit rule); this is the disclosure, not a re-priced fill."""
    if res.legs[-1]["reason"] != "stop":
        return False
    bar_open = float(df["Open"].values[res.exit_index])
    if plan.direction == "bullish":
        return bar_open <= plan.stop_loss
    return bar_open >= plan.stop_loss


def _record(df, i, plan) -> dict | None:
    """One side's exit as ArmTrade fields plus the two disclosures, or None
    when the plan never became a trade."""
    res = simulate_exit(df, i, plan, scale_out=True)
    if res.outcome in UNTRIGGERED:
        return None
    trade = arm_trade_from_plan(plan, entry_date=str(df.index[i].date()),
                                outcome=res.outcome, r_multiple=res.r_total)
    return {**dataclasses.asdict(trade), "exit_mix": _exit_mix(res),
            "gap_through": _gap_through(df, plan, res)}


def _cell_plan(arm, plan, atr_val, m, b):
    """(copy of `plan` with the cell applied, eligible). The shared plan is
    never mutated -- every cell starts from the flag-off plan."""
    cell = copy.copy(plan)
    if arm == ARM_Z:
        return cell, apply_arm_z(cell, atr_val, m, b)
    return cell, apply_arm_b(cell, atr_val, b)


def entry_row(arm, df, i, plan, atr_val, cells) -> dict | None:
    """One entry under the baseline and every cell in `cells`.

    A not-eligible plan keeps today's exit in every cell (delta R = 0) and
    stays in the population. The row is dropped only when NOTHING triggered:
    a wider arm-Z stop changes stop-entry invalidation, so one side can be
    None while the other traded, and those rows are disclosed, not hidden.
    """
    baseline = _record(df, i, plan)
    records, eligible = {}, False
    for m, b in cells:
        cell, eligible = _cell_plan(arm, plan, atr_val, m, b)
        records[cell_key(m, b)] = _record(df, i, cell) if eligible else baseline
    if baseline is None and all(record is None for record in records.values()):
        return None
    return {"arm": arm, "ticker": plan.ticker, "horizon_key": plan.horizon_key,
            "entry_date": str(df.index[i].date()), "direction": plan.direction,
            "eligible": eligible, "baseline": baseline, "cells": records}


def _break_retest_plans(ticker, df, horizon_key) -> list:
    """(signal_index, plan) for every plan the Break & Retest backtest
    builds, in order. Captured by wrapping backtest._bt_plan for this one
    call, so tp2 and the one-at-a-time population are the backtest's own."""
    captured = []
    original = backtest._bt_plan

    def recording(frame, i, **kwargs):
        plan = original(frame, i, **kwargs)
        captured.append((int(i), plan))
        return plan

    backtest._bt_plan = recording
    try:
        backtest.run_backtest(ticker, df, BREAK_RETEST, horizon_key,
                              exit_model="v2", scale_out=True, tp2_mode="levels")
    finally:
        backtest._bt_plan = original
    return captured


def _plans(arm, ticker, df, horizon_key, gates) -> list:
    if arm == ARM_Z:
        return replay_scenarios(ticker, df, horizon_key, gates=gates)
    return _break_retest_plans(ticker, df, horizon_key)


def _in_window(signal_date, start, end) -> bool:
    return not ((start and signal_date < start) or (end and signal_date > end))


def replay_entries(arm, ticker, df, horizons, *, start=None, end=None,
                   cells=None, gates=None) -> list:
    """Rows for one ticker. `start`/`end` (ISO or None) restrict the SIGNAL
    date; the exit walk may run past `end`, the run_backtest_range convention.
    `cells` defaults to the arm's whole grid; Stage 3 passes the one selected
    cell so VALIDATION is never read for a cell that was not selected.
    `gates` is a test seam for arm Z (None = live ScanParams)."""
    if enabled_arms():
        raise RuntimeError(
            "ACCEPTANCE_EXIT_ENABLED must be off while measuring: entries are "
            "built with today's exits and each cell is applied to a copy.")
    cells = CELLS[arm] if cells is None else tuple(tuple(cell) for cell in cells)
    rows = []
    for horizon_key in horizons:
        for i, plan in _plans(arm, ticker, df, horizon_key, gates):
            if not _in_window(str(df.index[i].date()), start, end):
                continue
            row = entry_row(arm, df, i, plan, atr_at(df, i, plan.trigger_price), cells)
            if row is not None:
                rows.append(row)
    return rows
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_acceptance_replay.py`
Expected: all pass. Then:
- `python scripts/dev/testrun.py file tests/backtesting/test_v129_flag_off_golden.py` (the wrapper restores `backtest._bt_plan`; the golden must still be green).
- `python -m radon cc -s -n C swingbot/core/backtesting/acceptance_replay.py`. Nothing may be listed.

If `test_break_retest_replay_baseline_matches_run_backtest` shows an extra row, the fixture produced a plan that never triggered in the baseline but did in a cell. That cannot happen in arm B (the stop is unchanged), so treat it as a bug in `_record`, not as data.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/acceptance_replay.py tests/backtesting/test_acceptance_replay.py
git commit -m "feat(v129): acceptance_replay -- shared entries re-simulated per grid cell

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V129-8: `acceptance_exit_funnel` — Stages 0–3 and the disclosures

**Files:**
- Create: `swingbot/core/backtesting/acceptance_exit_funnel.py`
- Create: `tests/backtesting/acceptance_rows.py` (synthetic-row helpers, also used by V129-9)
- Create: `tests/backtesting/test_acceptance_exit_funnel.py`

**Interfaces:**
- Consumes: `acceptance_replay.CELLS`, `M_STEPS`, `B_STEPS`, `cell_key` and the row shape (V129-7). `acceptance_harvest.mde_expectancy_r_paired`, `evaluate_harvest` (V129-3 and existing). `acceptance.bootstrap_delta`, `delta_expectancy_r`, `project_target_n`, `render_json`, `ArmTrade`, `CLOSED`, `_group_by_ticker`.
- Produces (V129-9 consumes all):
  - Frozen constants: `TRAIN = ("2020-01-01", "2023-12-31")`, `VALIDATION = ("2024-01-01", "2025-12-31")`, `TRAIN_DAYS = 1460`, `VALIDATION_DAYS = 730`, `MDE_CEILING_R = 0.10`, `MDE_POWER = 0.80`, `FOLD_YEARS = (2020, 2021, 2022, 2023)`, `PERMUTATION_N = 200`, `PERMUTATION_SEED = 42`, `ELIGIBILITY_CLAUSES = ("expectancy_gain", "win_rate_floor", "volume")`.
  - `arm_trades(rows, key) -> tuple[list[ArmTrade], list[ArmTrade]]`.
  - `stage0(rows, arm) -> dict` with `verdict` `POWERED | UNDERPOWERED`.
  - `stage1(rows, arm, *, n_resamples=BOOTSTRAP_RESAMPLES, seed=42) -> dict` with `verdict` `SELECTED | NO_ELIGIBLE_CELL` and `selected = {"cell", "m", "b"} | None`.
  - `stage2(rows, arm, key) -> dict` with `verdict` `PASS | FAIL`.
  - `sign_flip_p(baseline, component, *, n_perm=PERMUTATION_N, seed=PERMUTATION_SEED) -> float | None`.
  - `stage3(rows, arm, key, *, n_resamples=BOOTSTRAP_RESAMPLES, seed=42) -> dict` with `verdict` `PASS | FAIL`.
  - `report(rows, arm, key, *, n_resamples=BOOTSTRAP_RESAMPLES, seed=42) -> dict` (the spec's § Reporting block).
- Test helpers in `tests/backtesting/acceptance_rows.py`: `record(...)`, `row(...)`, `lifted_rows(arm, lifts, *, jitter=0.0, n_tickers=20, per_ticker=4, year=2021)`.

The rules frozen here are the pre-registration (index, Spec correction 7 and 8). Every one is a module constant or a one-line rule with a test:
- **Stage 0.** Per cell, `target_n = project_target_n(observed_n=<baseline closed N on TRAIN>, observed_days=1460, target_days=730)`. The arm is `UNDERPOWERED` when any cell's paired MDE is `None` or above `+0.10R`.
- **Stage 1.** A cell is eligible when `expectancy_gain`, `win_rate_floor` and `volume` all read `PASS` from `evaluate_harvest(stage="walkforward")`. A cell is on the plateau when it and every grid neighbour (±1 step in `m` or `b`; in arm B, the other cell) are eligible. The selected cell is the plateau cell with the highest lower-95% ΔExpR. A tie goes to the earlier cell in `CELLS` order (smaller `m`, then smaller `b`).
- **Stage 2.** One fold per TRAIN calendar year. A fold is measurable when ΔExpR is defined, and reversed when it is `< 0`. `FAIL` when more than half the measurable folds reverse, or when no fold is measurable.
- **Stage 3.** `sign_flip_p` swaps the two arms' labels for a random half of the tickers, `n = 200`, `seed = 42`. For a paired trade that is exactly a sign flip of its ΔR, and it also handles the entries only one arm triggered. `p` is the share of permutations whose ΔExpR is at or above the observed one.

- [ ] **Step 0: Check for v123's permutation**

Run: `git grep -n "def permutation_p_expectancy" -- swingbot/core/backtesting/acceptance_harvest.py`
If it prints a line, v123 landed first and already ships the same instrument. In that case do **not** write `_swapped`/`sign_flip_p` bodies below. Define `sign_flip_p` as a one-line wrapper: `return permutation_p_expectancy(baseline, component, n_perm=n_perm, seed=seed)`. The tests below must pass unchanged either way.

- [ ] **Step 1: Write the row helpers**

`tests/backtesting/acceptance_rows.py`:

```python
"""Synthetic v129 replay rows (the acceptance_replay.entry_row shape) for the
funnel tests and the driver-script tests."""


def record(ticker, date, outcome, r, *, horizon="4w", rr=2.0, mix=None, gap=False):
    return {"ticker": ticker, "strategy": "S", "horizon_key": horizon,
            "entry_date": date, "outcome": outcome, "r_multiple": r,
            "planned_rr": rr, "source": "confluence", "direction": "bullish",
            "exit_mix": mix or ("tp1" if outcome == "win" else "stop"),
            "gap_through": gap}


def row(baseline, cells, *, arm="Z", eligible=True):
    """`baseline` and each `cells` value are record() dicts or None."""
    anchor = baseline or next(c for c in cells.values() if c is not None)
    return {"arm": arm, "ticker": anchor["ticker"], "horizon_key": anchor["horizon_key"],
            "entry_date": anchor["entry_date"], "direction": anchor["direction"],
            "eligible": eligible, "baseline": baseline, "cells": cells}


def lifted_rows(arm, lifts, *, jitter=0.0, n_tickers=20, per_ticker=4, year=2021):
    """n_tickers * per_ticker paired rows. The baseline alternates win (+2R)
    and loss (-1R); each cell keeps the outcome and adds lifts[key], plus
    +jitter on even trades and -jitter on odd ones."""
    rows = []
    for t in range(n_tickers):
        for k in range(per_ticker):
            ticker, date = f"T{t:02d}", f"{year}-{k + 1:02d}-15"
            outcome, base_r = ("win", 2.0) if k % 2 == 0 else ("loss", -1.0)
            wobble = jitter if k % 2 == 0 else -jitter
            cells = {key: record(ticker, date, outcome, base_r + lift + wobble)
                     for key, lift in lifts.items()}
            rows.append(row(record(ticker, date, outcome, base_r), cells, arm=arm))
    return rows
```

- [ ] **Step 2: Write the failing tests**

`tests/backtesting/test_acceptance_exit_funnel.py`:

```python
"""v129 funnel: Stage 0 paired MDE, Stage 1 plateau selection, Stage 2 fold
reversal, Stage 3 one-shot gate, and the disclosure report. Synthetic rows
with uniform lifts make every bootstrap draw equal the lift, so each verdict
is checkable by hand."""
import pytest

from swingbot.core.backtesting import acceptance_exit_funnel as funnel
from swingbot.core.backtesting.acceptance_replay import CELLS, cell_key
from tests.backtesting.acceptance_rows import lifted_rows, record, row

N = 200   # bootstrap resamples: tests only, never a real run

Z_KEYS = [cell_key(m, b) for m, b in CELLS["Z"]]
PLATEAU = {"m0.5_b0": 0.10, "m0.5_b0.25": 0.05, "m1_b0": 0.30,
           "m1_b0.25": 0.25, "m1.5_b0": 0.20, "m1.5_b0.25": 0.15}


def test_frozen_constants():
    assert funnel.TRAIN == ("2020-01-01", "2023-12-31")
    assert funnel.VALIDATION == ("2024-01-01", "2025-12-31")
    assert (funnel.TRAIN_DAYS, funnel.VALIDATION_DAYS) == (1460, 730)
    assert funnel.MDE_CEILING_R == 0.10 and funnel.MDE_POWER == 0.80
    assert funnel.FOLD_YEARS == (2020, 2021, 2022, 2023)
    assert (funnel.PERMUTATION_N, funnel.PERMUTATION_SEED) == (200, 42)


def test_arm_trades_drops_untriggered_side_only():
    rows = [
        row(record("A", "2021-01-15", "loss", -1.0), {"b0": record("A", "2021-01-15", "win", 1.0)}),
        row(None, {"b0": record("B", "2021-02-15", "win", 1.5)}),
        row(record("C", "2021-03-15", "win", 2.0), {"b0": None}),
    ]
    baseline, component = funnel.arm_trades(rows, "b0")
    assert [t.ticker for t in baseline] == ["A", "C"]
    assert [t.ticker for t in component] == ["A", "B"]


# --- Stage 0 ----------------------------------------------------------------

def test_stage0_powered_when_every_cell_clears_the_ceiling():
    out = funnel.stage0(lifted_rows("Z", PLATEAU), "Z")
    assert out["verdict"] == "POWERED"
    assert [c["cell"] for c in out["cells"]] == Z_KEYS
    assert all(c["observed_n"] == 80 and c["target_n"] == 40 for c in out["cells"])
    assert all(c["mde_r"] == pytest.approx(0.0) for c in out["cells"])


def test_stage0_underpowered_when_one_cell_is_noisy():
    rows = lifted_rows("B", {"b0": 0.3, "b0.25": 0.3})
    noisy = lifted_rows("B", {"b0.25": 0.3}, jitter=2.0)
    for target, source in zip(rows, noisy):
        target["cells"]["b0.25"] = source["cells"]["b0.25"]
    out = funnel.stage0(rows, "B")
    assert out["verdict"] == "UNDERPOWERED"
    by_cell = {c["cell"]: c for c in out["cells"]}
    assert by_cell["b0"]["powered"] is True
    assert by_cell["b0.25"]["powered"] is False
    assert by_cell["b0.25"]["mde_r"] > funnel.MDE_CEILING_R


def test_stage0_underpowered_when_the_mde_is_undefined():
    rows = lifted_rows("B", {"b0": 0.3, "b0.25": 0.3}, n_tickers=1, per_ticker=1)
    assert funnel.stage0(rows, "B")["verdict"] == "UNDERPOWERED"


# --- Stage 1 ----------------------------------------------------------------

def test_stage1_selects_the_highest_lower_bound_on_the_plateau():
    out = funnel.stage1(lifted_rows("Z", PLATEAU), "Z", n_resamples=N)
    assert out["verdict"] == "SELECTED"
    assert out["selected"] == {"cell": "m1_b0", "m": 1.0, "b": 0.0}
    assert all(c["eligible"] and c["plateau"] for c in out["cells"])


def test_stage1_skips_a_spike_with_an_ineligible_neighbour():
    lifts = dict(PLATEAU, **{"m1.5_b0": 0.50, "m1.5_b0.25": 0.0})
    out = funnel.stage1(lifted_rows("Z", lifts), "Z", n_resamples=N)
    by_cell = {c["cell"]: c for c in out["cells"]}
    assert by_cell["m1.5_b0"]["eligible"] is True
    assert by_cell["m1.5_b0"]["plateau"] is False      # its b neighbour failed
    assert by_cell["m1_b0.25"]["plateau"] is False     # its m neighbour failed
    assert out["selected"]["cell"] == "m1_b0"


def test_stage1_no_eligible_cell():
    out = funnel.stage1(lifted_rows("Z", {key: 0.0 for key in Z_KEYS}), "Z", n_resamples=N)
    assert out["verdict"] == "NO_ELIGIBLE_CELL" and out["selected"] is None


def test_stage1_arm_b_needs_both_cells():
    one = funnel.stage1(lifted_rows("B", {"b0": 0.3, "b0.25": 0.0}), "B", n_resamples=N)
    assert one["verdict"] == "NO_ELIGIBLE_CELL"
    both = funnel.stage1(lifted_rows("B", {"b0": 0.1, "b0.25": 0.3}), "B", n_resamples=N)
    assert both["selected"] == {"cell": "b0.25", "m": None, "b": 0.25}


# --- Stage 2 ----------------------------------------------------------------

def _years(lift_by_year):
    rows = []
    for year, lift in lift_by_year.items():
        rows += lifted_rows("B", {"b0": lift}, year=year)
    return rows


def test_stage2_passes_when_at_most_half_the_folds_reverse():
    out = funnel.stage2(_years({2020: 0.2, 2021: 0.2, 2022: -0.1, 2023: -0.1}), "B", "b0")
    assert out["verdict"] == "PASS"
    assert [f["reversed"] for f in out["folds"]] == [False, False, True, True]


def test_stage2_fails_when_most_folds_reverse():
    out = funnel.stage2(_years({2020: 0.2, 2021: -0.1, 2022: -0.1, 2023: -0.1}), "B", "b0")
    assert out["verdict"] == "FAIL"


def test_stage2_ignores_empty_folds_and_fails_with_none_measurable():
    out = funnel.stage2(_years({2021: 0.2, 2022: -0.1}), "B", "b0")
    assert out["verdict"] == "PASS" and out["measurable"] == 2
    assert funnel.stage2([], "B", "b0")["verdict"] == "FAIL"


# --- Stage 3 ----------------------------------------------------------------

def test_sign_flip_p_detects_a_uniform_lift_and_not_identity():
    lifted = funnel.arm_trades(lifted_rows("B", {"b0": 0.3}), "b0")
    same = funnel.arm_trades(lifted_rows("B", {"b0": 0.0}), "b0")
    assert funnel.sign_flip_p(*lifted) < 0.05
    assert funnel.sign_flip_p(*same) == 1.0
    assert funnel.sign_flip_p([], []) is None


def test_stage3_passes_a_real_lift_and_fails_a_null():
    good = funnel.stage3(lifted_rows("B", {"b0": 0.3}, year=2024), "B", "b0", n_resamples=N)
    assert good["verdict"] == "PASS" and good["permutation_p"] < 0.05
    names = {c["name"]: c["verdict"] for c in good["gate"]["clauses"]}
    assert names == {"expectancy_gain": "PASS", "win_rate_floor": "PASS",
                     "volume": "PASS", "permutation": "PASS"}
    null = funnel.stage3(lifted_rows("B", {"b0": 0.0}, year=2024), "B", "b0", n_resamples=N)
    assert null["verdict"] == "FAIL"


# --- disclosures ------------------------------------------------------------

def test_report_counts_flips_mix_and_disclosures():
    stuck = record("D", "2021-04-15", "loss", -1.0, gap=True)
    rows = [
        row(record("A", "2021-01-15", "loss", -1.0),
            {"m1_b0": record("A", "2021-01-15", "win", 1.5, rr=1.0, mix="tp1+runner_trail")}),
        row(record("B", "2021-02-15", "win", 2.0),
            {"m1_b0": record("B", "2021-02-15", "loss", -0.4, rr=1.0, mix="acceptance_exit")}),
        row(None, {"m1_b0": record("C", "2021-03-15", "win", 1.0, rr=1.0)}),
        row(stuck, {"m1_b0": stuck}, eligible=False),
    ]
    out = funnel.report(rows, "Z", "m1_b0", n_resamples=N)
    assert (out["n_baseline"], out["n_component"]) == (3, 4)
    assert out["flips"] == {"win_to_loss": 1, "loss_to_win": 1, "other": 0}
    assert out["exit_mix"]["component"] == {"tp1+runner_trail": 1, "acceptance_exit": 1,
                                            "tp1": 1, "stop": 1}
    assert out["exit_mix"]["baseline"] == {"stop": 2, "tp1": 1}
    assert out["not_eligible"] == 1
    assert out["gap_through"] == {"baseline": 1, "component": 1}
    assert (out["only_baseline_triggered"], out["only_cell_triggered"]) == (0, 1)
    assert out["per_horizon_n"] == {"4w": 4}
    assert out["median_planned_rr"] == {"baseline": 2.0, "component": 1.0}
    assert out["delta_expr"] == pytest.approx((1.5 - 0.4 + 1.0 - 1.0) / 4 - 0.0)
```

- [ ] **Step 3: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_acceptance_exit_funnel.py`
Expected: FAIL, `ImportError: cannot import name 'acceptance_exit_funnel'`.

- [ ] **Step 4: Implement**

```python
"""v129 acceptance-exit funnel: Stages 0-3 over acceptance_replay rows.

Every constant here is PRE-REGISTERED (spec § Gate and funnel; plan index,
Spec corrections 7 and 8). Changing one is a new pre-registration, not a
tuning step -- see docs/claude/backtest-methodology.md.

The gate is the v92 harvest gate (acceptance_harvest.evaluate_harvest); this
module only decides which cell meets it and in what order the stages run.
"""
from __future__ import annotations

import dataclasses
from collections import Counter

import numpy as np

from .acceptance import (
    ArmTrade, BOOTSTRAP_RESAMPLES, CLOSED, _group_by_ticker, bootstrap_delta,
    delta_expectancy_r, expectancy_r, median_planned_rr, project_target_n,
    render_json, win_rate,
)
from .acceptance_harvest import evaluate_harvest, mde_expectancy_r_paired
from .acceptance_replay import B_STEPS, CELLS, M_STEPS, cell_key

TRAIN = ("2020-01-01", "2023-12-31")
VALIDATION = ("2024-01-01", "2025-12-31")
TRAIN_DAYS, VALIDATION_DAYS = 1460, 730
MDE_CEILING_R = 0.10
MDE_POWER = 0.80
FOLD_YEARS = (2020, 2021, 2022, 2023)
PERMUTATION_N = 200
PERMUTATION_SEED = 42
#: The clauses a TRAIN cell must PASS to be eligible. `permutation` is not
#: among them: it is SKIPPED before the validation stage.
ELIGIBILITY_CLAUSES = ("expectancy_gain", "win_rate_floor", "volume")

_TRADE_FIELDS = tuple(f.name for f in dataclasses.fields(ArmTrade))


def _trade(record) -> ArmTrade:
    return ArmTrade(**{name: record[name] for name in _TRADE_FIELDS})


def arm_trades(rows, key) -> tuple:
    """(baseline, component) ArmTrade lists for one cell. A side that never
    triggered is absent from ITS list only, so population_split reports the
    row as added or removed instead of the row vanishing from both."""
    baseline = [_trade(r["baseline"]) for r in rows if r["baseline"] is not None]
    component = [_trade(r["cells"][key]) for r in rows if r["cells"][key] is not None]
    return baseline, component


# --- Stage 0 ---------------------------------------------------------------

def _mde_cell(rows, key) -> dict:
    baseline, component = arm_trades(rows, key)
    observed_n = sum(1 for t in baseline if t.outcome in CLOSED)
    target_n = project_target_n(observed_n=observed_n, observed_days=TRAIN_DAYS,
                                target_days=VALIDATION_DAYS)
    mde = mde_expectancy_r_paired(baseline, component, target_n=target_n,
                                  power=MDE_POWER)
    return {"cell": key, "observed_n": observed_n, "target_n": target_n,
            "mde_r": mde, "powered": mde is not None and mde <= MDE_CEILING_R}


def stage0(rows, arm) -> dict:
    """Paired MDE precheck on TRAIN rows. Any cell over the ceiling closes
    the arm UNDERPOWERED, because Stage 1 may select any cell."""
    cells = [_mde_cell(rows, cell_key(m, b)) for m, b in CELLS[arm]]
    verdict = "POWERED" if all(c["powered"] for c in cells) else "UNDERPOWERED"
    return {"stage": 0, "arm": arm, "verdict": verdict,
            "mde_ceiling_r": MDE_CEILING_R, "power": MDE_POWER, "cells": cells}


# --- Stage 1 ---------------------------------------------------------------

def _neighbours(arm, m, b) -> list:
    """Grid cells one step away in m or in b. Arm B has one axis, so the
    neighbour of a cell is the other cell."""
    if m is None:
        return [cell for cell in CELLS[arm] if cell != (m, b)]
    mi, bi = M_STEPS.index(m), B_STEPS.index(b)
    out = [(M_STEPS[j], b) for j in (mi - 1, mi + 1) if 0 <= j < len(M_STEPS)]
    out += [(m, B_STEPS[j]) for j in (bi - 1, bi + 1) if 0 <= j < len(B_STEPS)]
    return out


def _selection_cell(rows, m, b, n_resamples, seed) -> dict:
    key = cell_key(m, b)
    baseline, component = arm_trades(rows, key)
    result = evaluate_harvest(baseline, component, stage="walkforward",
                              n_resamples=n_resamples, seed=seed)
    boot = bootstrap_delta(baseline, component, delta_expectancy_r,
                           n_resamples=n_resamples, seed=seed)
    eligible = all(result.clause(name).verdict == "PASS"
                   for name in ELIGIBILITY_CLAUSES)
    return {"cell": key, "m": m, "b": b, "eligible": eligible,
            "delta_expr": boot.point, "lo95": boot.lo, "hi95": boot.hi,
            "gate": render_json(result)}


def stage1(rows, arm, *, n_resamples: int = BOOTSTRAP_RESAMPLES, seed: int = 42) -> dict:
    """TRAIN plateau selection: the eligible cell with the highest lower-95%
    dExpR whose grid neighbours are all eligible. A tie goes to the earlier
    cell in CELLS order (max() keeps the first maximum)."""
    table = {(m, b): _selection_cell(rows, m, b, n_resamples, seed)
             for m, b in CELLS[arm]}
    for (m, b), cell in table.items():
        cell["plateau"] = cell["eligible"] and all(
            table[other]["eligible"] for other in _neighbours(arm, m, b))
    pool = [cell for cell in table.values() if cell["plateau"]]
    selected = None
    if pool:
        best = max(pool, key=lambda cell: cell["lo95"])
        selected = {"cell": best["cell"], "m": best["m"], "b": best["b"]}
    return {"stage": 1, "arm": arm,
            "verdict": "SELECTED" if selected else "NO_ELIGIBLE_CELL",
            "selected": selected, "cells": list(table.values())}


# --- Stage 2 ---------------------------------------------------------------

def stage2(rows, arm, key) -> dict:
    """Free walk-forward folds: one per TRAIN calendar year, for the selected
    cell. FAIL when more than half the measurable folds reverse sign, or when
    no fold is measurable."""
    folds = []
    for year in FOLD_YEARS:
        fold_rows = [r for r in rows if r["entry_date"][:4] == str(year)]
        delta = delta_expectancy_r(*arm_trades(fold_rows, key))
        folds.append({"year": year, "n": len(fold_rows), "delta_expr": delta,
                      "reversed": delta is not None and delta < 0})
    measurable = [f for f in folds if f["delta_expr"] is not None]
    reversed_n = sum(1 for f in measurable if f["reversed"])
    ok = bool(measurable) and reversed_n <= len(measurable) / 2
    return {"stage": 2, "arm": arm, "cell": key, "verdict": "PASS" if ok else "FAIL",
            "measurable": len(measurable), "reversed": reversed_n, "folds": folds}


# --- Stage 3 ---------------------------------------------------------------

def _swapped(b_by, c_by, tickers, flips) -> tuple:
    left, right = [], []
    for ticker, flip in zip(tickers, flips):
        b, c = b_by.get(ticker, []), c_by.get(ticker, [])
        left.extend(c if flip else b)
        right.extend(b if flip else c)
    return left, right


def sign_flip_p(baseline, component, *, n_perm: int = PERMUTATION_N,
                seed: int = PERMUTATION_SEED) -> float | None:
    """The not_luck instrument: swap the arm labels of a random half of the
    tickers and recompute dExpR. For a paired trade that is a sign flip of
    its dR; it also covers entries only one arm triggered. p = share of
    permutations at or above the observed dExpR."""
    observed = delta_expectancy_r(baseline, component)
    if observed is None:
        return None
    b_by, c_by = _group_by_ticker(baseline), _group_by_ticker(component)
    tickers = sorted(set(b_by) | set(c_by))
    rng = np.random.default_rng(seed)
    hits = 0
    for _ in range(n_perm):
        flips = rng.random(len(tickers)) < 0.5
        delta = delta_expectancy_r(*_swapped(b_by, c_by, tickers, flips))
        hits += delta is not None and delta >= observed - 1e-12
    return hits / n_perm


def stage3(rows, arm, key, *, n_resamples: int = BOOTSTRAP_RESAMPLES,
           seed: int = 42) -> dict:
    """The one VALIDATION shot for the selected cell: all four harvest
    clauses, with the permutation p from sign_flip_p."""
    baseline, component = arm_trades(rows, key)
    p = sign_flip_p(baseline, component)
    result = evaluate_harvest(baseline, component, stage="validation",
                              permutation_p=p, n_resamples=n_resamples, seed=seed)
    return {"stage": 3, "arm": arm, "cell": key, "verdict": result.verdict,
            "permutation_p": p, "gate": render_json(result)}


# --- disclosures (spec § Reporting) ----------------------------------------

def _flips(rows, key) -> dict:
    out = {"win_to_loss": 0, "loss_to_win": 0, "other": 0}
    for r in rows:
        base, cell = r["baseline"], r["cells"][key]
        if base is None or cell is None or base["outcome"] == cell["outcome"]:
            continue
        pair = (base["outcome"], cell["outcome"])
        name = {("win", "loss"): "win_to_loss", ("loss", "win"): "loss_to_win"}.get(pair, "other")
        out[name] += 1
    return out


def _sides(rows, key) -> tuple:
    baseline = [r["baseline"] for r in rows if r["baseline"] is not None]
    component = [r["cells"][key] for r in rows if r["cells"][key] is not None]
    return baseline, component


def _triggered_once(rows, key) -> tuple:
    only_base = sum(1 for r in rows if r["baseline"] is not None and r["cells"][key] is None)
    only_cell = sum(1 for r in rows if r["baseline"] is None and r["cells"][key] is not None)
    return only_base, only_cell


def _pp(component, baseline) -> float | None:
    return None if component is None or baseline is None else component - baseline


def report(rows, arm, key, *, n_resamples: int = BOOTSTRAP_RESAMPLES,
           seed: int = 42) -> dict:
    """Everything the spec asks to be reported for one cell. Informational:
    nothing here gates."""
    baseline, component = arm_trades(rows, key)
    base_records, cell_records = _sides(rows, key)
    boot = bootstrap_delta(baseline, component, delta_expectancy_r,
                           n_resamples=n_resamples, seed=seed)
    wr_base, wr_cell = win_rate(baseline), win_rate(component)
    only_base, only_cell = _triggered_once(rows, key)
    return {
        "arm": arm, "cell": key,
        "n_baseline": len(baseline), "n_component": len(component),
        "expr_baseline": expectancy_r(baseline), "expr_component": expectancy_r(component),
        "delta_expr": boot.point, "delta_expr_lo95": boot.lo, "delta_expr_hi95": boot.hi,
        "wr_baseline": wr_base, "wr_component": wr_cell,
        "delta_wr_pp": _pp(wr_cell, wr_base),
        "flips": _flips(rows, key),
        "exit_mix": {"baseline": dict(Counter(r["exit_mix"] for r in base_records)),
                     "component": dict(Counter(r["exit_mix"] for r in cell_records))},
        "median_planned_rr": {"baseline": median_planned_rr(baseline),
                              "component": median_planned_rr(component)},
        "not_eligible": sum(1 for r in rows if not r["eligible"]),
        "gap_through": {"baseline": sum(1 for r in base_records if r["gap_through"]),
                        "component": sum(1 for r in cell_records if r["gap_through"])},
        "only_baseline_triggered": only_base, "only_cell_triggered": only_cell,
        "per_horizon_n": dict(Counter(r["horizon_key"] for r in rows)),
    }
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_acceptance_exit_funnel.py`
Expected: all pass. Then:
- `python scripts/dev/testrun.py file tests/backtesting/test_acceptance_harvest.py` (the gate module is imported, not edited; it must be unchanged).
- `python -m radon cc -s -n C swingbot/core/backtesting/acceptance_exit_funnel.py`. Nothing may be listed.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/backtesting/acceptance_exit_funnel.py tests/backtesting/acceptance_rows.py tests/backtesting/test_acceptance_exit_funnel.py
git commit -m "feat(v129): acceptance-exit funnel -- paired MDE, plateau selection, folds, one-shot gate

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V129-9: `measure_acceptance_exits.py` — the stage driver

**Files:**
- Create: `scripts/backtest/measure_acceptance_exits.py`
- Create: `tests/scripts/test_measure_acceptance_exits.py`

**Interfaces:**
- Consumes: `acceptance_exit_funnel` (`stage0`..`stage3`, `report`, `TRAIN`, `VALIDATION`), `acceptance_replay.CELLS`, `cell_key`, `replay_entries` (V129-7/8). `measure_arms.cached_universe`, `measure_arms.load_frame`, `backtest_scenarios._resolve_replay_workers`, `strategy_types.LEGACY_HORIZONS`. Test helpers `tests.backtesting.acceptance_rows.lifted_rows` (V129-8).
- Produces:
  - `RESULTS = docs/superpowers/results/v129/`, `stage_path(out_dir, arm, stage) -> Path` (`2026-10-03-v129-arm<ARM>-stage<N>.json`), `rows_path(out_dir, arm, window) -> Path` (`2026-10-03-v129-arm<ARM>-<train|validation>-rows.json`).
  - `build_rows(arm, window, cells, *, tickers=None, workers=None) -> list[dict]`.
  - `run_stage(arm, stage, out_dir, *, build, n_resamples=BOOTSTRAP_RESAMPLES) -> dict`. `build` is `callable(arm, window, cells) -> rows`, injected so the tests never replay.
  - CLI: `python scripts/backtest/measure_acceptance_exits.py --arm Z|B --stage 0|1|2|3 [--preregistration PATH] [--out-dir DIR] [--tickers N] [--workers N] [--resamples N]`. Exit code 0 when the stage's verdict is `POWERED`, `SELECTED` or `PASS`, else 1.
  - V129-10..15 run this CLI.

Rules the driver enforces:
- **Each stage consumes the previous stage's verdict JSON.** Stage 1 needs Stage 0 `POWERED`, Stage 2 needs Stage 1 `SELECTED`, Stage 3 needs Stage 2 `PASS`. A missing or failing predecessor is `refused:`, and nothing is replayed.
- **TRAIN rows are built once**, at Stage 0, and reused by Stages 1 and 2 from the rows file.
- **Stage 3 is one shot** (Review Focus 5). It is refused when its output file exists. It replays VALIDATION for **the selected cell only**. It needs `--preregistration` to name an existing file and refuses `--tickers`. If the VALIDATION rows file exists but the verdict file does not (a crash between the two writes), the saved rows are reused without replaying.
- **`--tickers N` is a smoke run** and is refused with the default `--out-dir`, so a partial universe can never overwrite a real stage file.
- **Progress:** a flushed line per ticker, plus `logs/measure_acceptance_exits.arm<ARM>.progress` rewritten after every ticker and deleted on completion.

- [ ] **Step 1: Write the failing tests**

```python
"""v129 stage driver: prerequisites, the one-shot refusal and the
selected-cell-only VALIDATION replay. `build` is faked; no replay runs."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "backtest"))
import measure_acceptance_exits as mae  # noqa: E402

from swingbot.core.backtesting import acceptance_exit_funnel as funnel
from swingbot.core.backtesting.acceptance_replay import CELLS, cell_key
from tests.backtesting.acceptance_rows import lifted_rows

N = 200


def _fake_build(calls, lift=0.3):
    def build(arm, window, cells):
        calls.append((arm, tuple(window), [tuple(cell) for cell in cells]))
        lifts = {cell_key(m, b): lift for m, b in CELLS[arm]}
        return lifted_rows(arm, lifts, year=int(window[0][:4]))
    return build


def _run(arm, stage, out_dir, calls, **kw):
    return mae.run_stage(arm, stage, out_dir, build=_fake_build(calls, **kw), n_resamples=N)


def test_paths():
    assert mae.stage_path("d", "Z", 3).name == "2026-10-03-v129-armZ-stage3.json"
    assert mae.rows_path("d", "B", "train").name == "2026-10-03-v129-armB-train-rows.json"


def test_stage0_builds_train_rows_once_and_writes_the_verdict(tmp_path):
    calls = []
    out = _run("Z", 0, tmp_path, calls)
    assert out["verdict"] == "POWERED"
    assert calls == [("Z", funnel.TRAIN, list(CELLS["Z"]))]
    assert mae.rows_path(tmp_path, "Z", "train").exists()
    assert json.loads(mae.stage_path(tmp_path, "Z", 0).read_text())["verdict"] == "POWERED"
    _run("Z", 0, tmp_path, calls)
    assert len(calls) == 1          # the rows file is reused, not rebuilt


def test_stage1_refuses_without_stage0(tmp_path):
    calls = []
    with pytest.raises(SystemExit, match="run stage 0 first"):
        _run("Z", 1, tmp_path, calls)
    assert calls == []


def test_a_closed_arm_does_not_advance(tmp_path):
    mae.stage_path(tmp_path, "B", 0).write_text(json.dumps({"verdict": "UNDERPOWERED"}))
    with pytest.raises(SystemExit, match="closed at stage 0 with UNDERPOWERED"):
        _run("B", 1, tmp_path, [])


def test_full_chain_replays_validation_for_the_selected_cell_only(tmp_path):
    calls = []
    assert _run("Z", 0, tmp_path, calls)["verdict"] == "POWERED"
    stage1 = _run("Z", 1, tmp_path, calls)
    assert stage1["verdict"] == "SELECTED"
    assert len(stage1["reports"]) == len(CELLS["Z"])
    assert _run("Z", 2, tmp_path, calls)["verdict"] == "PASS"
    stage3 = _run("Z", 3, tmp_path, calls)
    picked = stage1["selected"]
    assert calls[-1] == ("Z", funnel.VALIDATION, [(picked["m"], picked["b"])])
    assert len(calls) == 2          # TRAIN once, VALIDATION once
    assert stage3["cell"] == picked["cell"] and stage3["verdict"] == "PASS"
    assert stage3["report"]["cell"] == picked["cell"]


def test_stage3_refuses_when_output_exists(tmp_path):
    calls = []
    for stage in (0, 1, 2, 3):
        _run("B", stage, tmp_path, calls)
    before = len(calls)
    with pytest.raises(SystemExit, match="spent"):
        _run("B", 3, tmp_path, calls)
    assert len(calls) == before


def test_stage3_reuses_saved_validation_rows_after_a_crash(tmp_path):
    calls = []
    for stage in (0, 1, 2, 3):
        _run("B", stage, tmp_path, calls)
    mae.stage_path(tmp_path, "B", 3).unlink()      # crash before the verdict write
    before = len(calls)
    assert _run("B", 3, tmp_path, calls)["verdict"] == "PASS"
    assert len(calls) == before                    # no second look at VALIDATION


def test_cli_refuses_stage3_without_a_preregistration(tmp_path, capsys):
    code = mae.main(["--arm", "Z", "--stage", "3", "--out-dir", str(tmp_path)])
    assert code == 1
    assert "refused:no-preregistration" in capsys.readouterr().err


def test_cli_refuses_a_smoke_run_into_the_real_results_dir(capsys):
    code = mae.main(["--arm", "Z", "--stage", "0", "--tickers", "3"])
    assert code == 1
    assert "refused:smoke-run" in capsys.readouterr().err


def test_cli_refuses_a_partial_universe_at_stage3(tmp_path, capsys):
    prereg = tmp_path / "prereg.md"
    prereg.write_text("x")
    code = mae.main(["--arm", "Z", "--stage", "3", "--out-dir", str(tmp_path),
                     "--tickers", "3", "--preregistration", str(prereg)])
    assert code == 1
    assert "refused:partial-validation" in capsys.readouterr().err
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_measure_acceptance_exits.py`
Expected: FAIL, `ModuleNotFoundError: No module named 'measure_acceptance_exits'`.

- [ ] **Step 3: Implement**

```python
#!/usr/bin/env python3
"""v129 acceptance-failure exits: Stage 0-3 driver, one arm and one stage per call.

Each stage reads the previous stage's verdict JSON and refuses to run without
the verdict it needs, so a closed arm cannot be advanced by hand:

  stage 0  paired MDE precheck on TRAIN   -> POWERED | UNDERPOWERED
  stage 1  TRAIN plateau selection        -> SELECTED | NO_ELIGIBLE_CELL
  stage 2  TRAIN calendar-year folds      -> PASS | FAIL
  stage 3  ONE-SHOT VALIDATION            -> PASS | FAIL

TRAIN rows are replayed once (stage 0) and reused. Stage 3 replays VALIDATION
for the selected cell only and is refused when its output exists.

PROGRESS: a flushed line per ticker, plus logs/measure_acceptance_exits.
arm<ARM>.progress (percent, rewritten per ticker, deleted on completion).

Run: python scripts/backtest/measure_acceptance_exits.py --arm Z --stage 0
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

from swingbot.core.backtesting import acceptance_exit_funnel as funnel  # noqa: E402
from swingbot.core.backtesting.acceptance import BOOTSTRAP_RESAMPLES  # noqa: E402
from swingbot.core.backtesting.acceptance_replay import CELLS, cell_key, replay_entries  # noqa: E402
from swingbot.core.backtesting.backtest_scenarios import _resolve_replay_workers  # noqa: E402
from swingbot.core.market.strategy_types import LEGACY_HORIZONS  # noqa: E402

RESULTS = ROOT / "docs" / "superpowers" / "results" / "v129"
LOG_DIR = ROOT / "logs"
PREFIX = "2026-10-03-v129"
#: stage -> (the stage it consumes, the verdict that stage must carry).
REQUIRES = {1: (0, "POWERED"), 2: (1, "SELECTED"), 3: (2, "PASS")}
ADVANCING = ("POWERED", "SELECTED", "PASS")


def stage_path(out_dir, arm, stage) -> Path:
    return Path(out_dir) / f"{PREFIX}-arm{arm}-stage{stage}.json"


def rows_path(out_dir, arm, window) -> Path:
    return Path(out_dir) / f"{PREFIX}-arm{arm}-{window}-rows.json"


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write(path, blob, indent=1) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(blob, indent=indent), encoding="utf-8")


def _refuse(message):
    raise SystemExit(f"refused: {message}")


# --- replay ------------------------------------------------------------------

def _worker(task):
    """One ticker, every horizon -- the process-pool entry point."""
    arm, ticker, window, cells = task
    from measure_arms import load_frame
    frame = load_frame(ticker)
    if frame is None:
        return ticker, []
    return ticker, replay_entries(arm, ticker, frame, LEGACY_HORIZONS,
                                  start=window[0], end=window[1], cells=cells)


def _write_progress(path, done, total) -> None:
    try:
        path.write_text(f"{done}/{total} tickers ({done / total * 100:.0f}%)\n",
                        encoding="utf-8")
    except OSError:
        pass


def build_rows(arm, window, cells, *, tickers=None, workers=None) -> list:
    """Replay every cached ticker and return its rows in ticker order, so the
    output is identical whatever order the pool finishes in."""
    from measure_arms import cached_universe
    universe = cached_universe()[:tickers] if tickers else cached_universe()
    tasks = [(arm, ticker, tuple(window), tuple(tuple(c) for c in cells))
             for ticker in universe]
    LOG_DIR.mkdir(exist_ok=True)
    progress = LOG_DIR / f"measure_acceptance_exits.arm{arm}.progress"
    by_ticker: dict = {}

    def record(ticker, rows):
        by_ticker[ticker] = rows
        print(f"  [arm {arm} {window[0]}..{window[1]}] {len(by_ticker)}/{len(tasks)} "
              f"{ticker}: {len(rows)} entries", flush=True)
        _write_progress(progress, len(by_ticker), len(tasks))

    n_workers = _resolve_replay_workers(workers)
    if n_workers <= 1 or len(tasks) <= 1:
        for task in tasks:
            record(*_worker(task))
    else:
        with ProcessPoolExecutor(max_workers=n_workers) as pool:
            for future in as_completed([pool.submit(_worker, task) for task in tasks]):
                record(*future.result())
    progress.unlink(missing_ok=True)
    return [row for ticker in sorted(by_ticker) for row in by_ticker[ticker]]


# --- stages ------------------------------------------------------------------

def _previous(out_dir, arm, stage) -> dict:
    """The verdict JSON this stage consumes, or a refusal."""
    needed_stage, needed_verdict = REQUIRES[stage]
    path = stage_path(out_dir, arm, needed_stage)
    if not path.exists():
        _refuse(f"stage {stage} needs {path.name} -- run stage {needed_stage} first")
    previous = _load(path)
    if previous["verdict"] != needed_verdict:
        _refuse(f"arm {arm} closed at stage {needed_stage} with "
                f"{previous['verdict']} -- stage {stage} does not run")
    return previous


def _saved_rows(out_dir, arm, window_name, window, cells, build) -> list:
    """Rows from the rows file, building (and saving) them when absent."""
    path = rows_path(out_dir, arm, window_name)
    if not path.exists():
        _write(path, build(arm, window, cells), indent=None)
    return _load(path)


def _train_rows(out_dir, arm, build) -> list:
    return _saved_rows(out_dir, arm, "train", funnel.TRAIN, CELLS[arm], build)


def _stage0(out_dir, arm, build, n_resamples) -> dict:
    return funnel.stage0(_train_rows(out_dir, arm, build), arm)


def _stage1(out_dir, arm, build, n_resamples) -> dict:
    _previous(out_dir, arm, 1)
    rows = _train_rows(out_dir, arm, build)
    out = funnel.stage1(rows, arm, n_resamples=n_resamples)
    out["reports"] = [funnel.report(rows, arm, cell_key(m, b), n_resamples=n_resamples)
                      for m, b in CELLS[arm]]
    return out


def _stage2(out_dir, arm, build, n_resamples) -> dict:
    selected = _previous(out_dir, arm, 2)["selected"]
    return funnel.stage2(_train_rows(out_dir, arm, build), arm, selected["cell"])


def _stage3(out_dir, arm, build, n_resamples) -> dict:
    _previous(out_dir, arm, 3)
    selected = _load(stage_path(out_dir, arm, 1))["selected"]
    rows = _saved_rows(out_dir, arm, "validation", funnel.VALIDATION,
                       [(selected["m"], selected["b"])], build)
    out = funnel.stage3(rows, arm, selected["cell"], n_resamples=n_resamples)
    out["report"] = funnel.report(rows, arm, selected["cell"], n_resamples=n_resamples)
    return out


_STAGES = {0: _stage0, 1: _stage1, 2: _stage2, 3: _stage3}


def run_stage(arm, stage, out_dir, *, build, n_resamples: int = BOOTSTRAP_RESAMPLES) -> dict:
    """Run one stage and write its verdict JSON. Stages 0-2 are TRAIN-only
    and deterministic, so they may be re-run; stage 3 may not."""
    out_dir = Path(out_dir)
    target = stage_path(out_dir, arm, stage)
    if stage == 3 and target.exists():
        _refuse(f"{target.name} exists -- arm {arm}'s one VALIDATION shot is spent")
    out = _STAGES[stage](out_dir, arm, build, n_resamples)
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
    parser.add_argument("--arm", required=True, choices=sorted(CELLS))
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
    build = functools.partial(build_rows, tickers=args.tickers, workers=args.workers)
    out = run_stage(args.arm, args.stage, args.out_dir, build=build,
                    n_resamples=args.resamples)
    print(f"arm {args.arm} stage {args.stage}: {out['verdict']} "
          f"-> {stage_path(args.out_dir, args.arm, args.stage)}", flush=True)
    return 0 if out["verdict"] in ADVANCING else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scripts/test_measure_acceptance_exits.py`
Expected: all pass. Then `python -m radon cc -s -n C scripts/backtest/measure_acceptance_exits.py`. Nothing may be listed.

- [ ] **Step 5: Smoke the real replay on three tickers (TRAIN only, scratch directory)**

Invoke the `backtest-gate` skill first (this is a backtest run). Then:

```bash
python scripts/backtest/measure_acceptance_exits.py --arm B --stage 0 --tickers 3 --workers 1 --resamples 200 --out-dir logs/v129-smoke
python scripts/backtest/measure_acceptance_exits.py --arm Z --stage 0 --tickers 3 --resamples 200 --out-dir logs/v129-smoke
```

Expected: both print `arm <ARM> stage 0: POWERED` or `UNDERPOWERED` (either is fine on three tickers; exit code 1 on `UNDERPOWERED` is not an error here) and write a `-train-rows.json`. Check the arm Z rows file is non-empty and that at least one row has `"eligible": false` or note that none did. **This is a plumbing check on a partial universe. Do not read ΔExpR from it and do not carry any number forward.** Delete `logs/v129-smoke/` afterwards. Note the arm Z wall time for three tickers: V129-10 uses it to tell `backtest-runner` how long the full run should take.

- [ ] **Step 6: Commit**

```bash
git add scripts/backtest/measure_acceptance_exits.py tests/scripts/test_measure_acceptance_exits.py
git commit -m "feat(v129): measure_acceptance_exits stage driver with one-shot VALIDATION guard

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
