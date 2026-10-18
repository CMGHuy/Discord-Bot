"""v171 D5: the one pre-post rebuild entry point.

The lanes pass `rescenario` (re-run the scan's scenario build at the new
price, same frame) and `attach` (their existing plan attach); this module
chooses the price, re-prices the item and stamps the record. Posted plans
never reach it.

NO-LOOKAHEAD: only `current_price` changes. The quote is never spliced into
the forming bar; the frame, ATR and level inputs the scan used are reused by
the caller's `rescenario`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable

from swingbot import config
from swingbot.core.market.session import RTH_OPEN, is_regular_session, is_tape_open, now_et

if TYPE_CHECKING:
    from swingbot.core.marketdata.shared.kinds import QuoteDetail

KIND_TRADE = "trade"
KIND_MID = "mid"
KIND_YF = "yf-1m"
KIND_SCAN = "scan"

_YF_SOURCE = "yfinance-1m"


@dataclass(frozen=True)
class RebuildPrice:
    price: float
    kind: str
    age_s: float | None
    quote_at: str | None
    fetched_at: float | None
    confirmed: bool
    session: str


@dataclass
class RebuildOutcome:
    kept: bool
    reason: str | None
    price: RebuildPrice


def session_label(now: datetime) -> str:
    """"regular" / "pre-market" / "after-hours" / "closed" at `now`."""
    if is_regular_session(now):
        return "regular"
    if not is_tape_open(now):
        return "closed"
    return "pre-market" if now_et(now).time() < RTH_OPEN else "after-hours"


def _age(ts: datetime | None, now: datetime) -> float | None:
    return None if ts is None else max(0.0, (now - ts).total_seconds())


def _fresh(ts: datetime | None, now: datetime, limit: float) -> bool:
    age = _age(ts, now)
    return age is not None and age < limit


def _candidates(quote: QuoteDetail | None) -> tuple:
    """(kind, price, timestamp) in the D5 order; a candidate missing a part is skipped."""
    if quote is None:
        return ()
    is_yf = quote.source == _YF_SOURCE
    traded = None if is_yf else quote.trade_price
    yf = quote.trade_price if is_yf else None
    return ((KIND_TRADE, traded, quote.trade_at),
            (KIND_MID, quote.mid(), quote.quote_at),
            (KIND_YF, yf, quote.trade_at))


def choose_rebuild_price(quote: QuoteDetail | None, scan_price: float, now: datetime, *,
                         max_age_s: float | None = None) -> RebuildPrice:
    """D5 order: live trade, then bid/ask mid, then a yfinance 1-minute bar,
    each strictly younger than the limit; else the scan price, unconfirmed."""
    limit = float(config.REBUILD_PRICE_MAX_AGE_S if max_age_s is None else max_age_s)
    session = session_label(now)
    for kind, price, ts in _candidates(quote):
        if price and price > 0 and _fresh(ts, now, limit):
            return RebuildPrice(float(price), kind, round(_age(ts, now), 1),
                                ts.isoformat(), None, True, session)
    return RebuildPrice(float(scan_price), KIND_SCAN, None, None, None, False, session)


def stamp_quote(plan: Any, price: RebuildPrice, age_at_persist_s: float | None = None) -> None:
    """Write the five D2 quote fields onto a TradePlanV2 or a legacy Scenario."""
    setattr(plan, "quote_at", price.quote_at)
    setattr(plan, "quote_kind", price.kind)
    setattr(plan, "quote_age_s", age_at_persist_s)
    setattr(plan, "quote_session", price.session)
    setattr(plan, "price_confirmed", price.confirmed)


def quote_record(price: RebuildPrice, age_at_persist_s: float | None) -> dict:
    """The trade record's `quote` dict (V171-17)."""
    return {"at": price.quote_at, "kind": price.kind, "age_s": age_at_persist_s,
            "session": price.session, "confirmed": price.confirmed}


def _reprice(item: Any, scenario: Any, price: float) -> None:
    item.plan = scenario
    item.plan_v2 = None
    item.plan_v2_rejected = None
    item.plan_v2_rejected_plan = None
    item.plan_v2_rejected_margin = None
    item.result.close = price
    item.result.scenario = scenario


def _rejection(item: Any) -> str | None:
    """In `on` mode a rebuild never posts un-gated legacy numbers."""
    if config.PLAN_ENGINE_V2 != "on":
        return None
    if item.plan_v2_rejected:
        return item.plan_v2_rejected
    return "no_plan" if item.plan_v2 is None else None


def _display_target(item: Any) -> Any:
    return item.plan_v2 if item.plan_v2 is not None else item.plan


def rebuild_before_post(item: Any, price: RebuildPrice, *,
                        rescenario: Callable[[float], Any | None],
                        attach: Callable[[Any], None]) -> RebuildOutcome:
    """Rebuild `item`'s plan at `price` and re-run its gates, or drop it.

    An unconfirmed price leaves the plan exactly as the scan built it and
    only stamps it. A dropped plan consumes no cooldown and no dedup (the
    caller simply does not post it).
    """
    if not price.confirmed:
        stamp_quote(_display_target(item), price)
        return RebuildOutcome(True, None, price)
    scenario = rescenario(price.price)
    if scenario is None:
        return RebuildOutcome(False, "rebuild:no_scenario", price)
    _reprice(item, scenario, price.price)
    attach(scenario)
    reason = _rejection(item)
    if reason is not None:
        return RebuildOutcome(False, f"rebuild:{reason}", price)
    stamp_quote(_display_target(item), price)
    return RebuildOutcome(True, None, price)
