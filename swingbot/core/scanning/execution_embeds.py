"""Discord rendering for the v81 execution feed.

Message wording is projected by presentation.instructions; this module only
applies shared Discord chrome and accents.
"""
import discord

from swingbot import config
from swingbot.core import presentation as ui
from swingbot.core.presentation.instructions import (Instruction, block_warnings,
                                                     instruction_for, ticket_for)

from .plan_table import _sizing_snapshot


_OUTCOME_FOR_TONE = {"good": "win", "bad": "loss", "neutral": "scratch"}


def _accent(instruction: Instruction):
    if instruction.tone == "level":
        return ui.accent_for_level(instruction.level)
    if instruction.tone == "inert":
        return ui.accent_blocked()
    return ui.accent_for_outcome(_OUTCOME_FOR_TONE.get(instruction.tone, "scratch"))


def render(instruction: Instruction) -> discord.Embed:
    """Render warnings, headline and instruction lines with shared chrome."""
    side = "LONG" if instruction.direction == "bullish" else "SHORT"
    embed = discord.Embed(title=(f"{ui.direction_glyph(instruction.direction)} {side} "
                                 f"{instruction.ticker} — {instruction.verb}"))
    embed.description = "\n".join([*instruction.warnings, f"**{instruction.headline}**",
                                   *instruction.lines])
    ui.apply_chrome(embed, accent=_accent(instruction), plan_id=instruction.plan_id)
    return embed


def _entry(plan) -> float:
    return plan.entry_price if plan.entry_price is not None else plan.trigger_price


def build_ticket_embed(item, plan) -> discord.Embed:
    """Render a new v2 alert's order ticket."""
    return render(ticket_for(
        plan, logged=item.paper_logged, not_logged_reason=item.not_logged_reason,
        sizing=_sizing_snapshot(_entry(plan), plan), currency=config.CURRENCY_SYMBOL,
        warnings=block_warnings(heat=getattr(item, "heat_blocked", None),
                                cluster=getattr(item, "cluster_blocked", None),
                                kill=getattr(item, "kill_switch_blocked", None)),
        level=item.conf.level,
    ))


def build_instruction_embed(plan, event) -> discord.Embed:
    """Render one lifecycle event for the execution feed."""
    return render(instruction_for(plan, event, sizing=_sizing_snapshot(_entry(plan), plan)))
