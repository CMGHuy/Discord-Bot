"""!account and its subcommands."""
from swingbot.core.account import (
    load_account_config, set_balance, set_max_open_positions, set_position_pct,
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
        f"Max concurrent open positions: {cfg.get('max_open_positions', 5)}\n\n"
        f"Change with `!account balance <amount>`, `!account sizing risk|account`, "
        f"`!account positionpct <pct>`, `!account risk <pct>`, `!account maxpositions <n>`"
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
