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

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from swingbot.core.infra.swallowed import swallowed

from . import iso

log = logging.getLogger(__name__)

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


#: Last leg's reason -> the outcome word on a closed-trade line.
_OUTCOMES = {
    "tp1_runner_tp2": "TP2", "tp1_runner_be": "runner at floor",
    "tp1_runner_trail": "trailed", "tp1_runner_progress_stall": "runner stalled",
    "time_exit": "time exit", "stall_exit": "stall exit", "scratch": "scratch",
    "loss": "stop", "tp1": "TP1",
}


def _outcome(trade: Mapping) -> str | None:
    legs = trade.get("legs") or []
    last = legs[-1] if legs and isinstance(legs[-1], Mapping) else {}
    label = _OUTCOMES.get(str(last.get("reason") or ""))
    return label or trade.get("close_reason") or trade.get("status")


def trade_closed_rows(trades: list[dict]) -> list[dict]:
    from swingbot.core.tracking.performance import closed_r_multiple
    rows = []
    for trade in trades:
        at = iso_at(trade.get("closed_at"))
        if at is None or trade.get("status") == "open":
            continue
        r = closed_r_multiple(trade)
        pnl = None if r is None else {"r": r, "amount": _number(trade.get("realized_pnl_amount"))}
        outcome = _outcome(trade)
        text = f"{trade.get('ticker') or '?'} closed" + (f" · {outcome}" if outcome else "")
        rows.append(event_row(at, "trade_closed", text, tone_for(r), trade.get("id"), pnl))
    return rows


def killswitch_rows(state: Mapping) -> list[dict]:
    """The latest transition only, worded by `on`: the table holds one row and
    `release()` overwrites its time, so no history and no engagement claimed
    at a release time."""
    at = iso_at(state.get("at")) if isinstance(state, Mapping) else None
    if at is None:
        return []
    engaged = bool(state.get("on"))
    text = "Killswitch engaged" if engaged else "Killswitch released"
    return [event_row(at, "killswitch", text, "warning" if engaged else "neutral", None)]


@dataclass(frozen=True)
class EventKind:
    kind: str
    source: str
    build: Callable[[dict], list[dict]]


EVENT_KINDS: tuple[EventKind, ...] = (
    EventKind("plan_alerted", "plans", lambda s: plan_alerted_rows(s["plans"])),
    EventKind("paper_filled", "plans", lambda s: paper_filled_rows(s["plans"])),
    EventKind("tp1_hit", "plans", lambda s: tp1_hit_rows(s["plans"], s.get("shares") or {})),
    EventKind("trade_closed", "trades", lambda s: trade_closed_rows(s["trades"])),
    EventKind("killswitch", "killswitch", lambda s: killswitch_rows(s["killswitch"])),
)

#: Most recently updated plans read per request. A fill or TP1 rewrites its
#: plan's row, so a recent event's plan is near the top of this window.
PLAN_WINDOW = 200
#: Closed trades read per request: no more than `live.MAX_LIMIT` can show.
TRADE_WINDOW = 50


def _load_plans() -> list[dict]:
    from swingbot.core.db.repositories.plans import plans_repo
    from swingbot.core.db.schema import plans
    return plans_repo().list_all(order_by=plans.c.updated_at.desc(), limit=PLAN_WINDOW)


def _load_trades() -> list[dict]:
    from swingbot.core.db.repositories.trades import trades_repo
    from swingbot.core.tracking.performance import _json_record
    return [_json_record(row) for row in trades_repo().closed_trades(limit=TRADE_WINDOW)]


def _load_killswitch() -> dict:
    from swingbot.core.db.repositories.killswitch import killswitch_repo
    return killswitch_repo().state()


def _load_shares() -> dict[str, float]:
    """plan_id -> shares, for TP1 amounts; open and recently closed trades."""
    from swingbot.core.db.repositories.trades import trades_repo
    repo = trades_repo()
    rows = repo.open_trades() + repo.closed_trades(limit=PLAN_WINDOW)
    return {str(row["plan_id"]): row["shares"] for row in rows
            if row.get("plan_id") and row.get("shares")}


SOURCE_LOADERS: dict[str, Callable[[], Any]] = {
    "plans": _load_plans, "trades": _load_trades,
    "killswitch": _load_killswitch, "shares": _load_shares,
}


def _load_sources(loaders: Mapping[str, Callable[[], Any]]) -> dict:
    sources = {}
    for name, load in loaders.items():
        try:
            sources[name] = load()
        except Exception as exc:
            swallowed(log, "ops.live.load_sources", exc, "live events source %s failed", name,
                      level=logging.WARNING)
    return sources


def _build(kind: EventKind, sources: dict) -> list[dict] | None:
    """The kind's rows, or None when its source failed or its data was bad."""
    if kind.source not in sources:
        return None
    try:
        return kind.build(sources)
    except Exception as exc:
        swallowed(log, "ops.live.build", exc, "live events kind %s failed", kind.kind, level=logging.WARNING)
        return None


def _meta(missing: list[str], now: datetime) -> dict:
    if not missing:
        state = "ok"
    elif len(missing) == len(EVENT_KINDS):
        state = "unavailable"
    else:
        state = "partial"
    return {"availability": state, "as_of": iso(now), "missing": missing}


def collect_events(limit: int, *, loaders: Mapping[str, Callable[[], Any]] | None = None,
                   now: datetime | None = None) -> tuple[list[dict], dict]:
    """Every kind's rows merged newest first and cut to `limit`, plus the meta
    naming each kind whose source failed, so a gap never reads as a quiet day."""
    now = now or datetime.now(timezone.utc)
    sources = _load_sources(SOURCE_LOADERS if loaders is None else loaders)
    rows, missing = [], []
    for kind in EVENT_KINDS:
        built = _build(kind, sources)
        if built is None:
            missing.append(kind.kind)
        else:
            rows.extend(built)
    rows.sort(key=lambda row: datetime.fromisoformat(row["at"]), reverse=True)
    return rows[:limit], _meta(missing, now)
