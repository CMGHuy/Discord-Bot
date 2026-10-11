"""!account and its subcommands, and their /account slash twins (v153).

Each body lives in one handle_account_<x>(reply, ...) handler. The prefix
command and the /account <x> subcommand both call it through a Reply
(swingbot/commands/reply.py), so the two surfaces cannot drift.
"""
import discord
from discord import app_commands

from swingbot.core.planning.account import (
    load_account_config, set_balance, set_max_open_positions, set_max_position_pct,
    set_max_position_value_absolute, set_max_risk_amount_absolute, set_position_pct,
    set_risk_pct, set_sizing_mode,
)
from swingbot.bot_core import bot
from swingbot.commands.reply import CtxReply, InteractionReply, send_prefix_tip


_EDGE_SIZING_LABELS = {
    "kelly": "Quarter-Kelly", "vol_target": "Vol-target", "min_of_all": "Min-of-all",
}

# Values are what set_sizing_mode() accepts (core/planning/account.py).
SIZING_CHOICES = [
    app_commands.Choice(name="Risk % (size from stop distance)", value="risk"),
    app_commands.Choice(name="Account % (fixed allocation)", value="account"),
    app_commands.Choice(name="Quarter-Kelly", value="kelly"),
    app_commands.Choice(name="Vol-target", value="vol_target"),
    app_commands.Choice(name="Min-of-all", value="min_of_all"),
]


# ──────────────────────────────────────────────
# Text builders
# ──────────────────────────────────────────────

def _sizing_line(cfg: dict) -> str:
    mode = cfg.get("sizing_mode", "risk_pct")
    if mode == "account_pct":
        return f"Position sizing: **Account %** -- {cfg.get('position_pct', 0.1)}% of balance per trade"
    if mode in _EDGE_SIZING_LABELS:
        return (f"Position sizing: **{_EDGE_SIZING_LABELS[mode]}** -- effective risk computed "
                f"per-trade from strategy/volatility stats (config risk % {cfg['risk_pct']} is the ceiling)")
    return f"Position sizing: **Risk %** -- {cfg['risk_pct']}% of balance risked per trade"


def _sizing_set_text(cfg: dict) -> str:
    if cfg["sizing_mode"] == "account_pct":
        return (
            f"Position sizing set to **Account %** -- every trade now opens at "
            f"{cfg.get('position_pct', 0.1)}% of the account balance ({cfg['balance']}), "
            f"regardless of stop distance. Change the % with `!account positionpct <pct>`."
        )
    if cfg["sizing_mode"] in _EDGE_SIZING_LABELS:
        return (
            f"Position sizing set to **{_EDGE_SIZING_LABELS[cfg['sizing_mode']]}** -- effective risk is "
            f"computed per-trade from strategy/volatility stats, never above your risk % "
            f"({cfg['risk_pct']}%, the ceiling) or the frozen 2% hard cap."
        )
    return (
        f"Position sizing set to **Risk %** -- every trade is now sized so a full "
        f"stop-out costs {cfg['risk_pct']}% of the account balance."
    )


# ──────────────────────────────────────────────
# Handlers (one body per command, shared by ! and /)
# ──────────────────────────────────────────────

async def handle_account_show(reply) -> None:
    cfg = load_account_config()
    await reply.send(
        f"**Account settings:**\nBalance: {cfg['balance']} "
        f"(base {cfg.get('base_balance', cfg['balance'])} + all-time realized P&L)\n{_sizing_line(cfg)}\n"
        f"Max position size: {cfg.get('max_position_pct', 0.1)}% of balance, capped at "
        f"{cfg.get('max_position_value_absolute', 1000)} absolute\n"
        f"Max risk per trade: {cfg.get('max_risk_amount_absolute', 100)} absolute (hard cap, regardless of %)\n"
        f"Max concurrent open positions: {cfg.get('max_open_positions', 5)}\n\n"
        f"Change with `!account balance <amount>`, `!account sizing risk|account`, "
        f"`!account positionpct <pct>`, `!account risk <pct>`, `!account maxpositions <n>`, "
        f"`!account maxpositionpct <pct>`, `!account maxposition <amount>`, `!account maxrisk <amount>`"
    )


async def handle_account_balance(reply, amount: float) -> None:
    cfg = set_balance(amount)
    await reply.send(
        f"Base balance set to {amount} -- effective balance is now {cfg['balance']} "
        f"(base + all-time realized P&L). This will keep accounting for realized "
        f"gain/loss on top of this new base going forward."
    )


async def handle_account_risk(reply, pct: float) -> None:
    cfg = set_risk_pct(pct)
    await reply.send(f"Risk per trade set to {cfg['risk_pct']}%.")


async def handle_account_maxpositions(reply, n: int) -> None:
    cfg = set_max_open_positions(n)
    await reply.send(f"Max concurrent open positions set to {cfg['max_open_positions']}.")


async def handle_account_sizing(reply, mode: str) -> None:
    """`risk` (fixed-fractional, size varies with stop distance) or `account`
    (fixed allocation -- every trade opens at exactly `positionpct`% of the
    account, regardless of stop distance), or an edge sizing mode."""
    try:
        cfg = set_sizing_mode(mode)
    except ValueError as e:
        await reply.send_error(str(e))
        return
    await reply.send(_sizing_set_text(cfg))


async def handle_account_positionpct(reply, pct: float) -> None:
    """Only used in 'account' sizing mode -- see `!account sizing`."""
    cfg = set_position_pct(pct)
    note = "" if cfg.get("sizing_mode") == "account_pct" else " (currently unused -- switch with `!account sizing account` to apply it)"
    await reply.send(f"Position size set to {cfg['position_pct']}% of account per trade{note}.")


async def handle_account_maxpositionpct(reply, pct: float) -> None:
    """Position-size cap as a % of balance -- see `!account maxposition` for the
    absolute currency cap that holds regardless of balance."""
    cfg = set_max_position_pct(pct)
    await reply.send(
        f"Max position size set to {cfg['max_position_pct']}% of balance "
        f"(still also capped at {cfg.get('max_position_value_absolute', 1000)} absolute)."
    )


async def handle_account_maxposition(reply, amount: float) -> None:
    """Hard currency cap on position value -- holds no matter what the account
    balance or % settings are. Set to 0 to disable and rely on maxpositionpct alone."""
    cfg = set_max_position_value_absolute(amount)
    await reply.send(
        f"Max position size set to {cfg['max_position_value_absolute']} absolute -- "
        f"no trade will ever open larger than this, regardless of balance or % settings."
    )


async def handle_account_maxrisk(reply, amount: float) -> None:
    """Hard currency cap on the REAL risk if a trade's stop-loss is hit -- holds no
    matter what the account balance, sizing mode, or risk % are. Set to 0 to disable."""
    cfg = set_max_risk_amount_absolute(amount)
    await reply.send(
        f"Max loss per trade set to {cfg['max_risk_amount_absolute']} absolute -- "
        f"no trade's real risk-if-stopped will ever exceed this, regardless of balance, "
        f"sizing mode, or risk %."
    )


# ──────────────────────────────────────────────
# ! prefix commands
# ──────────────────────────────────────────────

@bot.group(name="account", invoke_without_command=True)
async def account_cmd(ctx):
    reply = CtxReply(ctx)
    await handle_account_show(reply)
    await send_prefix_tip(ctx, reply)


@account_cmd.command(name="balance")
async def account_balance(ctx, amount: float):
    reply = CtxReply(ctx)
    await handle_account_balance(reply, amount)
    await send_prefix_tip(ctx, reply)


@account_cmd.command(name="risk")
async def account_risk(ctx, pct: float):
    reply = CtxReply(ctx)
    await handle_account_risk(reply, pct)
    await send_prefix_tip(ctx, reply)


@account_cmd.command(name="maxpositions")
async def account_maxpositions(ctx, n: int):
    reply = CtxReply(ctx)
    await handle_account_maxpositions(reply, n)
    await send_prefix_tip(ctx, reply)


@account_cmd.command(name="sizing")
async def account_sizing(ctx, mode: str):
    """`!account sizing risk` (fixed-fractional, size varies with stop distance) or
    `!account sizing account` (fixed allocation -- every trade opens at exactly
    `positionpct`% of the account, regardless of stop distance)."""
    reply = CtxReply(ctx)
    await handle_account_sizing(reply, mode)
    await send_prefix_tip(ctx, reply)


@account_cmd.command(name="positionpct")
async def account_positionpct(ctx, pct: float):
    """Only used in 'account' sizing mode -- see `!account sizing`."""
    reply = CtxReply(ctx)
    await handle_account_positionpct(reply, pct)
    await send_prefix_tip(ctx, reply)


@account_cmd.command(name="maxpositionpct")
async def account_maxpositionpct(ctx, pct: float):
    """Position-size cap as a % of balance."""
    reply = CtxReply(ctx)
    await handle_account_maxpositionpct(reply, pct)
    await send_prefix_tip(ctx, reply)


@account_cmd.command(name="maxposition")
async def account_maxposition(ctx, amount: float):
    """Hard currency cap on position value."""
    reply = CtxReply(ctx)
    await handle_account_maxposition(reply, amount)
    await send_prefix_tip(ctx, reply)


@account_cmd.command(name="maxrisk")
async def account_maxrisk(ctx, amount: float):
    """Hard currency cap on the real risk if a trade's stop-loss is hit."""
    reply = CtxReply(ctx)
    await handle_account_maxrisk(reply, amount)
    await send_prefix_tip(ctx, reply)


# ──────────────────────────────────────────────
# /account slash group (new in v153; `!account` alone maps to /account show)
# ──────────────────────────────────────────────

account_group = app_commands.Group(
    name="account", description="Show or change the account balance, risk and position sizing",
)


@account_group.command(name="show", description="Show the account settings")
async def slash_account_show(interaction: discord.Interaction):
    await handle_account_show(InteractionReply(interaction))


@account_group.command(name="balance", description="Set the base balance (realized P&L keeps adding on top)")
@app_commands.describe(amount="New base balance")
async def slash_account_balance(interaction: discord.Interaction, amount: float):
    await handle_account_balance(InteractionReply(interaction), amount)


@account_group.command(name="risk", description="Set the % of balance risked per trade")
@app_commands.describe(pct="Risk per trade, in percent")
async def slash_account_risk(interaction: discord.Interaction, pct: float):
    await handle_account_risk(InteractionReply(interaction), pct)


@account_group.command(name="maxpositions", description="Set the max number of concurrent open positions")
@app_commands.describe(n="Max concurrent open positions")
async def slash_account_maxpositions(interaction: discord.Interaction, n: int):
    await handle_account_maxpositions(InteractionReply(interaction), n)


@account_group.command(name="sizing", description="Choose the position-sizing mode")
@app_commands.describe(mode="Sizing mode")
@app_commands.choices(mode=SIZING_CHOICES)
async def slash_account_sizing(interaction: discord.Interaction, mode: app_commands.Choice[str]):
    await handle_account_sizing(InteractionReply(interaction), mode.value)


@account_group.command(name="positionpct", description="Set the position size as a % of account (account sizing mode)")
@app_commands.describe(pct="Position size, in percent of the account")
async def slash_account_positionpct(interaction: discord.Interaction, pct: float):
    await handle_account_positionpct(InteractionReply(interaction), pct)


@account_group.command(name="maxpositionpct", description="Cap a position's size as a % of balance")
@app_commands.describe(pct="Position-size cap, in percent of balance")
async def slash_account_maxpositionpct(interaction: discord.Interaction, pct: float):
    await handle_account_maxpositionpct(InteractionReply(interaction), pct)


@account_group.command(name="maxposition", description="Cap a position's value in currency (0 disables)")
@app_commands.describe(amount="Max position value, absolute")
async def slash_account_maxposition(interaction: discord.Interaction, amount: float):
    await handle_account_maxposition(InteractionReply(interaction), amount)


@account_group.command(name="maxrisk", description="Cap the real loss per trade in currency (0 disables)")
@app_commands.describe(amount="Max loss per trade, absolute")
async def slash_account_maxrisk(interaction: discord.Interaction, amount: float):
    await handle_account_maxrisk(InteractionReply(interaction), amount)


bot.tree.add_command(account_group)
