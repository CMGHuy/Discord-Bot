"""!account and its subcommands."""
from swingbot.core.account import load_account_config, set_balance, set_max_open_positions, set_risk_pct
from swingbot.bot_core import bot


@bot.group(name="account", invoke_without_command=True)
async def account_cmd(ctx):
    cfg = load_account_config()
    await ctx.send(
        f"**Account settings:**\nBalance: {cfg['balance']}\nRisk per trade: {cfg['risk_pct']}%\n"
        f"Max concurrent open positions: {cfg.get('max_open_positions', 5)}\n\n"
        f"Change with `!account balance <amount>`, `!account risk <pct>`, `!account maxpositions <n>`"
    )


@account_cmd.command(name="balance")
async def account_balance(ctx, amount: float):
    cfg = set_balance(amount)
    await ctx.send(f"Account balance set to {cfg['balance']}.")


@account_cmd.command(name="risk")
async def account_risk(ctx, pct: float):
    cfg = set_risk_pct(pct)
    await ctx.send(f"Risk per trade set to {cfg['risk_pct']}%.")


@account_cmd.command(name="maxpositions")
async def account_maxpositions(ctx, n: int):
    cfg = set_max_open_positions(n)
    await ctx.send(f"Max concurrent open positions set to {cfg['max_open_positions']}.")
