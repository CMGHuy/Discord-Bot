"""v151: the Why panel's keys on GET /api/v1/trades/<id> `detail`.

Kept out of api_v1/trades.py so `_plan_detail` / `_legacy_detail` gain one
`**` merge each and no branch. Everything here is read-only and API-only:
stored plans and trades are never rewritten (schema-evolution.md -- no
read-time upcasting). v146's `confidence_points` / `confidence_unevaluated`
are passed through, never computed; a record written before v146 has
neither and gets None / [].
"""
from __future__ import annotations

import datetime as dt

from swingbot import config
from swingbot.core.market.session import US_MARKET_TZ, nyse_calendar
from swingbot.core.market.strategy_types import HORIZONS
from swingbot.core.planning.time_exit import fill_day_from_history
from swingbot.core.presentation.why_view import GateThresholds, calendar_rows, gate_rows

#: Only these entry_context keys go on the wire, not the full feature dict.
WIRE_CONTEXT_KEYS = ("regime2_state", "rs_pctile", "sector_pctile", "rs_combined",
                     "htf_aligned", "gap_p90_pct", "gap_fragile")


def gate_thresholds() -> GateThresholds:
    """Today's gate configuration -- the UI labels margins 'vs today's thresholds'."""
    return GateThresholds(
        rs_gate=bool(config.RS_GATE),
        rs_laggard_pct=float(config.RS_LAGGARD_PERCENTILE),
        rs_leader_pct=float(config.RS_LEADER_PERCENTILE),
        regime_gates=bool(config.REGIME_GATES_ENABLED),
    )


def _today() -> dt.date:
    """The ET session date now. Tests monkeypatch this."""
    return dt.datetime.now(US_MARKET_TZ).date()


def _session_day(stamp) -> dt.date | None:
    """An ISO date or datetime string as its ET calendar date; None on garbage."""
    if not stamp:
        return None
    try:
        moment = dt.datetime.fromisoformat(str(stamp))
    except ValueError:
        return None
    if moment.tzinfo is None:
        return moment.date()
    return moment.astimezone(US_MARKET_TZ).date()


def _iso(day: dt.date | None) -> str | None:
    return day.isoformat() if day else None


def _as_dict(value) -> dict:
    return dict(value) if isinstance(value, dict) else {}


def _wire_context(ctx: dict) -> dict:
    return {key: ctx[key] for key in WIRE_CONTEXT_KEYS if key in ctx}


def _first_set(*values):
    """The first value that is not None -- an empty {} or [] is a real answer."""
    return next((v for v in values if v is not None), None)


def _sessions_since(created: dt.date | None, today: dt.date) -> int | None:
    return None if created is None else nyse_calendar().sessions_between(created, today)


def _expires_on(plan: dict, created: dt.date | None) -> dt.date | None:
    """Last live bar of a PENDING plan: `pending_expired` fires past expiry_bars."""
    bars = plan.get("expiry_bars")
    if plan.get("status") != "PENDING" or created is None or not isinstance(bars, int):
        return None
    return nyse_calendar().session_after(created, bars)


def _time_exit_on(plan: dict) -> dt.date | None:
    """The fill session is session 1, so the cap-th session is cap - 1 after it."""
    cap = plan.get("hold_cap_bars")
    if not isinstance(cap, int) or cap < 1:
        return None
    try:
        fill = fill_day_from_history(plan.get("status_history") or [])
    except ValueError:
        return None
    return nyse_calendar().session_after(fill, cap - 1)


def _window_end(plan: dict, created: dt.date, expires, time_exit) -> dt.date | None:
    if time_exit is not None:
        return time_exit
    if expires is not None:
        return expires
    hold = (HORIZONS.get(plan.get("horizon_key")) or {}).get("max_holding_days")
    return created + dt.timedelta(days=hold) if hold else None


def _calendar(plan: dict, created: dt.date | None, expires, time_exit) -> list[dict]:
    if created is None:
        return []
    end = _window_end(plan, created, expires, time_exit)
    return calendar_rows(created, end) if end is not None else []


def plan_why_fields(plan: dict, trade: dict | None, today: dt.date | None = None) -> dict:
    """The new detail keys for a plan-backed row. The plan's frozen copy of
    entry_context / risk_features wins; the trade's logged copy is the
    fallback for an older plan."""
    t = trade or {}
    today = today or _today()
    created = _session_day(plan.get("created_at"))
    expires = _expires_on(plan, created)
    time_exit = _time_exit_on(plan)
    ctx = _as_dict(plan.get("entry_context") or t.get("entry_context"))
    risk = _as_dict(plan.get("risk_features") or t.get("risk_features"))
    cohort = plan.get("cohort_label")
    return {
        "entry_context": _wire_context(ctx),
        "risk_features": risk,
        "cohort_label": cohort,
        "confidence_points": _first_set(t.get("confidence_points"), plan.get("confidence_points")),
        "confidence_unevaluated": _first_set(t.get("confidence_unevaluated"),
                                             plan.get("confidence_unevaluated")) or [],
        "gates": gate_rows(plan.get("direction"), ctx, risk, cohort, gate_thresholds()),
        "sessions_since_created": _sessions_since(created, today),
        "expires_on": _iso(expires),
        "time_exit_on": _iso(time_exit),
        "calendar": _calendar(plan, created, expires, time_exit),
        "hold_cap_bars": plan.get("hold_cap_bars"),
        "acceptance_level": plan.get("acceptance_level"),
    }


def legacy_why_fields(trade: dict, today: dt.date | None = None) -> dict:
    """Same keys for a legacy trade; plan-only ones are None / []."""
    today = today or _today()
    ctx = _as_dict(trade.get("entry_context"))
    risk = _as_dict(trade.get("risk_features"))
    return {
        "entry_context": _wire_context(ctx),
        "risk_features": risk,
        "cohort_label": None,
        "confidence_points": trade.get("confidence_points"),
        "confidence_unevaluated": trade.get("confidence_unevaluated") or [],
        "gates": gate_rows(trade.get("direction"), ctx, risk, None, gate_thresholds()),
        "sessions_since_created": _sessions_since(_session_day(trade.get("opened_at")), today),
        "expires_on": None,
        "time_exit_on": None,
        "calendar": [],
        "hold_cap_bars": None,
        "acceptance_level": None,
    }
