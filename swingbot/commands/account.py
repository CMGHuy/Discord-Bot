"""!account and its subcommands."""
from swingbot.core.account import (
    load_account_config, set_balance, set_max_open_positions, set_max_position_pct,
    set_max_position_value_absolute, set_max_risk_amount_absolute, set_position_pct,
    set_risk_pct, set_sizing_mode,
)
from swingbot.bot_core import bot


@bot.group(name="account", invoke_without_command=True)
async def account_cmd(ctx):
    cfg = load_account_config()
    mode = cfg.get("sizing_mode", "risk_pct")
    if mode == "account_pct":
        sizing_line = f"Position sizing: **Account %** -- {cfg.get('position_pct', 0.1)}% of balance per trade"
    else:
        sizing_line = f"Position sizing: **Risk %** -- {cfg['risk_pct']}% of balance risked per trade"
    await ctx.send(
        f"**Account settings:**\nBalance: {cfg['balance']} "
        f"(base {cfg.get('base_balance', cfg['balance'])} + all-time realized P&L)\n{sizing_line}\n"
        f"Max position size: {cfg.get('max_position_pct', 0.1)}% of balance, capped at "
        f"{cfg.get('max_position_value_absolute', 1000)} absolute\n"
        f"Max risk per trade: {cfg.get('max_risk_amount_absolute', 100)} absolute (hard cap, regardless of %)\n"
        f"Max concurrent open positions: {cfg.get('max_open_positions', 5)}\n\n"
        f"Change with `!account balance <amount>`, `!account sizing risk|account`, "
        f"`!account positionpct <pct>`, `!account risk <pct>`, `!account maxpositions <n>`, "
        f"`!account maxpositionpct <pct>`, `!account maxposition <amount>`, `!account maxrisk <amount>`"
    )


@account_cmd.command(name="balance")
async def account_balance(ctx, amount: float):
    cfg = set_balance(amount)
    await ctx.send(
        f"Base balance set to {amount} -- effective balance is now {cfg['balance']} "
        f"(base + all-time realized P&L). This will keep accounting for realized "
        f"gain/loss on top of this new base going forward."
    )


@account_cmd.command(name="risk")
async def account_risk(ctx, pct: float):
    cfg = set_risk_pct(pct)
    await ctx.send(f"Risk per trade set to {cfg['risk_pct']}%.")


@account_cmd.command(name="maxpositions")
async def account_maxpositions(ctx, n: int):
    cfg = set_max_open_positions(n)
    await ctx.send(f"Max concurrent open positions set to {cfg['max_open_positions']}.")


@account_cmd.command(name="sizing")
async def account_sizing(ctx, mode: str):
    """`!account sizing risk` (fixed-fractional, size varies with stop distance) or
    `!account sizing account` (fixed allocation -- every trade opens at exactly
    `positionpct`% of the account, regardless of stop distance)."""
    try:
        cfg = set_sizing_mode(mode)
    except ValueError as e:
        await ctx.send(str(e))
        return
    if cfg["sizing_mode"] == "account_pct":
        await ctx.send(
            f"Position sizing set to **Account %** -- every trade now opens at "
            f"{cfg.get('position_pct', 0.1)}% of the account balance ({cfg['balance']}), "
            f"regardless of stop distance. Change the % with `!account positionpct <pct>`."
        )
    else:
        await ctx.send(
            f"Position sizing set to **Risk %** -- every trade is now sized so a full "
            f"stop-out costs {cfg['risk_pct']}% of the account balance."
        )


@account_cmd.command(name="positionpct")
async def account_positionpct(ctx, pct: float):
    """Only used in 'account' sizing mode -- see `!account sizing`."""
    cfg = set_position_pct(pct)
    note = "" if cfg.get("sizing_mode") == "account_pct" else " (currently unused -- switch with `!account sizing account` to apply it)"
    await ctx.send(f"Position size set to {cfg['position_pct']}% of account per trade{note}.")


@account_cmd.command(name="maxpositionpct")
async def account_maxpositionpct(ctx, pct: float):
    """Position-size cap as a % of balance -- see `!account maxposition` for the
    absolute currency cap that holds regardless of balance."""
    cfg = set_max_position_pct(pct)
    await ctx.send(
        f"Max position size set to {cfg['max_position_pct']}% of balance "
        f"(still also capped at {cfg.get('max_position_value_absolute', 1000)} absolute)."
    )


@account_cmd.command(name="maxposition")
async def account_maxposition(ctx, amount: float):
    """Hard currency cap on position value -- holds no matter what the account
    balance or % settings are. Set to 0 to disable and rely on maxpositionpct alone."""
    cfg = set_max_position_value_absolute(amount)
    await ctx.send(
        f"Max position size set to {cfg['max_position_value_absolute']} absolute -- "
        f"no trade will ever open larger than this, regardless of balance or % settings."
    )


@account_cmd.command(name="maxrisk")
async def account_maxrisk(ctx, amount: float):
    """Hard currency cap on the REAL risk if a trade's stop-loss is hit -- holds no
    matter what the account balance, sizing mode, or risk % are. Set to 0 to disable."""
    cfg = set_max_risk_amount_absolute(amount)
    await ctx.send(
        f"Max loss per trade set to {cfg['max_risk_amount_absolute']} absolute -- "
        f"no trade's real risk-if-stopped will ever exceed this, regardless of balance, "
        f"sizing mode, or risk %."
    )
