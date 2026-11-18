"""v232 mechanism tags (spec ### Layer 1, Mechanism tags).

Descriptive cut-offs, frozen by the spec (Claude's call 9). Every rule is one entry
of RULES, so the classifier stays table-driven (complexity < 15 per function).
"""
from __future__ import annotations

import dataclasses
import datetime as dt
from typing import Callable

from swingbot.core.analytics.metrics import close_reason_text

from . import sessions

TAGS = ("same_day_exit", "wick_missed", "both_levels_bar", "gap_through",
        "exit_outside_rth", "entry_outside_rth", "first_15min", "live_stop_moved",
        "levels_edited", "scaled_out", "time_stop", "earnings_in_window",
        "short_gap_against", "outcome_flip_live_better", "outcome_flip_live_worse")
SLIP_TAG_R = 0.05
SHORT_GAP_PCT = 0.03
FIRST_MINUTES = 15
LEVEL_TOLERANCE = 0.005
TIME_REASONS = ("timeout", "time_exit", "stall", "hold")
STOP_MARKERS = ("be_armed_session", "runner_floor_session")


@dataclasses.dataclass(frozen=True)
class TagInput:
    rec: object
    df: object
    fill_pos: int
    exit_pos: int | None
    live_risk: float
    r_live: float
    r_exit_only: float
    live_class: str
    exit_only_class: str


def _sign(t) -> int:
    return -1 if t.rec.side == "short" else 1


def _last(t) -> int:
    return len(t.df) - 1 if t.exit_pos is None else t.exit_pos


def _after_fill(t) -> range:
    return range(max(t.fill_pos + 1, 1), _last(t) + 1)


def _held_through(t) -> range:
    end = len(t.df) if t.exit_pos is None else t.exit_pos
    return range(t.fill_pos + 1, end)


def _bar(t, k: int) -> tuple[float, float, float, float]:
    row = t.df.iloc[k]
    return float(row["Open"]), float(row["High"]), float(row["Low"]), float(row["Close"])


def _targets(plan: dict) -> list[float]:
    return [float(plan[key]) for key in ("tp1", "tp2") if plan.get(key) is not None]


def _differs(a, b) -> bool:
    return a is not None and b is not None and abs(float(a) - float(b)) > LEVEL_TOLERANCE


def _marker(plan: dict) -> dt.date | None:
    days = [dt.date.fromisoformat(str(plan[k])[:10]) for k in STOP_MARKERS if plan.get(k)]
    return min(days) if days else None


def _stop_on(t, k: int) -> float:
    plan, marker = t.rec.plan, _marker(t.rec.plan)
    moved = plan.get("working_stop")
    if moved is not None and marker is not None and t.df.index[k].date() > marker:
        return float(moved)
    return float(plan["stop_loss"])


def _touches_stop(t, k: int, stop: float) -> bool:
    _, high, low, _ = _bar(t, k)
    return low <= stop if _sign(t) > 0 else high >= stop


def _holds_both(t, k: int) -> bool:
    _, high, low, _ = _bar(t, k)
    stop, sign = float(t.rec.plan["stop_loss"]), _sign(t)
    if not _touches_stop(t, k, stop):
        return False
    return any((high >= x) if sign > 0 else (low <= x) for x in _targets(t.rec.plan))


def _opens_beyond(t, k: int) -> bool:
    opened, sign = _bar(t, k)[0], _sign(t)
    if sign * (opened - float(t.rec.plan["stop_loss"])) <= 0:
        return True
    return any(sign * (opened - x) >= 0 for x in _targets(t.rec.plan))


def _gap_bar(t) -> int | None:
    return next((k for k in _after_fill(t) if _opens_beyond(t, k)), None)


def _short_gap(t) -> bool:
    if t.rec.side != "short":
        return False
    return any(_bar(t, k)[0] > _bar(t, k - 1)[3] * (1 + SHORT_GAP_PCT) for k in _after_fill(t))


def _same_day(t) -> bool:
    trade = t.rec.trade
    return sessions.ny_time(trade["opened_at"]).date() == sessions.ny_time(trade["closed_at"]).date()


def _early(t) -> bool:
    stamps = (t.rec.trade["opened_at"], t.rec.trade["closed_at"])
    minutes = [sessions.minutes_after_open(s) for s in stamps]
    return any(m is not None and m < FIRST_MINUTES for m in minutes)


def _stop_moved(t) -> bool:
    plan = t.rec.plan
    return _differs(plan.get("working_stop"), plan["stop_loss"]) or _marker(plan) is not None


def _edited(t) -> bool:
    plan, trade = t.rec.plan, t.rec.trade
    return (_differs(trade.get("stop_loss"), plan["stop_loss"])
            or _differs(trade.get("take_profit"), plan.get("tp1")))


def _scaled(t) -> bool:
    if any(float(leg.get("fraction", 1.0)) < 1.0 for leg in t.rec.trade.get("legs") or []):
        return True
    return any(h.get("reason") == "tp1_partial" for h in t.rec.plan.get("status_history") or [])


def _days_to_earnings(rec):
    for doc in (rec.trade, rec.journal or {}):
        value = (doc.get("risk_features") or {}).get("days_to_earnings")
        if value is not None:
            return value
    return None


def _earnings(t) -> bool:
    days = _days_to_earnings(t.rec)
    if days is None:
        return False
    trade = t.rec.trade
    held = sessions.sessions_apart(sessions.issue_session(trade["opened_at"]),
                                   sessions.issue_session(trade["closed_at"]))
    return 0 <= float(days) <= held


RULES: dict[str, Callable[[TagInput], bool]] = {
    "same_day_exit": _same_day,
    "wick_missed": lambda t: any(_touches_stop(t, k, _stop_on(t, k)) for k in _held_through(t)),
    "both_levels_bar": lambda t: any(_holds_both(t, k) for k in _after_fill(t)),
    "gap_through": lambda t: _gap_bar(t) is not None,
    "exit_outside_rth": lambda t: not sessions.in_regular_session(t.rec.trade["closed_at"]),
    "entry_outside_rth": lambda t: not sessions.in_regular_session(t.rec.trade["opened_at"]),
    "first_15min": _early,
    "live_stop_moved": _stop_moved,
    "levels_edited": _edited,
    "scaled_out": _scaled,
    "time_stop": lambda t: any(s in close_reason_text(t.rec.trade) for s in TIME_REASONS),
    "earnings_in_window": _earnings,
    "short_gap_against": _short_gap,
    "outcome_flip_live_better": lambda t: (t.live_class, t.exit_only_class) == ("win", "loss"),
    "outcome_flip_live_worse": lambda t: (t.live_class, t.exit_only_class) == ("loss", "win"),
}


def tags_for(t: TagInput) -> tuple[str, ...]:
    return tuple(name for name in TAGS if RULES[name](t))
