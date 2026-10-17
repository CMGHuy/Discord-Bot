"""Discord rendering for the v81 execution feed.

Message wording is projected by presentation.instructions. This module picks
the v110 registry kind for each message, adds the ANSI price block where the
kind carries one (NEW SETUP ticket, ENTRY fill, RESULT close), and applies the
shared chrome.
"""
import logging

import discord

from swingbot import config
from swingbot.core import presentation as ui
from swingbot.core.presentation import kinds
from swingbot.core.presentation.instructions import (CLOSE_AT_MARKET, DO_NOT_PLACE, Instruction,
                                                     Money, block_warnings, instruction_for,
                                                     money_from, ticket_for, total_r)
from swingbot.core.presentation.kinds import Family, Kind

from .plan_table import _sizing_snapshot

log = logging.getLogger(__name__)


#: feed transition -> registry kind; "filled" and "closed" are styled in _event_style.
_EVENT_KINDS = {
    "be_moved": Kind.BE_MOVED,
    "tp1_partial": Kind.TP1_HIT,
    "stop_moved": Kind.MOVE_STOP,
    "cancelled_expired": Kind.EXPIRED,
    "cancelled_invalidated": Kind.INVALIDATED,
    "cancelled_risk_cap": Kind.RISK_CAP,
}


def _result_detail(kind: Kind, r: float | None) -> str:
    """Expired / invalidated carry only their grey ⏹️ mark (the label names them);
    a closed trade reads its outcome from R."""
    if kind in (Kind.EXPIRED, Kind.INVALIDATED):
        return kinds.outcome_mark(kind.name.lower())
    return kinds.outcome_detail(kinds.outcome_for_r(r), r)


def render(instruction: Instruction, kind: Kind, *, block: str | None = None,
           r: float | None = None) -> discord.Embed:
    """Registry title and push line; body = ANSI block (if any), warnings,
    bold headline, instruction lines."""
    detail = _result_detail(kind, r) if kind.family is Family.RESULT else ""
    embed = ui.push_embed(kind, instruction.ticker, instruction.direction, detail)
    body = [*instruction.warnings, f"**{instruction.headline}**", *instruction.lines]
    embed.description = "\n".join([block, *body] if block else body)
    ui.apply_chrome(embed, kind=kind, level=instruction.level, r=r, plan_id=instruction.plan_id,
                    link_base=config.ADMIN_PUBLIC_URL)
    return embed


def _entry(plan) -> float:
    return plan.entry_price if plan.entry_price is not None else plan.trigger_price


def _move_pct(entry: float | None, exit_price: float | None, direction: str) -> float | None:
    if not entry or exit_price is None:
        return None
    sign = 1 if direction == "bullish" else -1
    return (exit_price - entry) / entry * 100 * sign


def plan_levels_block(plan, entry: float | None) -> str:
    """A plan's levels block from ``entry`` (trigger for a ticket, fill for an entry)."""
    return ui.levels_block(direction=plan.direction, entry=entry, stop=plan.stop_loss,
                           tp1=plan.tp1, tp2=plan.tp2)


def plan_result_block(plan, exit_price: float | None, r: float | None) -> str:
    """A plan's RESULT block: entry → exit / stop and the realised R."""
    return ui.result_headline(direction=plan.direction, entry=plan.entry_price,
                              exit_price=exit_price, stop=plan.stop_loss,
                              pct=_move_pct(plan.entry_price, exit_price, plan.direction), r=r)


def _ticket_money(plan) -> Money:
    """The ticket's money: the same sizing snapshot scan_run logs the paper
    trade from in the same scan (v170 §1); unsized when there is none."""
    sizing = _sizing_snapshot(_entry(plan), plan) or {}
    return money_from(sizing.get("shares"), config.CURRENCY_SYMBOL)


def build_ticket_embed(item, plan) -> discord.Embed:
    """Render a new v2 alert's order ticket."""
    instruction = ticket_for(
        plan, logged=item.paper_logged, not_logged_reason=item.not_logged_reason,
        money=_ticket_money(plan),
        warnings=block_warnings(heat=getattr(item, "heat_blocked", None),
                                cluster=getattr(item, "cluster_blocked", None),
                                kill=getattr(item, "kill_switch_blocked", None)),
        level=item.conf.level,
    )
    kind = Kind.TICKET_DO_NOT_PLACE if instruction.verb == DO_NOT_PLACE else Kind.TICKET_PLACE
    return render(instruction, kind, block=plan_levels_block(plan, plan.trigger_price))


def _event_style(plan, event, instruction: Instruction) -> tuple:
    """(kind, ANSI block or None, realised R or None) for one feed event."""
    if event.transition == "closed":
        exit_price = event.detail.get("exit_price")
        r = total_r(plan, exit_price)
        kind = Kind.CLOSE_AT_MARKET if instruction.verb == CLOSE_AT_MARKET else Kind.EXITED
        return kind, plan_result_block(plan, exit_price, r), r
    if event.transition == "filled":
        return Kind.FILLED, plan_levels_block(plan, event.detail["entry_price"]), None
    return _EVENT_KINDS.get(event.transition, Kind.PLAN_UPDATE), None, None


def _linked_trade(plan_id: str) -> dict | None:
    """The plan's paper-trade record in any status (TradeLog.trade_for_plan),
    or None. Never raises: a failed lookup renders the message without $.
    Imported here, not at module level, to keep scanning's import graph as
    it was."""
    if not plan_id:
        return None
    try:
        from swingbot.core.tracking.performance import TradeLog
        return TradeLog().trade_for_plan(plan_id)
    except Exception:
        log.warning("execution feed: trade lookup failed for plan %s", plan_id, exc_info=True)
        return None


def _event_money(plan) -> Money:
    """Lifecycle money from the plan's linked paper record (v170 §1): share
    counts and dollars from one record, so a trade opened at one balance is
    never re-sized against a later one. No linked record (or one without
    shares): today's sizing snapshot for the share counts, as before v170,
    and no dollar figure at all."""
    trade = _linked_trade(plan.plan_id)
    if trade and trade.get("shares"):
        return money_from(trade["shares"], config.CURRENCY_SYMBOL,
                          realized_amount=trade.get("realized_pnl_amount"))
    sizing = _sizing_snapshot(_entry(plan), plan) or {}
    return money_from(sizing.get("shares"), config.CURRENCY_SYMBOL, priced=False)


def build_instruction_embed(plan, event) -> discord.Embed:
    """Render one lifecycle event for the execution feed."""
    instruction = instruction_for(plan, event, money=_event_money(plan))
    kind, block, r = _event_style(plan, event, instruction)
    return render(instruction, kind, block=block, r=r)
