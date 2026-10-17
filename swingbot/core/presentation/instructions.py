"""v81: the execution feed's broker instructions, as pure data.

Every message the simple-alerts channel sends -- an alert's order ticket and
each plan lifecycle event -- is projected here into the verb and the order
lines a reader places at a broker. No discord import, no I/O, no clock:
money (v170: a frozen Money), block annotations and every live stop arrive
as arguments or in the event's detail, which plan_manager stamps. Every
glyph comes from tokens.FEED_SYMBOLS; none is written here as a literal.
core/scanning/execution_embeds.py is the only thing that turns an
Instruction into a Discord embed.
"""
from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass

from swingbot.core.planning.exit_sim import runner_floor
from swingbot.core.planning.plan_types import breakeven_trigger
from swingbot.core.presentation import short_notice, tokens
from swingbot.core.presentation.plan_view import plan_view

PLACE = "PLACE"
DO_NOT_PLACE = "DO NOT PLACE"
FILLED = "FILLED"
MOVE_STOP = "MOVE STOP"
CANCEL = "CANCEL"
EXITED = "EXITED"
CLOSE_AT_MARKET = "CLOSE AT MARKET"

#: plan_manager close reasons, in the words a reader recognises.
_EXIT_WORDS = {
    "loss": "stop",
    "scratch": "break-even",
    "win": "target",
    "tp1_runner_be": "runner floor",
    "tp1_runner_trail": "trail",
    "tp1_runner_tp2": "TP2",
    "time_exit": "ten-session time exit",
    "tp1_runner_progress_stall": "higher high failed on cooling range and volume",
}

#: Closes the bot books with no resting broker order behind them (v123):
#: the reader must act at market, exactly like an extended-hours exit.
_MARKET_EXIT_REASONS = frozenset({"tp1_runner_progress_stall"})


@dataclass(frozen=True)
class Instruction:
    """One execution-feed message.

    ``headline`` is the bold action line; ``warnings`` render above it and
    ``lines`` below. ``tone`` picks the accent: ``"level"`` (the confidence
    ramp, order tickets only), ``"good"``, ``"bad"``, ``"neutral"`` or
    ``"inert"`."""

    verb: str
    ticker: str
    direction: str
    headline: str
    lines: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    tone: str = "neutral"
    level: int | None = None
    plan_id: str | None = None


def _sides(direction: str) -> dict[str, str]:
    if direction == "bullish":
        return {"entry_stop": "BUY STOP", "entry_market": "BUY AT MARKET",
                "stop": "SELL STOP", "limit": "SELL LIMIT", "exit": "SELL AT MARKET"}
    return {"entry_stop": "SELL STOP", "entry_market": "SELL SHORT AT MARKET",
            "stop": "BUY STOP", "limit": "BUY LIMIT", "exit": "BUY TO COVER AT MARKET"}


def _price(x: float | None) -> str:
    return tokens.fmt_price(x)


def signed_r(x: float) -> str:
    """``+0.8R`` / ``−1.1R`` / ``0.0R`` -- the feed signs every non-zero R."""
    text = tokens.fmt_r(x)
    return text if x < 0 or text == "0.0R" else f"+{text}"


_S = tokens.FEED_SYMBOLS


@dataclass(frozen=True)
class Money:
    """The dollar inputs of one feed message (v170 §1, A3), as data.

    ``shares`` is the whole-share count the message prints (the floor of the
    position); ``record_shares`` the paper record's unrounded count, used
    only for realised figures (the record's own arithmetic).
    ``realized_amount`` is the record's settled ``realized_pnl_amount``.
    ``record_shares is None`` means no paper record backs the message: it
    still prints share counts but no dollar figure."""

    currency: str
    shares: int | None
    realized_amount: float | None = None
    record_shares: float | None = None


def money_from(shares: float | None, currency: str, *,
               realized_amount: float | None = None, priced: bool = True) -> Money:
    """The one constructor callers use. ``priced=False`` keeps the share
    count (a lifecycle message with no linked record sizes from today's
    snapshot, as before v170) and drops every dollar figure."""
    whole = math.floor(shares) if shares else 0
    return Money(currency=currency, shares=whole or None,
                 realized_amount=realized_amount if priced else None,
                 record_shares=float(shares) if priced and shares else None)


def _sign(direction: str) -> int:
    return 1 if direction == "bullish" else -1


def _printed(x: float) -> float:
    """``x`` as the message prints it, so printed shares × printed move is
    exactly the printed dollars (v170 §1)."""
    return float(_price(x))


def _r_at(plan, entry: float | None, level: float | None) -> float | None:
    """R of ``level`` measured from ``entry`` against the plan's stop, signed
    by direction; None when there is no entry, level or risk."""
    if entry is None or level is None:
        return None
    risk = abs(entry - plan.stop_loss)
    if not risk:
        return None
    return (level - entry) * _sign(plan.direction) / risk


def _join(*parts: str) -> str:
    """Join the non-empty parts with the feed's ' · ' separator."""
    return " · ".join(part for part in parts if part)


def _priced(money: Money | None) -> bool:
    """True when the message may print dollars: shares known and record-backed."""
    return money is not None and money.shares is not None and money.record_shares is not None


def _toward(direction: str) -> str:
    """The comparison glyph for price moving the trade's way."""
    return _S["at_or_above"] if direction == "bullish" else _S["at_or_below"]


def _against(direction: str) -> str:
    """The comparison glyph for price moving against the trade."""
    return _S["at_or_below"] if direction == "bullish" else _S["at_or_above"]


def _dollars(amount: float, money: Money) -> str:
    return tokens.fmt_money(amount, money.currency)


def _projected(plan, entry, level, shares: int | None, money: Money | None) -> str:
    """'If hit' dollars: printed shares × printed move, signed by direction;
    '' when the message is unpriced."""
    if not _priced(money) or shares is None or entry is None or level is None:
        return ""
    return _dollars(shares * (_printed(level) - _printed(entry)) * _sign(plan.direction), money)


def _if_hit(plan, entry, level, shares: int | None, money: Money | None) -> str:
    """'if hit <$> · <R>' for one ticket level; whichever figures exist."""
    r = _r_at(plan, entry, level)
    figures = _join(_projected(plan, entry, level, shares, money),
                    signed_r(r) if r is not None else "")
    return f"if hit {figures}" if figures else ""


def approx_last_trigger_session(created_at: str, expiry_bars: int) -> dt.date:
    """The last session a pending plan can still trigger in: ``created_at``
    plus ``expiry_bars`` weekdays (lifecycle.pending_expired is strictly
    greater-than; plan_manager._bars_since counts rows dated after
    created_at). Approximate by construction -- there is no holiday calendar
    in this repo, and every holiday moves the real date one session later."""
    day = dt.date.fromisoformat(created_at[:10])
    added = 0
    while added < expiry_bars:
        day += dt.timedelta(days=1)
        if day.weekday() < 5:
            added += 1
    return day


def block_warnings(*, heat: dict | None, cluster: dict | None,
                   kill: dict | None) -> tuple[str, ...]:
    """Heat, cluster and kill-switch blocks only label an alert: scan_run sets
    them after the paper trade is logged at full size, so the ticket still
    says PLACE and names each block above the orders (v81 D1)."""
    warnings = []
    if heat is not None:
        warnings.append(f"⚠ over portfolio heat cap — open {heat['open_heat']}% / "
                        f"cap {heat['cap']}%; the bot tracks this at full size")
    if cluster is not None:
        names = ", ".join(cluster.get("cluster", [])) or tokens.ABSENT
        warnings.append(f"⚠ over correlated-cluster cap — {names} at "
                        f"{cluster['correlated_heat']}% / cap {cluster['cap']}%; "
                        "the bot tracks this at full size")
    if kill is not None:
        warnings.append(f"⚠ kill switch on ({kill.get('reason')}) — "
                        "the bot tracks this at full size")
    return tuple(warnings)


def _leg_sizes(plan, money: Money | None) -> tuple:
    """(size, TP1 qty, runner qty, TP1 shares, runner shares) for the ticket;
    percentages and None share counts when unsized."""
    whole = money.shares if money is not None else None
    if whole is None:
        return ("size n/a", f"{plan.tp1_fraction:.0%}", f"{1 - plan.tp1_fraction:.0%}",
                None, None)
    tp1_shares = math.floor(whole * plan.tp1_fraction)
    runner = whole - tp1_shares
    return f"{whole:,} sh", f"{tp1_shares:,} sh", f"{runner:,} sh", tp1_shares, runner


def _runner_line(plan, entry, side: dict, qty: str, shares: int | None,
                 money: Money | None) -> str:
    """The runner's TP2 order (with its 'if hit' figures) and its trail."""
    trail = f"{_S['trail']} trail {plan.trail_atr_mult:g}×ATR, stop moves pinged here"
    target = ""
    if plan.tp2 is not None:
        target = _join(f"{_S['tp2']} {side['limit']} {_price(plan.tp2)}",
                       _if_hit(plan, entry, plan.tp2, shares, money))
    return f"{_S['runner']} {qty}: {_join(target, trail)}"


def _cancel_line(plan) -> str:
    """A stop entry's two cancel conditions, each saying CANCEL (v170 panel)."""
    sessions = plan_view(plan, bars_since_created=0).bars_to_expiry
    if sessions is None:
        sessions = plan.expiry_bars
    last = approx_last_trigger_session(plan.created_at, plan.expiry_bars)
    return _join(f"{_S['expiry']} CANCEL after {last:%a %d %b} ({sessions} sessions)",
                 f"{_S['invalid']} CANCEL if {_against(plan.direction)} "
                 f"{_price(plan.stop_loss)} first")


def ticket_for(plan, *, logged: bool, not_logged_reason: str | None,
               money: Money | None = None, warnings: tuple[str, ...] = (),
               level: int | None = None) -> Instruction:
    """The order ticket for a new alert (v81 D1, D2, D4). ``logged`` is
    scan_run's own paper-trade decision; the verb mirrors it. v170: every
    order line keeps its broker verb and carries its 'if hit' R and, when
    ``money`` is priced, its dollars; the stop line's loss sits beside the
    gains."""
    side = _sides(plan.direction)
    entry = plan.entry_price if plan.entry_price is not None else plan.trigger_price
    common = dict(ticker=plan.ticker, direction=plan.direction,
                  plan_id=plan.plan_id, level=level)
    if not logged:
        reason = not_logged_reason or "the bot is not tracking this setup"
        return Instruction(
            verb=DO_NOT_PLACE, headline=f"{DO_NOT_PLACE} — {reason}",
            lines=(f"levels: entry {_price(entry)} · stop {_price(plan.stop_loss)} · "
                   f"TP1 {_price(plan.tp1)}",),
            tone="inert", **common)

    size, tp1_qty, runner_qty, tp1_shares, runner_shares = _leg_sizes(plan, money)
    whole = money.shares if money is not None else None
    if plan.entry_type == "stop_entry":
        order = f"{side['entry_stop']} {_price(plan.trigger_price)}"
    else:
        order = f"{side['entry_market']} ~{_price(plan.trigger_price)}"
    lines = [
        _join(f"{_S['stop']} {side['stop']} {_price(plan.stop_loss)}",
              _if_hit(plan, entry, plan.stop_loss, whole, money)),
        _join(f"{_S['tp1']} {side['limit']} {_price(plan.tp1)}", tp1_qty,
              _if_hit(plan, entry, plan.tp1, tp1_shares, money)),
        _runner_line(plan, entry, side, runner_qty, runner_shares, money),
        f"{_S['breakeven']} stop → entry at {_toward(plan.direction)} "
        f"{_price(breakeven_trigger(plan, entry))}",
    ]
    if plan.entry_type == "stop_entry":
        lines.append(_cancel_line(plan))
    return Instruction(verb=PLACE, headline=f"{_S['entry']} {order} · {size}",
                       lines=tuple(lines), warnings=tuple(warnings), tone="level", **common)


def total_r(plan, exit_price: float | None) -> float:
    """Fraction-weighted R over ``legs_realized``, or the single position's R
    for a close that realized no leg: a pre-TP1 stop or scratch and a v70
    extended-hours exit append nothing to the plan (plan_manager._on_event
    synthesizes that leg for the trade log only)."""
    if plan.legs_realized:
        return sum(leg["fraction"] * leg["r"] for leg in plan.legs_realized)
    if plan.entry_price is None or exit_price is None:
        return 0.0
    risk = abs(plan.entry_price - plan.stop_loss)
    if not risk:
        return 0.0
    sign = 1 if plan.direction == "bullish" else -1
    return (exit_price - plan.entry_price) * sign / risk


def _stop_kind(plan, new_stop: float) -> str:
    if plan.status != "PARTIAL":
        return "break-even"
    floor = runner_floor(plan.entry_price, plan.tp1)
    return "runner floor" if math.isclose(new_stop, floor, abs_tol=1e-6) else "trail"


#: _stop_kind's word -> its FEED_SYMBOLS key.
_STOP_KIND_KEYS = {"break-even": "breakeven", "runner floor": "runner", "trail": "trail"}


def _leg_qty(money: Money | None, fraction: float) -> str:
    """Printed shares of one leg (floor of the printed position × fraction),
    or the fraction as a percentage when unsized."""
    whole = money.shares if money is not None else None
    return f"{math.floor(whole * fraction):,} sh" if whole is not None else f"{fraction:.0%}"


def _leg_dollars(plan, entry: float, leg: dict, money: Money) -> float:
    """A realised leg in record arithmetic (v170 A3): the paper record's own
    shares × fraction × (exit − entry), signed -- the figure the trade log
    banks, so it can differ from printed shares × move by under one share."""
    return (money.record_shares * leg["fraction"] * (leg["exit_price"] - entry)
            * _sign(plan.direction))


def _open_whole(money: Money, legs: list) -> int:
    """Printed shares still open: the printed position less each banked leg's printed count."""
    return max(0, money.shares - sum(math.floor(money.shares * leg["fraction"]) for leg in legs))


def stop_projection(plan, new_stop: float, money: Money | None) -> tuple[float | None, float]:
    """What the whole position totals if ``new_stop`` fills (v170 §2):
    ($ or None when unpriced, total R). Banked legs plus the open part
    stopped at ``new_stop``; the open part is printed shares × printed move,
    the banked legs are record arithmetic (the TP1 message's own figure).
    A projection -- a gap can fill worse -- and worded as one."""
    entry = plan.entry_price if plan.entry_price is not None else plan.trigger_price
    legs = list(plan.legs_realized or [])
    open_fraction = max(0.0, 1.0 - sum(leg["fraction"] for leg in legs))
    r_total = (sum(leg["fraction"] * leg["r"] for leg in legs)
               + open_fraction * (_r_at(plan, entry, new_stop) or 0.0))
    r_total = round(r_total, 4) + 0.0           # float noise must not print '−0.0R'
    if not _priced(money):
        return None, r_total
    open_usd = (_open_whole(money, legs) * (_printed(new_stop) - _printed(entry))
                * _sign(plan.direction))
    return open_usd + sum(_leg_dollars(plan, entry, leg, money) for leg in legs), r_total


def _if_fills_line(plan, new_stop: float, money: Money | None) -> str:
    usd, r_total = stop_projection(plan, new_stop, money)
    figures = _join(_dollars(usd, money) if usd is not None else "", f"{signed_r(r_total)} total")
    return f"{_S['if_fills']} if it fills: {figures}"


def _move_stop_headline(side: dict, stop: float) -> str:
    """D2: a stop move names the broker order, MOVE SELL STOP / MOVE BUY STOP."""
    return f"{_S['stop']} MOVE {side['stop']} → {_price(stop)} now"


def _market_close_headline(detail: dict) -> str:
    if detail.get("reason") in _MARKET_EXIT_REASONS:
        return f"CLOSE AT MARKET now — {_EXIT_WORDS[detail['reason']]}"
    return "CLOSE AT MARKET now"


def _market_close_line(side: dict, exit_price, detail: dict) -> str:
    if detail.get("reason") in _MARKET_EXIT_REASONS:
        return (f"{side['exit']} at market: the runner's {_EXIT_WORDS[detail['reason']]} "
                f"(bot exit @ {_price(exit_price)}); no resting order covers this exit")
    return (f"{side['exit']}: the bot exited on an extended-hours print @ "
            f"{_price(exit_price)}; resting stop orders do not fire outside regular hours")


def _closed(plan, detail: dict, side: dict, common: dict) -> Instruction:
    exit_price = detail.get("exit_price")
    r = total_r(plan, exit_price)
    tone = "good" if r > 0.05 else "bad" if r < -0.05 else "neutral"
    if detail.get("session") == "extended" or detail.get("reason") in _MARKET_EXIT_REASONS:
        verb, headline = CLOSE_AT_MARKET, _market_close_headline(detail)
        lines = [_market_close_line(side, exit_price, detail),
                 f"{signed_r(r)} total"]
    else:
        word = _EXIT_WORDS.get(detail.get("reason"), detail.get("reason") or "closed")
        verb = EXITED
        headline = f"EXITED @ {_price(exit_price)} — {word} · {signed_r(r)} total"
        lines = [f"If your broker order did not fill: {side['exit']}"]
    told, held = detail.get("notified_stop"), detail.get("bot_stop")
    if told is not None and held is not None and not math.isclose(told, held, abs_tol=1e-6):
        lines.append(f"your last pinged stop was {_price(told)} — that order may still be open")
    lines.extend(_staged_order_lines(plan, detail, side))
    return Instruction(verb=verb, headline=headline, lines=tuple(lines), tone=tone, **common)


def _staged_order_lines(plan, detail: dict, side: dict) -> list[str]:
    """v119: a close that leaves a broker order behind. The bot never touches
    the broker, so these only ever tell the reader to cancel or verify."""
    if detail.get("reason") == "time_exit":
        return [f"CANCEL or VERIFY any resting protective {side['stop']} at your broker "
                "-- the bot cannot cancel it for you"]
    if getattr(plan, "time_exit_notified_date", None):      # a due notice was actually sent
        return [short_notice.staged_moc_line(side["exit"])]
    return []


def _auction_clock(stamp: str | None) -> str:
    """'16:00' from an ISO auction time; the raw text if it will not parse."""
    try:
        return dt.datetime.fromisoformat(str(stamp)).strftime("%H:%M ET")
    except ValueError:
        return str(stamp)


def _time_exit(plan, event, side: dict, common: dict, money: Money | None) -> Instruction:
    """v119 ten-session time exit: the due notice (cover at the close auction)
    and the unresolved notice (no official price, nothing was closed)."""
    detail = event.detail
    if event.transition == "time_exit_unresolved":
        lines = [f"{detail.get('reason', 'official closing-auction price unavailable')}; "
                 "the bot has NOT closed this paper trade"]
        if detail.get("cover_fraction") is not None:     # None = schedule missing, no cover advice
            lines.append(f"If you still hold it, {side['exit']} (cover the remaining "
                         f"{detail['cover_fraction']:.0%})")
        return Instruction(
            verb=CLOSE_AT_MARKET, headline="TIME EXIT UNRESOLVED — no official close price",
            lines=tuple(lines), tone="bad", **common)
    qty = _leg_qty(money, detail.get("cover_fraction", 1.0))
    headline, lines = short_notice.compression_due_lines(
        side["exit"], qty, detail, _auction_clock(detail.get("auction_time")))
    return Instruction(verb=CLOSE_AT_MARKET, headline=headline, lines=lines,
                       tone="neutral", **common)


def _closed_event(plan, event, side: dict, common: dict, money: Money | None) -> Instruction:
    return _closed(plan, event.detail, side, common)


def _filled(plan, event, side: dict, common: dict, money: Money | None) -> Instruction:
    fill = _price(event.detail["entry_price"])
    return Instruction(
        verb=FILLED, headline=f"{_S['entry']} FILLED @ {fill} (bot)",
        lines=(f"Confirm your broker filled; the bot's R is measured from {fill}",
               f"Resting: {_S['stop']} {side['stop']} {_price(plan.stop_loss)} · "
               f"{_S['tp1']} {side['limit']} {_price(plan.tp1)}"),
        **common)


def _be_moved(plan, event, side: dict, common: dict, money: Money | None) -> Instruction:
    stop = event.detail["working_stop"]
    return Instruction(
        verb=MOVE_STOP, headline=_move_stop_headline(side, stop),
        lines=(f"{_S['breakeven']} break-even", _if_fills_line(plan, stop, money)),
        **common)


def _realised_leg(plan, leg: dict, money: Money | None) -> str:
    """A banked leg's dollars (record arithmetic), or '' when unpriced."""
    if not _priced(money) or plan.entry_price is None:
        return ""
    return _dollars(_leg_dollars(plan, plan.entry_price, leg, money), money)


def _tp1_partial(plan, event, side: dict, common: dict, money: Money | None) -> Instruction:
    detail = event.detail
    pnl = _join(_realised_leg(plan, detail, money), signed_r(detail["r"]))
    return Instruction(
        verb=MOVE_STOP,
        headline=(f"{_S['tp1']} TP1 FILLED {_leg_qty(money, detail['fraction'])} @ "
                  f"{_price(detail['exit_price'])} · {_S['pnl']} {pnl}"),
        lines=(f"{_S['stop']} MOVE {side['stop']} on the runner → "
               f"{_price(detail['working_stop'])} now (runner floor)",),
        tone="good", **common)


def _stop_moved(plan, event, side: dict, common: dict, money: Money | None) -> Instruction:
    new = event.detail["new"]
    kind = _stop_kind(plan, new)
    return Instruction(
        verb=MOVE_STOP, headline=_move_stop_headline(side, new),
        lines=(f"{_S[_STOP_KIND_KEYS[kind]]} {kind}; {signed_r(event.detail['r_moved'])} "
               "since the last ping",
               _if_fills_line(plan, new, money)),
        **common)


#: cancel transition -> its headline's FEED_SYMBOLS key ('' = no glyph, v170 Decision 4).
_CANCEL_LEADS = {"cancelled_expired": "expiry", "cancelled_invalidated": "invalid",
                 "cancelled_risk_cap": ""}


def _cancel_why(plan, transition: str, detail: dict) -> str:
    if detail.get("reason_message"):
        return detail["reason_message"]             # v144: an outlook plan states its reason
    if short_notice.is_compression(plan) and transition != "cancelled_invalidated":
        return short_notice.compression_cancel_why(plan, transition, detail)
    if transition == "cancelled_expired":
        return f"not triggered within {plan.expiry_bars} sessions"
    if transition == "cancelled_invalidated":
        return f"price reached the stop {_price(plan.stop_loss)} before triggering"
    return (f"triggered at {_price(detail['entry_price'])} but risked "
            f"{detail['planned_loss_pct']:.1f}% against stop "
            f"{_price(detail['stop_loss'])} -- above the "
            f"{detail['max_planned_loss_pct']:.1f}% cap; never filled")


def _cancelled(plan, event, side: dict, common: dict, money: Money | None) -> Instruction:
    key = _CANCEL_LEADS[event.transition]
    lead = f"{_S[key]} " if key else ""
    return Instruction(
        verb=CANCEL,
        headline=f"{lead}CANCEL {side['entry_stop']} {_price(plan.trigger_price)}",
        lines=(_cancel_why(plan, event.transition, event.detail),), tone="inert", **common)


#: Every feed transition's builder; each takes (plan, event, side, common, money).
_BUILDERS = {
    "filled": _filled,
    "be_moved": _be_moved,
    "tp1_partial": _tp1_partial,
    "stop_moved": _stop_moved,
    "cancelled_expired": _cancelled,
    "cancelled_invalidated": _cancelled,
    "cancelled_risk_cap": _cancelled,
    "time_exit_due": _time_exit,
    "time_exit_unresolved": _time_exit,
    "closed": _closed_event,
}


def instruction_for(plan, event, *, money: Money | None = None) -> Instruction:
    """The execution-feed instruction for one plan_manager PlanEvent (v81 D2,
    D3). Every live stop is read from ``event.detail``, which plan_manager
    stamps -- never recomputed here, so the feed cannot quote a stop the
    manager is not holding. v170: ``money`` (the linked paper record, or an
    unpriced snapshot) supplies share counts and dollars; every transition
    is one entry of _BUILDERS."""
    builder = _BUILDERS.get(event.transition)
    if builder is None:
        raise ValueError(f"no execution-feed instruction for {event.transition!r}")
    common = dict(ticker=plan.ticker, direction=plan.direction, plan_id=plan.plan_id)
    return builder(plan, event, _sides(plan.direction), common, money)
