"""v142: the Partials tab -- TP1->TP2 conversion and runner counterfactuals.

Pure functions over TradePlanV2 records; no I/O. Every R goes through
`metrics.r_multiple` (initial-risk basis). The live book is a small,
non-pre-registered sample: nothing here is a gate.

Population: *filled* = plans that reached ACTIVE; *partial* = filled plans
whose status_history holds PARTIAL. A partial plan whose runner is still
open sits in the funnel and the `open` bucket only.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import mean

import numpy as np

from swingbot.core.analytics import metrics as m
from swingbot.core.analytics.runner_path import (LADDER_R, close_reason, runner_leg,
                                                 session_span, tp1_leg, transition_day)

THIN_N = 10
SPLIT_FRACTIONS = (0.33, 0.5, 0.67)
#: Every partial trade lands in exactly one; "other" (an unknown close
#: reason) is reported only when non-empty, never dropped.
OUTCOME_BUCKETS = ("tp2", "trail", "floor", "stall", "time", "manual", "no_tp2", "open")
BREAKDOWN_DIMENSIONS = ("strategy", "horizon", "side", "month")
FUNNEL_STAGES = ("filled", "tp1", "runner_closed", "tp2")
_REASON_BUCKET = {
    "tp1_runner_tp2": "tp2", "tp1_runner_trail": "trail", "tp1_runner_be": "floor",
    "tp1_runner_progress_stall": "stall", "time_exit": "time", "manual": "manual",
}


@dataclass(frozen=True)
class PartialTrade:
    plan_id: str
    strategy: str
    horizon: str
    side: str
    month: str                  # YYYY-MM of the TP1 session
    fraction: float             # the plan's own tp1_fraction
    r_tp1: float
    r_runner: float | None      # None: runner open, or a manual close with no price
    blended_r: float | None     # metrics.r_multiple over both legs
    bucket: str
    runner_path: dict | None
    hold_entry_tp1: int | None
    hold_tp1_exit: int | None
    hold_entry_exit: int | None

    @property
    def closed(self) -> bool:
        return self.bucket != "open"

    @property
    def measured(self) -> bool:
        """A closed runner whose runner R is known."""
        return self.closed and self.r_runner is not None

    @property
    def delta_r(self) -> float | None:
        """Blended R minus all-out-at-TP1 R."""
        if not self.measured:
            return None
        return (1.0 - self.fraction) * (self.r_runner - self.r_tp1)


# -- population ----------------------------------------------------------------

def _has(plan, status: str) -> bool:
    return any(entry.get("status") == status for entry in plan.status_history or [])


def is_filled(plan) -> bool:
    return _has(plan, "ACTIVE")


def is_partial(plan) -> bool:
    return _has(plan, "PARTIAL")


def _in_range(day, scope) -> bool:
    if scope.start is None and scope.end is None:
        return True
    if day is None:
        return False
    text = day.isoformat()
    return (scope.start is None or text >= scope.start) and (scope.end is None or text <= scope.end)


def _matches(plan, scope) -> bool:
    if scope.ledger != "both" and (plan.ledger or "main") != scope.ledger:
        return False
    wanted = ((scope.strategy, plan.strategy), (scope.horizon, plan.horizon_key),
              (scope.direction, plan.direction))
    return all(want is None or want == have for want, have in wanted)


def select_plans(plans: list, scope) -> list:
    """Filled plans inside a BookScope. The date range filters on FILL date."""
    return [plan for plan in plans if is_filled(plan)
            and _in_range(transition_day(plan, "ACTIVE"), scope) and _matches(plan, scope)]


# -- one trade -----------------------------------------------------------------

def outcome_bucket(plan) -> str:
    if plan.status != "CLOSED":
        return "open"
    if plan.tp2 is None:
        return "no_tp2"
    return _REASON_BUCKET.get(close_reason(plan), "other")


def _view(plan) -> dict | None:
    if plan.entry_price is None or plan.stop_loss is None:
        return None
    return {"entry": plan.entry_price, "stop_loss": plan.stop_loss, "direction": plan.direction}


def _one_leg_r(view: dict, leg: dict) -> float | None:
    return m.r_multiple({**view, "legs": [{**leg, "fraction": 1.0}]})


def _runner_or_manual(plan, manual_exits: dict) -> dict | None:
    """The runner leg; for a manual close (which records none on the plan) a
    leg built from the linked trade's exit price, when the trade has one."""
    leg = runner_leg(plan)
    if leg is not None or plan.status != "CLOSED":
        return leg
    price = manual_exits.get(plan.plan_id)
    if price is None:
        return None
    return {"fraction": round(1.0 - plan.tp1_fraction, 6), "exit_price": float(price),
            "reason": "manual"}


def _span(start, end) -> int | None:
    return None if start is None or end is None else session_span(start, end)


def partial_trade(plan, manual_exits: dict | None = None) -> PartialTrade | None:
    """One partial plan as a PartialTrade; None when it cannot be read (no
    fill price, zero risk, no TP1 leg)."""
    view, leg1 = _view(plan), tp1_leg(plan)
    r_tp1 = _one_leg_r(view, leg1) if view is not None and leg1 is not None else None
    if r_tp1 is None:
        return None
    runner = _runner_or_manual(plan, manual_exits or {})
    r_runner = _one_leg_r(view, runner) if runner is not None else None
    blended = m.r_multiple({**view, "legs": [leg1, runner]}) if runner is not None else None
    fill, tp1, exit_ = (transition_day(plan, s) for s in ("ACTIVE", "PARTIAL", "CLOSED"))
    return PartialTrade(
        plan.plan_id, plan.strategy, plan.horizon_key, plan.direction,
        tp1.isoformat()[:7] if tp1 else "unknown", float(plan.tp1_fraction), r_tp1,
        r_runner, blended, outcome_bucket(plan), plan.runner_path,
        _span(fill, tp1), _span(tp1, exit_), _span(fill, exit_))


# -- aggregates ----------------------------------------------------------------

def _rate(hits: int, n: int | None) -> float | None:
    return None if not n else round(100.0 * hits / n, 1)


def _mean(values) -> float | None:
    values = [v for v in values if v is not None]
    return round(mean(values), 4) if values else None


def _median(values) -> float | None:
    return float(np.median(values)) if values else None


def kpis(trades: list[PartialTrade], decided: int | None) -> dict:
    """The KPI set. `decided` = filled plans that are no longer open pre-TP1
    (the TP1-rate denominator); None where it has no meaning (month rows)."""
    closed = [t for t in trades if t.closed]
    convertible = [t for t in closed if t.bucket != "no_tp2"]
    deltas = [t.delta_r for t in closed if t.measured]
    tp1_exit = [t.hold_tp1_exit for t in closed if t.hold_tp1_exit is not None]
    return {
        "tp1_rate": None if decided is None else _rate(len(trades), decided),
        "tp1_rate_n": decided,
        "tp1_tp2_rate": _rate(sum(t.bucket == "tp2" for t in convertible), len(convertible)),
        "tp1_tp2_n": len(convertible),
        "beat_all_out": _rate(sum(d > 0 for d in deltas), len(deltas)),
        "beat_all_out_n": len(deltas),
        "mean_runner_delta_r": _mean(deltas),
        "median_tp1_exit_sessions": _median(tp1_exit),
        "tp1_exit_n": len(tp1_exit),
    }


def funnel(plans: list, trades: list[PartialTrade]) -> list[dict]:
    counts = (len(plans), len(trades), sum(t.closed for t in trades),
              sum(t.bucket == "tp2" for t in trades))
    return [{"stage": stage, "n": n} for stage, n in zip(FUNNEL_STAGES, counts)]


def outcomes(trades: list[PartialTrade]) -> list[dict]:
    rows = []
    for bucket in (*OUTCOME_BUCKETS, "other"):
        group = [t for t in trades if t.bucket == bucket]
        if bucket == "other" and not group:
            continue
        rows.append({"bucket": bucket, "n": len(group), "share": _rate(len(group), len(trades)),
                     "avg_runner_r": _mean(t.r_runner for t in group)})
    return rows


def _ladder_row(pathed: list[PartialTrade], level: float) -> dict:
    key = f"{level:.1f}"
    hits = [bool(t.runner_path["ladder"].get(key)) for t in pathed]
    cf = [t.fraction * t.r_tp1 + (1.0 - t.fraction) * (level if hit else t.r_runner)
          for t, hit in zip(pathed, hits)]
    return {"level_r": level, "touch_rate": _rate(sum(hits), len(pathed)),
            "cf_exp_r": _mean(cf), "n": len(pathed)}


def _split_row(measured: list[PartialTrade], fraction: float) -> dict:
    values = [fraction * t.r_tp1 + (1.0 - fraction) * t.r_runner for t in measured]
    return {"fraction": fraction, "exp_r": _mean(values), "n": len(measured)}


def _giveback(pathed: list[PartialTrade]) -> list[float]:
    """MFE R minus banked runner R, per trade with a stamped path."""
    return [round(t.runner_path["mfe_r"] - t.r_runner, 4) for t in pathed]


def _exclusions(closed: list[PartialTrade]) -> dict:
    """Closed runners left out of a figure, counted so none vanish silently."""
    return {"path_unavailable": sum(1 for t in closed if not t.runner_path),
            "runner_r_unavailable": sum(1 for t in closed if t.r_runner is None)}


def counterfactuals(trades: list[PartialTrade]) -> dict:
    """The four what-ifs, over closed runners with a known runner R; the
    ladder and giveback further need a stamped runner_path."""
    closed = [t for t in trades if t.closed]
    measured = [t for t in closed if t.measured]
    pathed = [t for t in measured if t.runner_path]
    return {
        "actual_exp_r": _mean(t.blended_r for t in measured),
        "all_out_exp_r": _mean(t.r_tp1 for t in measured),
        "giveback": _giveback(pathed),
        "ladder": [_ladder_row(pathed, level) for level in LADDER_R],
        "split": [_split_row(measured, fraction) for fraction in SPLIT_FRACTIONS],
        **_exclusions(closed),
    }


def _quantiles(points: list[int]) -> dict:
    if not points:
        return {"p25": None, "median": None, "p75": None, "points": []}
    p25, median, p75 = (float(v) for v in np.percentile(points, [25, 50, 75]))
    return {"p25": p25, "median": median, "p75": p75, "points": sorted(points)}


def holds(trades: list[PartialTrade]) -> dict:
    """Trading sessions per stage; open runners only in the entry->TP1 stage."""
    closed = [t for t in trades if t.closed]
    return {
        "entry_tp1": _quantiles([t.hold_entry_tp1 for t in trades if t.hold_entry_tp1 is not None]),
        "tp1_exit": _quantiles([t.hold_tp1_exit for t in closed if t.hold_tp1_exit is not None]),
        "entry_exit": _quantiles([t.hold_entry_exit for t in closed if t.hold_entry_exit is not None]),
    }


_TRADE_KEY = {"strategy": lambda t: t.strategy, "horizon": lambda t: t.horizon,
              "side": lambda t: t.side, "month": lambda t: t.month}
_PLAN_KEY = {"strategy": lambda p: p.strategy, "horizon": lambda p: p.horizon_key,
             "side": lambda p: p.direction}


def _decided_by(dimension: str, plans: list) -> dict:
    if dimension not in _PLAN_KEY:
        return {}
    counts: dict[str, int] = {}
    for plan in plans:
        if plan.status != "ACTIVE":
            key = _PLAN_KEY[dimension](plan)
            counts[key] = counts.get(key, 0) + 1
    return counts


def breakdown(dimension: str, trades: list[PartialTrade], plans: list) -> list[dict]:
    """KPI rows per key. Month is the month of the TP1 hit, so it has no
    TP1-rate denominator; a key with filled plans but no partial still shows."""
    groups: dict[str, list[PartialTrade]] = {}
    for trade in trades:
        groups.setdefault(_TRADE_KEY[dimension](trade), []).append(trade)
    decided = _decided_by(dimension, plans)
    rows = []
    for key in sorted(set(groups) | set(decided)):
        group = groups.get(key, [])
        denominator = decided.get(key, 0) if dimension in _PLAN_KEY else None
        rows.append({"key": key, "n": len(group), "thin": len(group) < THIN_N,
                     **kpis(group, denominator)})
    return rows


def build_report(plans: list, manual_exits: dict | None = None) -> dict:
    """Everything the Partials tab draws, over already-scoped filled plans."""
    partials = [plan for plan in plans if is_partial(plan)]
    trades = [t for plan in partials if (t := partial_trade(plan, manual_exits)) is not None]
    decided = sum(1 for plan in plans if plan.status != "ACTIVE")
    return {
        "kpis": kpis(trades, decided),
        "funnel": funnel(plans, trades),
        "outcomes": outcomes(trades),
        "counterfactuals": counterfactuals(trades),
        "holds": holds(trades),
        "breakdowns": {dim: breakdown(dim, trades, plans) for dim in BREAKDOWN_DIMENSIONS},
        "thin_n": THIN_N,
        "population": {"filled": len(plans), "partial": len(trades),
                       "unreadable": len(partials) - len(trades)},
    }
