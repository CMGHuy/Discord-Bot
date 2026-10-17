"""v170 §3 / A4-A6: the 💵 P&L now button's ephemeral reply.

render_reply is pure (plan, paper record, quote and clock in; text out), so
every plan status is unit-testable. reply_for wires the three seams -- the
plan store, the paper-trade record (TradeLog.trade_for_plan, any status) and
the price (scan_run.quote_trade, the single-trade body `!pnl` runs, so the
button and `!pnl` cannot disagree on the open figure) -- and never raises:
a press always gets an answer.

Dollars: the open part and the banked legs are the paper record's own
arithmetic (record shares, not the whole shares a message prints, v170 A3);
with no linked record no dollar figure prints at all. Every total is gross
on the paper account (tokens.COST_BASIS)."""
import datetime as dt
import logging

from swingbot import config
from swingbot.core.market.session import is_regular_session, now_et
from swingbot.core.planning.plan_types import PlanStatus
from swingbot.core.presentation import tokens
from swingbot.core.presentation.instructions import money_from, pnl_line, signed_r, total_r

log = logging.getLogger(__name__)

GONE = "This plan no longer exists."
UNAVAILABLE = "price unavailable"
NOT_FILLED = "not filled yet"
NEVER_FILLED = "never filled"
FAILED = "Could not compute P&L just now; please try again."

_WORD = {"bullish": "long", "bearish": "short"}
#: statuses whose reply needs a live price (closed/cancelled read the record only).
_LIVE = frozenset({PlanStatus.PENDING, PlanStatus.ACTIVE, PlanStatus.PARTIAL})


def _sign(direction: str) -> int:
    return 1 if direction == "bullish" else -1


def _clean(r: float) -> float:
    """Float noise must not print '−0.0R'."""
    return 0.0 if round(r, 1) == 0 else round(r, 4) + 0.0


def _head(plan) -> str:
    return f"{plan.ticker} {_WORD.get(plan.direction, plan.direction)} · {plan.status}"


def _as_of(quote, clock: dt.datetime, market_open: bool) -> str:
    """'last <price> · as of HH:MM ET' plus the daily-close date and
    'market closed' when they apply (A6: no quote carries a timestamp, so the
    fetch moment is the as-of); UNAVAILABLE when there is no price."""
    if quote is None or quote.price is None:
        return UNAVAILABLE
    parts = [f"last {tokens.fmt_price(quote.price)}", f"as of {now_et(clock):%H:%M} ET"]
    if quote.daily_close is not None:
        parts.append(f"daily close {quote.daily_close.isoformat()}")
    if not market_open:
        parts.append("market closed")
    return " · ".join(parts)


def _record_shares(trade: dict | None) -> float | None:
    shares = (trade or {}).get("shares")
    return float(shares) if shares else None


def _entry(plan, trade: dict | None) -> float:
    """The fill (the basis total_r and the feed measure R from); the
    record's entry, then the trigger, for a plan not filled yet."""
    if plan.entry_price is not None:
        return plan.entry_price
    if trade and trade.get("entry") is not None:
        return float(trade["entry"])
    return plan.trigger_price


def _pct(pnl) -> str:
    """The `!pnl` percentage; a sub-0.05% move prints '0.0%', never a signed zero."""
    if pnl is None:
        return tokens.fmt_pct(None)
    return tokens.fmt_pct(0.0 if round(pnl.pct_change, 1) == 0 else pnl.pct_change)


def _figures(r: float, usd: float, shares: float | None) -> str:
    """'<$> · <R>' -- the $ only when a record with shares backs it."""
    if shares is None:
        return signed_r(r)
    usd = 0.0 if round(usd, 2) == 0 else usd
    return f"{tokens.fmt_money(usd, config.CURRENCY_SYMBOL)} · {signed_r(r)}"


def _banked(plan, entry: float, shares: float | None) -> tuple[float, float]:
    """(R, $) of the legs already realised: Σ fraction × r, and the record's
    shares × fraction × (exit − entry), signed by direction."""
    sign = _sign(plan.direction)
    legs = plan.legs_realized or []
    r = sum(leg["fraction"] * leg["r"] for leg in legs)
    usd = sum((shares or 0.0) * leg["fraction"] * (leg["exit_price"] - entry) * sign
              for leg in legs)
    return r, usd


def _open_part(plan, entry: float, shares: float | None, price: float) -> tuple[float, float, float]:
    """(open fraction, its R contribution, its $ contribution) at ``price``."""
    fraction = max(0.0, 1.0 - sum(leg["fraction"] for leg in plan.legs_realized or []))
    risk = abs(entry - plan.stop_loss)
    move = (price - entry) * _sign(plan.direction)
    r = fraction * move / risk if risk else 0.0
    return fraction, r, (shares or 0.0) * fraction * move


def _open_reply(plan, trade, quote, pnl, clock, market_open) -> list[str]:
    shares = _record_shares(trade)
    entry = _entry(plan, trade)
    banked_r, banked_usd = _banked(plan, entry, shares)
    banked = [f"banked: {_figures(_clean(banked_r), banked_usd, shares)} {tokens.COST_BASIS}"] if plan.legs_realized else []
    if quote is None or quote.price is None:
        return [UNAVAILABLE, *banked]
    fraction, open_r, open_usd = _open_part(plan, entry, shares, quote.price)
    pct = _pct(pnl)
    total = _figures(_clean(open_r + banked_r), open_usd + banked_usd, shares)
    return [_as_of(quote, clock, market_open),
            f"open {fraction:.0%}: {pct} · {_figures(_clean(open_r), open_usd, shares)}",
            *banked,
            f"{tokens.FEED_SYMBOLS['pnl']} total {total} {tokens.COST_BASIS}"]


def _pending_reply(plan, trade, quote, pnl, clock, market_open) -> list[str]:
    return [_as_of(quote, clock, market_open),
            f"{tokens.FEED_SYMBOLS['entry']} trigger {tokens.fmt_price(plan.trigger_price)} · {NOT_FILLED}"]


def _closed_reply(plan, trade, quote, pnl, clock, market_open) -> list[str]:
    """The final result from the record: the settled realized_pnl_amount
    (R only until it is settled), never a live price."""
    record = trade or {}
    money = money_from(record.get("shares"), config.CURRENCY_SYMBOL,
                       realized_amount=record.get("realized_pnl_amount"))
    return [pnl_line(_clean(total_r(plan, record.get("exit_price"))), money)]


def _cancelled_reply(plan, trade, quote, pnl, clock, market_open) -> list[str]:
    return [NEVER_FILLED]


_REPLIES = {
    PlanStatus.PENDING: _pending_reply,
    PlanStatus.ACTIVE: _open_reply,
    PlanStatus.PARTIAL: _open_reply,
    PlanStatus.CLOSED: _closed_reply,
    PlanStatus.CANCELLED: _cancelled_reply,
}


def render_reply(plan, trade: dict | None, quote, pnl, *, clock: dt.datetime,
                 market_open: bool) -> str:
    """The ephemeral reply text for ``plan`` at its status now (A4)."""
    body = _REPLIES.get(plan.status, lambda *_: [])(plan, trade, quote, pnl, clock, market_open)
    return "\n".join([_head(plan), *body])


def _load_plan(plan_id: str):
    from swingbot.core.planning.plan_store import PlanStore
    return PlanStore().get(plan_id)


def _linked_trade(plan_id: str) -> dict | None:
    """The plan's paper record in any status, or None. Never raises."""
    try:
        from swingbot.core.tracking.performance import TradeLog
        return TradeLog().trade_for_plan(plan_id)
    except Exception:
        log.warning("P&L now: trade lookup failed for plan %s", plan_id, exc_info=True)
        return None


def _quote_input(plan, trade: dict | None) -> dict:
    """What quote_trade prices: the record itself (the `!pnl` row), or the
    plan's own levels when no record exists."""
    if trade:
        return trade
    return {"ticker": plan.ticker, "direction": plan.direction, "entry": _entry(plan, None),
            "stop_loss": plan.stop_loss, "take_profit": plan.tp1}


def _quote(plan, trade: dict | None):
    """(TradeQuote, UnrealizedPnL | None), or (None, None) when the fetch
    failed -- the reply then says UNAVAILABLE, never raises."""
    try:
        from swingbot.core.scanning import scan_run
        return scan_run.quote_trade(_quote_input(plan, trade))
    except Exception:
        log.warning("P&L now: price fetch failed for %s", plan.ticker, exc_info=True)
        return None, None


def reply_for(plan_id: str, *, now: dt.datetime | None = None) -> str:
    """The button's whole answer. Never raises: any failure is logged and
    answered with FAILED."""
    try:
        plan = _load_plan(plan_id)
        if plan is None:
            return GONE
        trade = _linked_trade(plan_id)
        quote, pnl = _quote(plan, trade) if plan.status in _LIVE else (None, None)
        clock = now or dt.datetime.now(dt.timezone.utc)
        return render_reply(plan, trade, quote, pnl, clock=clock,
                            market_open=is_regular_session(clock))
    except Exception:
        log.warning("P&L now: could not answer for plan %s", plan_id, exc_info=True)
        return FAILED
