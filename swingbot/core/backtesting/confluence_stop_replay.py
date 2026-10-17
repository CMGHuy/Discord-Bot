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
