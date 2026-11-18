"""v232 layer 2 (spec ### Layer 2): replay signals, matching, selection counts.

Holdout (partner decision 4): no structure here carries a replay outcome, R or exit date.
"""
from __future__ import annotations

import dataclasses
import datetime as dt

from autopsy.eras import ERA_BOUNDARY_UTC

from . import records, sessions

OUTCOME_FIELDS = ("outcome", "r_multiple", "exit_date")
MATCH_SESSIONS = 1
REPLAY_ONLY_REASONS = ("gate_rejection", "open_position", "unexplained")
CREATED_AT_BUCKET = "created_at"
LIVE_ONLY_BUCKETS = sessions.ISSUE_BUCKETS + (CREATED_AT_BUCKET,)
UNEXPLAINED_BUCKET = "outside_session"
SIDES = ("long", "short")
ERAS = ("headline", "earlier")
_BOUNDARY_DAY = sessions.ny_time(ERA_BOUNDARY_UTC).date().isoformat()


def _side(direction: str) -> str:
    return "short" if direction in ("bearish", "short") else "long"


@dataclasses.dataclass(frozen=True)
class ReplaySignal:
    lane: str
    ticker: str
    direction: str
    source: str
    mode: str | None
    decision_date: str
    horizon_key: str
    strategy: str
    entry: float
    stop: float
    target: float

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ReplaySignal":
        leaked = sorted(set(d) & set(OUTCOME_FIELDS))
        if leaked:
            raise ValueError(f"replay signal carries outcome field(s) {leaked}")
        return cls(**{f.name: d[f.name] for f in dataclasses.fields(cls)})


def adapt(alert) -> ReplaySignal:
    """A scan_replay.ReplayAlert reduced to levels and dates; outcome fields are dropped here."""
    kept = {f.name: getattr(alert, f.name) for f in dataclasses.fields(ReplaySignal)}
    for key in ("entry", "stop", "target"):
        kept[key] = float(kept[key])
    return ReplaySignal(**kept)


@dataclasses.dataclass(frozen=True)
class LivePlan:
    plan_id: str
    ticker: str
    direction: str
    source: str | None
    session: dt.date
    horizon_key: str | None
    bucket: str
    entry: float | None
    stop: float | None
    target: float | None
    r_live_net: float | None


def _num(value) -> float | None:
    return None if value is None else float(value)


def _live_plan(rec, row) -> LivePlan:
    stamp, source = sessions.stamp_source(rec.plan)
    bucket = CREATED_AT_BUCKET if source == "created_at" else sessions.issue_bucket(stamp)
    plan, _ = records.rehydrate(rec.plan)
    entry = plan.entry_price if plan.entry_price is not None else plan.trigger_price
    return LivePlan(rec.plan_id, rec.ticker, rec.direction, rec.plan.get("source"),
                    sessions.issue_session(stamp), rec.plan.get("horizon_key"), bucket,
                    _num(entry), _num(plan.stop_loss), _num(plan.tp1),
                    None if row is None else row.r_live_net)


def live_plans(export, rows_by_plan: dict) -> list[LivePlan]:
    """Every exported plan (filled or not), in export order; live net R from its TradeRow."""
    return [_live_plan(rec, rows_by_plan.get(rec.plan_id)) for rec in export.records]


@dataclasses.dataclass
class MatchResult:
    matched: list          # [(LivePlan, ReplaySignal)]
    live_only: list
    replay_only: list
    outside_replay: list   # source "strategy"


def _candidate_pairs(signals, plans) -> list[tuple]:
    by_key: dict = {}
    for j, plan in enumerate(plans):
        by_key.setdefault((plan.ticker, _side(plan.direction)), []).append(j)
    pairs = []
    for i, signal in enumerate(signals):
        day = dt.date.fromisoformat(signal.decision_date)
        for j in by_key.get((signal.ticker, _side(signal.direction)), ()):
            apart = abs(sessions.sessions_apart(plans[j].session, day))
            if apart <= MATCH_SESSIONS:
                pairs.append((plans[j].horizon_key != signal.horizon_key, apart, j, i))
    return sorted(pairs)


def match(signals, plans) -> MatchResult:
    """One-to-one: same ticker and side within MATCH_SESSIONS of the issue session; ties go
    to the same horizon, then the nearest date, then plan and signal order."""
    outside = [p for p in plans if p.source == "strategy"]
    inside = [p for p in plans if p.source != "strategy"]
    used_plans: set = set()
    used_signals: set = set()
    pairs = []
    for _, _, j, i in _candidate_pairs(signals, inside):
        if j in used_plans or i in used_signals:
            continue
        used_plans.add(j)
        used_signals.add(i)
        pairs.append((j, i))
    pairs.sort()
    return MatchResult(matched=[(inside[j], signals[i]) for j, i in pairs],
                       live_only=[p for j, p in enumerate(inside) if j not in used_plans],
                       replay_only=[s for i, s in enumerate(signals) if i not in used_signals],
                       outside_replay=outside)


def _gate_on(signal, export) -> str | None:
    gates = sorted(str(r.get("gate")) for r in export.rejections
                   if r.get("ticker") == signal.ticker
                   and str(r.get("signal_date") or "")[:10] == signal.decision_date)
    return gates[0] if gates else None


def _held_on(rec, ticker: str, day: dt.date) -> bool:
    trade = rec.trade
    if trade is None or rec.ticker != ticker or not trade.get("opened_at"):
        return False
    closed = trade.get("closed_at")
    opened_ok = sessions.ny_time(trade["opened_at"]).date() <= day
    return opened_ok and (not closed or day <= sessions.ny_time(closed).date())


def replay_only_reason(signal, export) -> tuple[str, str | None]:
    """(reason, gate): a gate rejection for that ticker and day (first gate by name), else a
    live trade in the ticker (any direction) open that day, else unexplained."""
    gate = _gate_on(signal, export)
    if gate is not None:
        return "gate_rejection", gate
    day = dt.date.fromisoformat(signal.decision_date)
    if any(_held_on(rec, signal.ticker, day) for rec in export.records):
        return "open_position", None
    return "unexplained", None


def _ratio(num: float, den: float) -> float | None:
    return None if not den else num / den


def level_diffs(plan, signal) -> dict:
    """Levels only: entry in percent, stop and target distances as ratios (replay / live)."""
    if not plan.entry or plan.stop is None or plan.target is None:
        return {"entry_pct": None, "stop_ratio": None, "target_ratio": None}
    return {"entry_pct": (signal.entry / plan.entry - 1.0) * 100.0,
            "stop_ratio": _ratio(abs(signal.entry - signal.stop), abs(plan.entry - plan.stop)),
            "target_ratio": _ratio(abs(signal.target - signal.entry),
                                   abs(plan.target - plan.entry))}


def _empty_cell() -> dict:
    return {"matched": 0,
            "level_diffs": {"entry_pct": [], "stop_ratio": [], "target_ratio": []},
            "live_only": {"n": 0, "by_bucket": dict.fromkeys(LIVE_ONLY_BUCKETS, 0),
                          "unexplained": 0, "live_r_net": 0.0, "live_r_n": 0},
            "replay_only": {"n": 0, "by_reason": dict.fromkeys(REPLAY_ONLY_REASONS, 0),
                            "by_gate": {}},
            "outside_replay": 0}


def _signal_cell(counts: dict, signal) -> dict:
    era = "headline" if signal.decision_date >= _BOUNDARY_DAY else "earlier"
    return counts[_side(signal.direction)][era]


def _plan_cell(counts: dict, recs: dict, plan) -> dict:
    return counts[_side(plan.direction)][records.era_of(recs[plan.plan_id])]


def _add_matched(cell: dict, plan, signal) -> None:
    cell["matched"] += 1
    for key, value in level_diffs(plan, signal).items():
        if value is not None:
            cell["level_diffs"][key].append(value)


def _add_live_only(cell: dict, plan) -> None:
    live = cell["live_only"]
    live["n"] += 1
    live["by_bucket"][plan.bucket] += 1
    live["unexplained"] += int(plan.bucket == UNEXPLAINED_BUCKET)
    if plan.r_live_net is not None:
        live["live_r_net"] += plan.r_live_net
        live["live_r_n"] += 1


def _add_replay_only(cell: dict, signal, export) -> None:
    reason, gate = replay_only_reason(signal, export)
    replay = cell["replay_only"]
    replay["n"] += 1
    replay["by_reason"][reason] += 1
    if gate is not None:
        replay["by_gate"][gate] = replay["by_gate"].get(gate, 0) + 1


def selection_counts(result: MatchResult, export) -> dict:
    """counts[side][era]; every plan in `result` comes from live_plans(export, ...)."""
    counts = {side: {era: _empty_cell() for era in ERAS} for side in SIDES}
    recs = {rec.plan_id: rec for rec in export.records}
    for plan, signal in result.matched:
        _add_matched(_plan_cell(counts, recs, plan), plan, signal)
    for plan in result.live_only:
        _add_live_only(_plan_cell(counts, recs, plan), plan)
    for plan in result.outside_replay:
        _plan_cell(counts, recs, plan)["outside_replay"] += 1
    for signal in result.replay_only:
        _add_replay_only(_signal_cell(counts, signal), signal, export)
    return counts
