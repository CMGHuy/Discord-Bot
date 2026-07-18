"""!liveplans -- live plan-lifecycle board over PlanStore (v2 plan engine).

Named `liveplans`, not `plans`: `!plans` already exists in history.py for
historical trade-plan lookup (ticker/date-range query against trades.json),
an unrelated pre-existing feature -- this is the intraday PENDING/ACTIVE/
PARTIAL board over the live PlanStore."""
from swingbot.bot_core import bot
from swingbot.core.plan_engine import PlanStatus
from swingbot.core.plan_store import PlanStore


def format_plans_board(plans, prices=None) -> str:
    prices = prices or {}
    if not plans:
        return "No live v2 plans."
    groups = {PlanStatus.PENDING: [], PlanStatus.ACTIVE: [], PlanStatus.PARTIAL: []}
    for p in plans:
        if p.status in groups:
            groups[p.status].append(p)

    lines = ["📋 **Live plans — Plan Engine v2**"]
    for status, rows in groups.items():
        if not rows:
            continue
        lines.append(f"**{status}** ({len(rows)})")
        for p in rows:
            icon = "✅" if p.badge == "VALIDATED" else "⚠️"
            if status == PlanStatus.PENDING:
                lines.append(f"{icon} `{p.ticker}` {p.direction} — "
                             f"trigger {p.trigger_price:.2f}, "
                             f"expires after {p.expiry_bars} bars")
            elif status == PlanStatus.ACTIVE:
                stop = p.working_stop if p.working_stop is not None else p.stop_loss
                extra = ""
                live = prices.get(p.ticker)
                if live:
                    extra = f", {abs(p.tp1 - live) / live * 100:.1f}% to TP1"
                lines.append(f"{icon} `{p.ticker}` {p.direction} — "
                             f"entry {p.entry_price:.2f}, stop {stop:.2f}{extra}")
            else:  # PARTIAL
                leg = p.legs_realized[0] if p.legs_realized else None
                banked = (f"banked {leg['r']:+.2f}R on {leg['fraction']:.0%}"
                          if leg else "banked")
                lines.append(f"{icon} `{p.ticker}` {p.direction} — {banked}, "
                             f"trail {p.working_stop:.2f}")
    return "\n".join(lines)


@bot.command(name="liveplans")
async def liveplans_cmd(ctx):
    store = PlanStore()
    await ctx.send(format_plans_board(store.open_plans())[:1990])
