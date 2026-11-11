"""v142: the Partials tab -- TP1->TP2 conversion and runner counterfactuals.

Pure functions over TradePlanV2 records; no I/O. Every R goes through
`metrics.r_multiple` (initial-risk basis). The live book is a small,
non-pre-registered sample: nothing here is a gate.

Population: *filled* = plans that reached ACTIVE; *partial* = filled plans
whose status_history holds PARTIAL. A partial plan whose runner is still
open sits in the funnel and the `open` bucket only.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import mean

import numpy as np

from swingbot.core.analytics import metrics as m
from swingbot.core.analytics.intervals import wilson_interval
from swingbot.core.analytics.runner_path import (LADDER_R, close_reason, runner_leg,
                                                 session_span, tp1_leg, transition_day)
from swingbot.core.tracking.origin import in_cohort

THIN_N = 10
SPLIT_FRACTIONS = (0.33, 0.5, 0.67)
#: v219: a runner that got this far from TP1 to TP2 and then closed below
#: TP1 gave the move back (the Giveback ending).
GIVEBACK_PROGRESS = 0.5
#: v219 Runner endings: the four scorecard endings, which sum to the section.
ENDING_ROWS = ("tp2", "trail", "floor", "other")
_ENDING_OF_BUCKET = {"tp2": "tp2", "trail": "trail", "floor": "floor"}
#: Every partial trade lands in exactly one; "other" (an unknown close
#: reason) is reported only when non-empty, never dropped.
OUTCOME_BUCKETS = ("tp2", "trail", "floor", "stall", "time", "manual", "no_tp2", "open")
BREAKDOWN_DIMENSIONS = ("strategy", "horizon", "side", "month")
FUNNEL_STAGES = ("filled", "tp1", "runner_closed", "tp2")
_REASON_BUCKET = {
    "tp1_runner_tp2": "tp2", "tp1_runner_trail": "trail", "tp1_runner_be": "floor",
    "tp1_runner_progress_stall": "stall", "time_exit": "time", "manual": "manual",
    # v173: a bulk clear is still a human close; it is told apart only by the
    # override-fidelity report, never by the partials buckets.
    "manual_bulk": "manual",
}


def _is_real(value) -> bool:
    """A finite int/float; a bool is not one (JSON `true` is an int in Python)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


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
    tp2_r: float | None = None  # v219: plan TP2 in R, initial entry/stop basis; None without a TP2

    @property
    def closed(self) -> bool:
        return self.bucket != "open"

    @property
    def pathed(self) -> bool:
        """A runner_path stamp carrying the fields the ladder and giveback read,
        with the types they read: a malformed stamp is unpathed, never a crash."""
        path = self.runner_path
        return (isinstance(path, dict) and _is_real(path.get("mfe_r"))
                and isinstance(path.get("ladder"), dict))

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

    @property
    def decidable(self) -> bool:
        """v219 path filter: a runner whose path figures can be trusted. A manual
        close is out by bucket (its stamp never saw the exit), not by r_runner."""
        return (self.pathed and self.r_runner is not None and self.bucket != "manual"
                and self.tp2_r is not None and self.tp2_r > self.r_tp1)

    @property
    def progress(self) -> float | None:
        """How far the runner got from TP1 towards TP2, clamped to [0, 1]."""
        if not self.decidable:
            return None
        raw = (self.runner_path["mfe_r"] - self.r_tp1) / (self.tp2_r - self.r_tp1)
        return min(1.0, max(0.0, raw))


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
    if not in_cohort(plan, getattr(scope, "origin", None)):
        return False
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


def _tp2_r(plan, view: dict) -> float | None:
    """The plan's TP2 in R on the initial entry/stop basis; None without a TP2."""
    return None if plan.tp2 is None else _one_leg_r(view, {"exit_price": plan.tp2})


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
        _span(fill, tp1), _span(tp1, exit_), _span(fill, exit_), _tp2_r(plan, view))


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


def _giveback(runners: list[PartialTrade]) -> list[float]:
    """MFE R minus banked runner R, per runner (unclamped). The Runner endings
    "Gave back" column uses the same formula."""
    return [round(t.runner_path["mfe_r"] - t.r_runner, 4) for t in runners]


def _giveback_strip(closed: list[PartialTrade]) -> dict:
    """The Giveback strip over the v219 path filter (manual, no-TP2 and
    no-distance runners out), with the count it dropped."""
    decidable = [t for t in closed if t.decidable]
    return {"giveback": _giveback(decidable), "giveback_excluded": len(closed) - len(decidable)}


def _exclusions(closed: list[PartialTrade]) -> dict:
    """Closed runners left out of a figure, counted so none vanish silently."""
    return {"path_unavailable": sum(1 for t in closed if not t.pathed),
            "runner_r_unavailable": sum(1 for t in closed if t.r_runner is None)}


def counterfactuals(trades: list[PartialTrade]) -> dict:
    """The four what-ifs, over closed runners with a known runner R; the
    ladder further needs a stamped runner_path, the giveback strip the v219
    path filter (`PartialTrade.decidable`)."""
    closed = [t for t in trades if t.closed]
    measured = [t for t in closed if t.measured]
    pathed = [t for t in measured if t.pathed]
    return {
        "actual_exp_r": _mean(t.blended_r for t in measured),
        "all_out_exp_r": _mean(t.r_tp1 for t in measured),
        **_giveback_strip(closed),
        "ladder": [_ladder_row(pathed, level) for level in LADDER_R],
        "split": [_split_row(measured, fraction) for fraction in SPLIT_FRACTIONS],
        **_exclusions(closed),
    }


# -- runner endings (v219) -------------------------------------------------------

#: The path filter's conditions, in counting order. Each is the negation of one
#: clause of `PartialTrade.decidable`, so first-failing counts sum to n - decidable.
_PATH_CHECKS = (
    ("runner_r_unavailable", lambda t: t.r_runner is None),
    ("manual_close", lambda t: t.bucket == "manual"),
    ("unpathed", lambda t: not t.pathed),
    ("no_tp2_distance", lambda t: t.tp2_r is None or t.tp2_r <= t.r_tp1),
)


def _section(trades: list[PartialTrade]) -> list[PartialTrade]:
    """The Runner endings population: closed runners of plans that have a TP2."""
    return [t for t in trades if t.closed and t.bucket != "no_tp2"]


def ending_of(trade: PartialTrade) -> str:
    """The scorecard ending of a closed runner; stall, time, manual and
    unknown close reasons all read as "other"."""
    return _ENDING_OF_BUCKET.get(trade.bucket, "other")


def is_giveback(trade: PartialTrade) -> bool:
    """Got at least halfway from TP1 to TP2, then closed below TP1, whatever
    the ending. Exactly at TP1 is not a giveback."""
    return (trade.decidable and trade.progress >= GIVEBACK_PROGRESS
            and trade.r_runner < trade.r_tp1)


def _share(k: int, n: int) -> dict:
    """A share and its Wilson 95% interval, percentages to 1 dp; None when n is 0."""
    bounds = wilson_interval(k, n)
    if bounds is None:
        return {"share": None, "lo": None, "hi": None}
    lo, hi = bounds
    return {"share": _rate(k, n), "lo": round(100.0 * lo, 1), "hi": round(100.0 * hi, 1)}


def _share_fields(ending: str, k: int, n: int) -> dict:
    return {"ending": ending, "n": k, "denominator": n, **_share(k, n), "thin": k < THIN_N}


def _total(values: list[float]) -> float | None:
    return round(sum(values), 4) if values else None


def _r_fields(group: list[PartialTrade]) -> dict:
    """R columns, over runners whose runner R is known."""
    measured = [t for t in group if t.r_runner is not None]
    sessions = [t.hold_tp1_exit for t in measured if t.hold_tp1_exit is not None]
    return {"r_n": len(measured),
            "avg_r": _mean(t.r_runner for t in measured),
            "median_r": _median([t.r_runner for t in measured]),
            "total_r": _total([(1.0 - t.fraction) * t.r_runner for t in measured]),
            "vs_all_out": _mean(t.delta_r for t in measured),
            "sessions": _median(sessions)}


def _path_fields(group: list[PartialTrade]) -> dict:
    """Path columns, over decidable runners only."""
    decidable = [t for t in group if t.decidable]
    progress = _mean(t.progress for t in decidable)
    return {"path_n": len(decidable),
            "best_r": _mean(t.runner_path["mfe_r"] for t in decidable),
            "progress": None if progress is None else round(100.0 * progress, 1),
            "gave_back": _mean(t.runner_path["mfe_r"] - t.r_runner for t in decidable)}


def _row(ending: str, group: list[PartialTrade], denominator: int) -> dict:
    return {**_share_fields(ending, len(group), denominator), **_r_fields(group),
            **_path_fields(group)}


def ending_rows(runners: list[PartialTrade]) -> list[dict]:
    """The five scorecard rows over a `_section` list. The four endings share
    the section as denominator; Giveback (any ending) is over decidable runners
    and is not part of that 100%."""
    rows = [_row(ending, [t for t in runners if ending_of(t) == ending], len(runners))
            for ending in ENDING_ROWS]
    decidable = [t for t in runners if t.decidable]
    rows.append(_row("giveback", [t for t in decidable if is_giveback(t)], len(decidable)))
    return rows


def path_exclusions(runners: list[PartialTrade]) -> dict:
    """Section runners left out of the path figures, by first failing reason."""
    counts = {name: 0 for name, _ in _PATH_CHECKS}
    for trade in runners:
        reason = next((name for name, fails in _PATH_CHECKS if fails(trade)), None)
        if reason is not None:
            counts[reason] += 1
    return counts


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
