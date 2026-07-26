"""!growth — the compounding reality dashboard (Edge plan E2)."""
import asyncio
from datetime import date

from discord.ext import commands

from swingbot.bot_core import bot
from swingbot.core import account as account_module
from swingbot.core.edge.growth import AVG_DAYS_PER_MONTH, growth_report, growth_path


def _collect_stats(target: float = 10.0) -> dict:
    stats = {}
    try:
        from swingbot.core.analytics.snapshots import load_snapshot
        snap = load_snapshot() or {}
        overall = snap.get("overall", {})
        stats["expectancy_r"] = overall.get("expectancy_r")
        stats["n_closed"] = overall.get("n", 0)

        # No stored "trades per month" stat exists -- derive one from the
        # equity curve's own per-close points (each point after the
        # baseline corresponds to one closed trade, dated by close day).
        points = (snap.get("equity_curve") or {}).get("points", [])
        trade_points = points[1:] if len(points) > 1 else []
        if len(trade_points) >= 2:
            first = date.fromisoformat(trade_points[0]["date"])
            last = date.fromisoformat(trade_points[-1]["date"])
            elapsed_months = max((last - first).days, 1) / AVG_DAYS_PER_MONTH
            stats["trades_per_month"] = len(trade_points) / elapsed_months
    except Exception:  # analytics not merged yet / snapshot stale — degrade
        pass
    cfg = account_module.load_account_config()
    stats["risk_pct"] = cfg.get("risk_pct", 1.0)
    base = cfg.get("base_balance")
    if base:
        stats["current_multiple"] = cfg.get("balance", base) / base
        stats["growth_path"] = growth_path(
            account_module.get_balance_history_points(), base, target_multiple=target)
    return stats


@bot.command(name="growth")
async def growth_command(ctx, target: float = 10.0):
    """Show the honest math to <target>x at current expectancy/frequency."""
    if target <= 1:
        await ctx.send(
            f"Target must be greater than 1x (got {target:g}x) -- a target of 1x or "
            "less means \"no growth needed\" or \"shrink\", which this dashboard doesn't model. "
            "Try e.g. `!growth 10`."
        )
        return
    stats = await asyncio.to_thread(_collect_stats, target)
    report = growth_report(stats, target=target)
    gp = stats.get("growth_path")
    if gp and gp.get("realized_daily_growth") is not None:
        on_track = gp["on_track_vs"].get(8, False)
        on_track_str = "yes" if on_track else "no"
        report += (f"\nat {gp['current_multiple']:.2f}x — {gp['pct_to_target']:.1f}% of the way "
                   f"(log scale) toward {target:g}x; on track for {target:g}x-in-8y: {on_track_str}")
    await ctx.send(f"```\n{report}\n```")


@bot.command(name="killswitch")
@commands.has_permissions(administrator=True)
async def killswitch_command(ctx, action: str = "status"):
    """!killswitch on|off|status — hard pause for all new entries."""
    from swingbot.core.edge import throttle
    if action == "status":
        st = throttle.kill_state()
        await ctx.send(f"kill switch: {'🔴 ON — ' + str(st['reason']) if st['on'] else '🟢 off'}")
        return
    st = throttle.set_kill(action == "on", reason="manual")
    await ctx.send(f"kill switch {'engaged 🔴 — no new entries' if st['on'] else 'released 🟢'}")
