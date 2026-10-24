"""v188: cancelled and filled plans to replay rows (pure).

Spec: docs/superpowers/specs/2026-10-23-v188-cancelled-plan-precision-design.md.
Bars arrive through an injected `loader(ticker) -> frame | None`, as in
`day_sparklines.py`. A plan whose row cannot be scored stays a row with an
`excluded` code: it is shown, never dropped and never scored.

The cancel is the LAST `status_history` entry with status CANCELLED; its
`reason` is bucketed into the closed allowlist REASONS, "manual" (the
partner's decision, out of scope) or OTHER. A `risk_cap` cancel yields two
rows: the plan's trigger, and the price that crossed it (`recorded` on the
history entry from v188 on, else `estimated` from the cancel-day open).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Callable

import pandas as pd

from swingbot.core.analytics.cancel_replay import (Replay, replay, split_guard_ok,
                                                   trading_date, window_end)
from swingbot.core.analytics.partials import is_filled
from swingbot.core.planning.plan_types import PlanStatus, plan_from_dict
from swingbot.core.planning.stop_scope import plan_stop_ceiling
from swingbot.core.risk_limits import planned_loss_pct
from swingbot.core.tracking.origin import NEXT_SESSION, origin_of

REASONS = ("risk_cap", "invalidated", "expired")
OTHER = "other"
MANUAL = "manual"
FILLED = "filled"
ENTRY_MODELS = ("trigger", "cancel_fill")
EXCLUSIONS = ("no_bars", "split_guard", "bad_levels", "unknown_horizon", "no_cancel_entry")
Loader = Callable[[str], "pd.DataFrame | None"]


@dataclass(frozen=True)
class CancelRow:
    plan_id: str
    ticker: str
    strategy: str
    horizon_key: str
    direction: str              # "long" | "short"
    origin: str                 # "regular" | "next_session"
    reason: str                 # REASONS member, OTHER, or FILLED (baseline rows)
    raw_reason: str | None
    cancel_day: date            # fill day for FILLED rows
    entry_model: str            # ENTRY_MODELS member
    entry_source: str | None    # "estimated" | "recorded" on cancel_fill rows, else None
    entry: float | None
    stop: float | None
    tp1: float | None
    badge: str | None
    stop_ceiling_pct: float | None
    cap_size_pct: float | None
    replay: Replay | None
    excluded: str | None        # EXCLUSIONS member or None

    @property
    def entry_date(self) -> str:
        """cancel_day as ISO text; the bootstrap's week key."""
        return self.cancel_day.isoformat()


def reason_bucket(raw: str | None) -> str:
    """REASONS -> itself, "manual" -> MANUAL, anything else -> OTHER."""
    if raw in REASONS:
        return raw
    return MANUAL if raw == MANUAL else OTHER


# -- plan access ---------------------------------------------------------------

def _as_plan(p):
    return plan_from_dict(p) if isinstance(p, dict) else p


def _entries(plan, status: str) -> list[dict]:
    return [e for e in plan.status_history or [] if e.get("status") == status]


def _day_of(entry: dict | None, plan) -> date:
    return trading_date((entry or {}).get("at") or plan.created_at)


def _ceiling(plan) -> float | None:
    try:
        return plan_stop_ceiling(plan)
    except (KeyError, TypeError, ValueError):
        return None


def _last_cancel(plan) -> dict | None:
    cancels = _entries(plan, PlanStatus.CANCELLED)
    return cancels[-1] if cancels else None


# -- row building --------------------------------------------------------------

def _cap_size(ceiling: float | None, entry: float | None, stop: float | None) -> float | None:
    """Share (%) of a normal position that keeps the planned loss at the ceiling."""
    if ceiling is None or entry is None:
        return None
    loss = planned_loss_pct(entry, stop)
    if not math.isfinite(loss) or loss <= 0:
        return None
    return round(100.0 * ceiling / loss, 2)


def _levels_ok(bullish: bool, entry, stop, tp1) -> bool:
    if entry is None or stop is None or tp1 is None:
        return False
    risk = entry - stop if bullish else stop - entry
    reward = tp1 - entry if bullish else entry - tp1
    return risk > 0 and reward > 0


def _exclusion(plan, frame, entry, day: date, model: str) -> str | None:
    """First failing check, in order of precedence."""
    if window_end(day, plan.horizon_key) is None:
        return "unknown_horizon"
    if frame is None or frame.empty:
        return "no_bars"
    if entry is None:
        return "no_cancel_entry" if model == "cancel_fill" else "bad_levels"
    if not _levels_ok(plan.direction == "bullish", entry, plan.stop_loss, plan.tp1):
        return "bad_levels"
    if not split_guard_ok(frame, day, entry):
        return "split_guard"
    return None


def _replay(plan, frame, entry, day: date, require_touch: bool) -> Replay:
    return replay(frame, bullish=plan.direction == "bullish", entry=entry,
                  stop=plan.stop_loss, tp1=plan.tp1, after=day,
                  until=window_end(day, plan.horizon_key), require_touch=require_touch)


def _row(plan, frame, *, reason: str, raw: str | None, day: date, model: str,
         entry, source: str | None, require_touch: bool = True) -> CancelRow:
    excluded = _exclusion(plan, frame, entry, day, model)
    ceiling = _ceiling(plan)
    return CancelRow(
        plan_id=plan.plan_id, ticker=plan.ticker, strategy=plan.strategy,
        horizon_key=plan.horizon_key,
        direction="long" if plan.direction == "bullish" else "short",
        origin=NEXT_SESSION if origin_of(plan) == NEXT_SESSION else "regular",
        reason=reason, raw_reason=raw, cancel_day=day, entry_model=model,
        entry_source=source, entry=entry, stop=plan.stop_loss, tp1=plan.tp1,
        badge=plan.badge, stop_ceiling_pct=ceiling,
        cap_size_pct=_cap_size(ceiling, entry, plan.stop_loss) if reason == "risk_cap" else None,
        replay=None if excluded else _replay(plan, frame, entry, day, require_touch),
        excluded=excluded)


# -- public --------------------------------------------------------------------

def cancel_entry(plan, frame, cancel_day: date) -> tuple[float | None, str | None]:
    """The `risk_cap` crossing price: recorded on the history entry, else
    max(cancel-day open, trigger) long / min(...) short, else (None, None)."""
    plan = _as_plan(plan)
    recorded = (_last_cancel(plan) or {}).get("entry_price")
    if recorded is not None:
        return float(recorded), "recorded"
    if frame is None or frame.empty or plan.trigger_price is None:
        return None, None
    on_day = frame[frame.index.normalize() == pd.Timestamp(cancel_day)]
    if on_day.empty:
        return None, None
    open_ = float(on_day["Open"].iloc[0])
    pick = max if plan.direction == "bullish" else min
    return pick(open_, float(plan.trigger_price)), "estimated"


def _cancelled(plans: list):
    """(plan, raw reason, cancel day) for every CANCELLED, non-manual plan."""
    for plan in map(_as_plan, plans):
        if plan.status != PlanStatus.CANCELLED:
            continue
        last = _last_cancel(plan)
        raw = (last or {}).get("reason")
        if reason_bucket(raw) != MANUAL:
            yield plan, raw, _day_of(last, plan)


def cancel_rows(plans: list, loader: Loader) -> list[CancelRow]:
    """One trigger row per CANCELLED, non-manual plan; +1 cancel_fill row per risk_cap."""
    rows = []
    for plan, raw, day in _cancelled(plans):
        frame = loader(plan.ticker)
        reason = reason_bucket(raw)
        rows.append(_row(plan, frame, reason=reason, raw=raw, day=day, model="trigger",
                         entry=plan.trigger_price, source=None))
        if reason == "risk_cap":
            entry, source = cancel_entry(plan, frame, day)
            rows.append(_row(plan, frame, reason=reason, raw=raw, day=day,
                             model="cancel_fill", entry=entry, source=source))
    return rows


def filled_rows(plans: list, loader: Loader) -> list[CancelRow]:
    """Every filled plan, replayed from its trigger strictly after the first
    ACTIVE transition's trading date, without a touch requirement."""
    rows = []
    for plan in map(_as_plan, plans):
        if not is_filled(plan):
            continue
        day = _day_of(_entries(plan, PlanStatus.ACTIVE)[0], plan)
        rows.append(_row(plan, loader(plan.ticker), reason=FILLED, raw=None, day=day,
                         model="trigger", entry=plan.trigger_price, source=None,
                         require_touch=False))
    return rows


def manual_count(plans: list) -> int:
    """CANCELLED plans whose last cancel is the partner's manual decision."""
    return sum(1 for plan in map(_as_plan, plans)
               if plan.status == PlanStatus.CANCELLED
               and reason_bucket((_last_cancel(plan) or {}).get("reason")) == MANUAL)
