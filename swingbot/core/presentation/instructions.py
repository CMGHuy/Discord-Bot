"""v81: the execution feed's broker instructions, as pure data.

Every message the simple-alerts channel sends -- an alert's order ticket and
each plan lifecycle event -- is projected here into the verb and the order
lines a reader places at a broker. No discord import, no I/O, no clock:
sizing, block annotations and every live stop arrive as arguments or in the
event's detail, which plan_manager stamps. core/scanning/execution_embeds.py
is the only thing that turns an Instruction into a Discord embed.
"""
from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass

from swingbot.core.planning.exit_sim import runner_floor
from swingbot.core.planning.plan_types import breakeven_trigger
from swingbot.core.presentation import tokens
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
}


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


def _whole_shares(sizing: dict | None) -> int | None:
    """compute_position_size returns fractional shares (2dp); a broker order
    is whole shares, so the ticket rounds down. None when unsized."""
    if not sizing or not sizing.get("shares"):
        return None
    return math.floor(sizing["shares"]) or None


def signed_r(x: float) -> str:
    """``+0.8R`` / ``−1.1R`` / ``0.0R`` -- the feed signs every non-zero R."""
    text = tokens.fmt_r(x)
    return text if x < 0 or text == "0.0R" else f"+{text}"


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


def ticket_for(plan, *, logged: bool, not_logged_reason: str | None,
               sizing: dict | None, currency: str = "",
               warnings: tuple[str, ...] = (), level: int | None = None) -> Instruction:
    """The order ticket for a new alert (v81 D1, D2, D4). ``logged`` is
    scan_run's own paper-trade decision; the verb mirrors it."""
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

    whole = _whole_shares(sizing)
    if whole is None:
        size = "size n/a"
        tp1_qty = f"{plan.tp1_fraction:.0%}"
        runner_qty = f"{1 - plan.tp1_fraction:.0%}"
    else:
        tp1_shares = math.floor(whole * plan.tp1_fraction)
        size = f"{whole:,} sh (risk {currency}{sizing['risk_amount']:,.0f})"
        tp1_qty = f"{tp1_shares:,} sh ({plan.tp1_fraction:.0%})"
        runner_qty = f"{whole - tp1_shares:,} sh"

    if plan.entry_type == "stop_entry":
        headline = f"{side['entry_stop']} {_price(plan.trigger_price)} · {size}"
    else:
        headline = f"{side['entry_market']} ~{_price(plan.trigger_price)} · {size}"
    trail = f"trail {plan.trail_atr_mult:g}×ATR"
    runner_to = f"TP2 {_price(plan.tp2)} / {trail}" if plan.tp2 is not None else trail
    lines = [
        f"{side['stop']} {_price(plan.stop_loss)}",
        f"TP1 {side['limit']} {_price(plan.tp1)} · {tp1_qty}",
        f"RUNNER {runner_qty} → {runner_to} — stop moves are pinged here",
        f"Stop → entry once price reaches {_price(breakeven_trigger(plan, entry))}",
    ]
    if plan.entry_type == "stop_entry":
        sessions = plan_view(plan, bars_since_created=0).bars_to_expiry
        if sessions is None:
            sessions = plan.expiry_bars
        last = approx_last_trigger_session(plan.created_at, plan.expiry_bars)
        lines.append(f"Cancel if: not triggered by the close of ≈ {last:%a %d %b} "
                     f"({sessions} sessions), or price reaches "
                     f"{_price(plan.stop_loss)} first")
    return Instruction(verb=PLACE, headline=headline, lines=tuple(lines),
                       warnings=tuple(warnings), tone="level", **common)


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


def _closed(plan, detail: dict, side: dict, common: dict) -> Instruction:
    exit_price = detail.get("exit_price")
    r = total_r(plan, exit_price)
    tone = "good" if r > 0.05 else "bad" if r < -0.05 else "neutral"
    if detail.get("session") == "extended":
        verb, headline = CLOSE_AT_MARKET, "CLOSE AT MARKET now"
        lines = [f"{side['exit']}: the bot exited on an extended-hours print @ "
                 f"{_price(exit_price)}; resting stop orders do not fire outside "
                 "regular hours",
                 f"{signed_r(r)} total"]
    else:
        word = _EXIT_WORDS.get(detail.get("reason"), detail.get("reason") or "closed")
        verb = EXITED
        headline = f"EXITED @ {_price(exit_price)} — {word} · {signed_r(r)} total"
        lines = [f"If your broker order did not fill: {side['exit']}"]
    told, held = detail.get("notified_stop"), detail.get("bot_stop")
    if told is not None and held is not None and not math.isclose(told, held, abs_tol=1e-6):
        lines.append(f"your last pinged stop was {_price(told)} — that order may still be open")
    return Instruction(verb=verb, headline=headline, lines=tuple(lines), tone=tone, **common)


def instruction_for(plan, event, *, sizing: dict | None = None) -> Instruction:
    """The execution-feed instruction for one plan_manager PlanEvent (v81 D2,
    D3). Every live stop is read from ``event.detail``, which plan_manager
    stamps -- never recomputed here, so the feed cannot quote a stop the
    manager is not holding."""
    side = _sides(plan.direction)
    detail = event.detail
    common = dict(ticker=plan.ticker, direction=plan.direction, plan_id=plan.plan_id)
    transition = event.transition
    if transition == "filled":
        fill = _price(detail["entry_price"])
        return Instruction(
            verb=FILLED, headline=f"FILLED @ {fill} (bot)",
            lines=(f"Confirm your broker filled; the bot's R is measured from {fill}",
                   f"Resting: {side['stop']} {_price(plan.stop_loss)} · "
                   f"TP1 {side['limit']} {_price(plan.tp1)}"),
            **common)
    if transition == "be_moved":
        return Instruction(
            verb=MOVE_STOP,
            headline=f"MOVE STOP → {_price(detail['working_stop'])} after today's close",
            lines=(f"break-even; keep {_price(plan.stop_loss)} until then",), **common)
    if transition == "tp1_partial":
        whole = _whole_shares(sizing)
        qty = (f"{math.floor(whole * detail['fraction']):,} sh" if whole is not None
               else f"{detail['fraction']:.0%}")
        return Instruction(
            verb=MOVE_STOP,
            headline=(f"TP1 FILLED {qty} @ {_price(detail['exit_price'])} "
                      f"({signed_r(detail['r'])})"),
            lines=(f"MOVE STOP on the runner → {_price(detail['working_stop'])} now "
                   "(runner floor)",),
            tone="good", **common)
    if transition == "stop_moved":
        timing = "after today's close" if detail["effective"] == "next_session" else "now"
        return Instruction(
            verb=MOVE_STOP, headline=f"MOVE STOP → {_price(detail['new'])} {timing}",
            lines=(f"{_stop_kind(plan, detail['new'])}; {signed_r(detail['r_moved'])} "
                   "since the last ping",),
            **common)
    if transition in ("cancelled_expired", "cancelled_invalidated"):
        why = (f"not triggered within {plan.expiry_bars} sessions"
               if transition == "cancelled_expired"
               else f"price reached the stop {_price(plan.stop_loss)} before triggering")
        return Instruction(
            verb=CANCEL, headline=f"CANCEL {side['entry_stop']} {_price(plan.trigger_price)}",
            lines=(why,), tone="inert", **common)
    if transition == "closed":
        return _closed(plan, detail, side, common)
    raise ValueError(f"no execution-feed instruction for {transition!r}")
