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
