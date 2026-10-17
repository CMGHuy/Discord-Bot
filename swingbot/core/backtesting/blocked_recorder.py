"""v147: the TRAIN gate-row recorder's shared pieces.

The row shape both TRAIN recorders write (``--record-blocked``) and the
report reads, the TRAIN-window guard, and the ``risk_cap`` shadow: a
record-only copy of ``analyze.attach_plan_v2``'s plan-time 2% check. It is
unrelated to exit_sim's fill-time ``_not_triggered("risk_cap")`` cancel.
No RS row is ever written on TRAIN (v34 closed).
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

from swingbot.core.backtesting.gate_counterfactual import result_from_exit
from swingbot.core.risk_limits import HARD_MAX_PLANNED_LOSS_PCT, planned_loss_pct

TRAIN_WINDOW = ("2020-01-01", "2023-12-31")
POPULATIONS = ("train", "live")
ARMS = ("blocked", "taken")
SOURCES = ("strategy", "confluence", "short_lane")
GATES = ("rs", "plan_rejected", "compression")
ROW_STATUSES = ("filled", "no-fill", "no-plan", "no-data")
_CAP_EPSILON = 1e-9               # analyze.attach_plan_v2's own tolerance


def _refuse(message: str) -> None:
    print(f"--record-blocked: {message}", file=sys.stderr, flush=True)
    raise SystemExit(2)


def require_train_window(date_from: str | None, date_to: str | None, *,
                         validation: bool = False) -> None:
    """Exit 2 unless the run sits inside TRAIN (2020-01-01..2023-12-31)."""
    start, end = TRAIN_WINDOW
    if validation:
        _refuse("refuses --validation; gate rows are recorded on TRAIN only")
    if date_from is not None and str(date_from) < start:
        _refuse(f"--from {date_from} is before the TRAIN window ({start})")
    if date_to is not None and str(date_to) > end:
        _refuse(f"--to {date_to} is after the TRAIN window ({end})")


def _planned_loss(plan) -> float:
    return planned_loss_pct(plan.trigger_price, plan.stop_loss)


def over_cap(plan) -> bool:
    """attach_plan_v2's plan-time check, verbatim: True means live rejects as risk_cap."""
    return _planned_loss(plan) > HARD_MAX_PLANNED_LOSS_PCT + _CAP_EPSILON


def risk_cap_margin(plan) -> float:
    """Planned loss % of entry past the 2% cap (positive = over the cap)."""
    return _planned_loss(plan) - HARD_MAX_PLANNED_LOSS_PCT


def dollar_risk(cf_r: float | None, planned_loss: float | None) -> float | None:
    """The outcome in units of the 2% dollar cap at the notional a 2%-wide stop sizes."""
    if cf_r is None or planned_loss is None or not math.isfinite(planned_loss):
        return None
    return float(cf_r) * float(planned_loss) / HARD_MAX_PLANNED_LOSS_PCT


def _check(name: str, value, allowed: tuple) -> None:
    if value not in allowed:
        raise ValueError(f"gate row {name}={value!r} not in {allowed}")


def gate_row(*, population, arm, source, ticker, strategy, horizon, direction, signal_date,
             gate, reason, margin, cf_status, cf_r, win, planned_loss_pct=None,
             expiry_bars=None, in_sample=False) -> dict:
    """One row of the shared gate-row shape (see the plan index)."""
    for name, value, allowed in (("population", population, POPULATIONS), ("arm", arm, ARMS),
                                 ("source", source, SOURCES), ("gate", gate, GATES),
                                 ("cf_status", cf_status, ROW_STATUSES)):
        _check(name, value, allowed)
    filled = cf_status == "filled"
    r = float(cf_r) if filled and cf_r is not None else None
    return {
        "population": population, "arm": arm, "source": source, "ticker": ticker,
        "strategy": strategy, "horizon": horizon, "direction": direction,
        "signal_date": str(signal_date), "entry_date": str(signal_date),
        "gate": gate, "reason": reason,
        "margin": None if margin is None else float(margin),
        "cf_status": cf_status, "cf_r": r, "win": bool(win) if filled and win is not None else None,
        "planned_loss_pct": None if planned_loss_pct is None else float(planned_loss_pct),
        "dollar_risk": dollar_risk(r, planned_loss_pct),
        "expiry_bars": None if expiry_bars is None else int(expiry_bars),
        "in_sample": bool(in_sample),
    }


def row_from_exit(exit_result, plan, **row_fields) -> dict:
    """A gate row from a replayed ExitResult; ticker/strategy/horizon/direction/expiry from the plan."""
    status, cf_r, win = result_from_exit(exit_result)
    fields = {"ticker": plan.ticker, "strategy": plan.strategy, "horizon": plan.horizon_key,
              "direction": plan.direction, "expiry_bars": plan.expiry_bars}
    fields.update(row_fields)
    return gate_row(cf_status=status, cf_r=cf_r, win=win, **fields)


def write_gate_rows(rows, path) -> int:
    """Write rows as JSONL (overwrite); returns the row count."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with target.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
            count += 1
    return count
