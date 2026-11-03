"""Activity rows for the Live dock (v202): one pure builder per event kind.

Every row is `event_row(...)`: `{"at", "kind", "text", "tone", "ref", "pnl"}`,
with `at` ISO-8601 UTC and `text` the line WITHOUT its P&L figure -- the SPA's
`activityLine` appends "+1.0R ($210) (paper, pre-cost)" from `pnl`.

What the sources can say (spec section 5): `trades.opened_at` is the alert
time, never a fill, so no builder reads it. The only fill is `paper_filled`,
the plan's first `status_history` entry with status ACTIVE, which is the
bot's simulated fill. A TP1 leg without `closed_at` (older plans) yields no
row rather than a guessed time.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from . import iso

_DIRECTION_WORDS = {"bullish": "long", "long": "long", "bearish": "short", "short": "short"}


def direction_word(direction: str | None) -> str:
    return _DIRECTION_WORDS.get(str(direction or "").strip().lower(), "")


def iso_at(value: Any) -> str | None:
    """A datetime or ISO string as ISO-8601 UTC; anything else is None."""
    if isinstance(value, datetime):
        return iso(value)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return iso(datetime.fromisoformat(value.strip()))
    except ValueError:
        return None


def event_row(at: str, kind: str, text: str, tone: str, ref: Any,
              pnl: dict | None = None) -> dict:
    return {"at": at, "kind": kind, "text": text, "tone": tone,
            "ref": None if ref is None else str(ref), "pnl": pnl}


def tone_for(r: float | None) -> str:
    if not r:
        return "neutral"
    return "positive" if r > 0 else "negative"


def _number(value: Any) -> float | None:
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def _price(value: Any) -> str | None:
    number = _number(value)
    return None if number is None else f"{number:.2f}"


def _who(plan: Mapping) -> str:
    parts = (str(plan.get("ticker") or "?"), direction_word(plan.get("direction")))
    return " ".join(part for part in parts if part)


def _alert_text(plan: Mapping) -> str:
    trigger = plan.get("trigger_price")
    price = _price(trigger if trigger is not None else plan.get("entry_price"))
    return f"Alert · {_who(plan)} · entry {price}" if price else f"Alert · {_who(plan)}"


def plan_alerted_rows(plans: list[dict]) -> list[dict]:
    rows = []
    for plan in plans:
        at = iso_at(plan.get("created_at"))
        if at is not None:
            rows.append(event_row(at, "plan_alerted", _alert_text(plan), "info",
                                  plan.get("plan_id")))
    return rows


def _first_fill(plan: Mapping) -> Mapping | None:
    history = plan.get("status_history") or []
    return next((entry for entry in history
                 if isinstance(entry, Mapping) and entry.get("status") == "ACTIVE"), None)


def paper_filled_rows(plans: list[dict]) -> list[dict]:
    rows = []
    for plan in plans:
        fill = _first_fill(plan)
        at = iso_at(fill.get("at")) if fill else None
        if at is None:
            continue
        price = _price(plan.get("entry_price"))
        text = f"Paper fill · {_who(plan)}" + (f" at {price}" if price else "")
        rows.append(event_row(at, "paper_filled", text, "info", plan.get("plan_id")))
    return rows


def _tp1_leg(plan: Mapping) -> Mapping | None:
    legs = plan.get("legs_realized") or []
    return next((leg for leg in legs if isinstance(leg, Mapping)
                 and leg.get("reason") == "tp1" and leg.get("closed_at")), None)


def _leg_amount(plan: Mapping, leg: Mapping, shares: Any) -> float | None:
    """Price move x shares x leg fraction, the same convention as
    `TradeLog._settle_account_balance` uses for `realized_pnl_amount`."""
    try:
        sign = -1.0 if direction_word(plan.get("direction")) == "short" else 1.0
        move = (float(leg["exit_price"]) - float(plan["entry_price"])) * sign
        return round(move * float(shares) * float(leg.get("fraction") or 0.0), 2)
    except (KeyError, TypeError, ValueError):
        return None


def tp1_hit_rows(plans: list[dict], shares_by_plan: Mapping[str, float]) -> list[dict]:
    rows = []
    for plan in plans:
        leg = _tp1_leg(plan)
        at = iso_at(leg.get("closed_at")) if leg else None
        if at is None:
            continue
        r = _number(leg.get("r"))
        shares = shares_by_plan.get(str(plan.get("plan_id")))
        pnl = None if r is None else {"r": r, "amount": _leg_amount(plan, leg, shares)
                                      if shares else None}
        rows.append(event_row(at, "tp1_hit", f"TP1 · {plan.get('ticker') or '?'}",
                              tone_for(r), plan.get("plan_id"), pnl))
    return rows
