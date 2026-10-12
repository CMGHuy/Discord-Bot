"""!growth, !killswitch, !portfolio and their slash twins (Edge plan E2; v153).

Each command body lives in one handle_<name>(reply, ...) handler shared by
the prefix command and its /<name> slash twin (swingbot/commands/reply.py).
"""
import asyncio
import os
from datetime import date

import discord
from discord import app_commands
from discord.ext import commands

from swingbot import config
from swingbot.bot_core import bot
from swingbot.commands.reply import CtxReply, InteractionReply, send_prefix_tip
from swingbot.core import presentation as ui
from swingbot.core.planning import account as account_module
from swingbot.core.edge.growth import AVG_DAYS_PER_MONTH, growth_report, growth_path
from swingbot.core.tracking.performance import TradeLog
from swingbot.core.edge.portfolio_state import collect_portfolio_state as _collect_portfolio_state

MC_MIN_CLOSED_TRADES = 10   # below this a bootstrap R-multiple sample is noise


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

    # Monte Carlo fan (E70): bootstrap over the account's OWN closed-trade
    # R multiples -- soft, degrades to no chart (text report always posts)
    # below MC_MIN_CLOSED_TRADES, on any missing balance, or on any error.
    try:
        from swingbot.core.analytics.metrics import r_multiple as _r_multiple
        from swingbot.core.edge.ruin import simulate as _mc_simulate
        from swingbot.core.charts.portfolio_charts import render_mc_fan
        rs = [r for t in TradeLog().get_trades(limit=None, ledger="main")
              if (r := _r_multiple(t)) is not None]
        if len(rs) >= MC_MIN_CLOSED_TRADES and base:
            sim = _mc_simulate(rs, risk_pct=stats["risk_pct"], return_paths=True)
            stats["mc_chart_path"] = render_mc_fan(
                sim, base, config.EXPORT_DIR, percentile_paths=sim["percentile_paths"])
    except Exception:
        pass
    return stats


def _growth_path_line(gp: dict, target: float) -> str:
    on_track = gp["on_track_vs"].get(8, False)
    on_track_str = "yes" if on_track else "no"
    return (f"\nat {gp['current_multiple']:.2f}x — {ui.fmt_pct(gp['pct_to_target'])} of the way "
            f"(log scale) toward {target:g}x; on track for {target:g}x-in-8y: {on_track_str}")


async def handle_growth(reply, target: float = 10.0) -> None:
    """Show the honest math to <target>x at current expectancy/frequency."""
    if target <= 1:
        await reply.send_error(
            f"Target must be greater than 1x (got {target:g}x) -- a target of 1x or "
            "less means \"no growth needed\" or \"shrink\", which this dashboard doesn't model. "
            "Try e.g. `!growth 10`."
        )
        return
    await reply.defer()
    stats = await asyncio.to_thread(_collect_stats, target)
    report = growth_report(stats, target=target)
    gp = stats.get("growth_path")
    if gp and gp.get("realized_daily_growth") is not None:
        report += _growth_path_line(gp, target)
    chart_path = stats.get("mc_chart_path")
    file = discord.File(chart_path, filename=os.path.basename(chart_path)) if chart_path else None
    await reply.send(f"```\n{report}\n```", file=file)


async def handle_killswitch(reply, action: str = "status") -> None:
    """on|off|status — hard pause for all new entries."""
    from swingbot.core.edge import throttle
    if action == "status":
        st = throttle.kill_state()
        await reply.send(f"kill switch: {'🔴 ON — ' + str(st['reason']) if st['on'] else '🟢 off'}")
        return
    st = throttle.set_kill(action == "on", reason="manual")
    await reply.send(f"kill switch {'engaged 🔴 — no new entries' if st['on'] else 'released 🟢'}")


@bot.command(name="growth")
async def growth_command(ctx, target: float = 10.0):
    """Show the honest math to <target>x at current expectancy/frequency."""
    reply = CtxReply(ctx)
    await handle_growth(reply, target)
    await send_prefix_tip(ctx, reply)


@bot.command(name="killswitch")
@commands.has_permissions(administrator=True)
async def killswitch_command(ctx, action: str = "status"):
    """!killswitch on|off|status — hard pause for all new entries."""
    reply = CtxReply(ctx)
    await handle_killswitch(reply, action)
    await send_prefix_tip(ctx, reply)


def portfolio_report(state: dict) -> str:
    """Survival dashboard: heat, sectors, clusters, throttle, kill, growth."""
    lines = ["PORTFOLIO SURVIVAL DASHBOARD"]
    if state.get("kill", {}).get("on"):
        lines.append(f"🔴 KILL SWITCH ON — {state['kill'].get('reason')} — no new entries")
    lines.append(f"heat: {ui.fmt_pct(state.get('open_heat', 0.0))} / {ui.fmt_pct(state.get('heat_cap', 6.0))} cap")
    for sec, h in sorted(state.get("sector_heat", {}).items(), key=lambda kv: -kv[1]):
        bar = "█" * int(round(h * 4))
        lines.append(f"  {sec:<24} {ui.fmt_pct(h)} {bar}")
    for cluster in state.get("clusters", []):
        lines.append(f"  ⚠ correlated cluster: {', '.join(cluster)}")
    mult = state.get("throttle_mult", 1.0)
    lines.append(f"throttle: x{mult:.2f}" + (" (PAUSED)" if state.get("paused") else ""))
    g = state.get("growth") or {}
    if g:
        lines.append(f"growth path: {g.get('current_multiple', 1.0):.2f}x — "
                     f"{ui.fmt_pct(g.get('pct_to_target', 0.0))} of the way to 10x (log scale)")
    lines.append("Projections from backtests/paper — real results will differ.")
    return "\n".join(lines)


async def handle_portfolio(reply) -> None:
    """Open heat vs cap, sector bars, clusters, throttle + kill state."""
    await reply.defer()
    state = await asyncio.to_thread(_collect_portfolio_state)
    await reply.send(f"```\n{portfolio_report(state)}\n```")


@bot.command(name="portfolio")
async def portfolio_command(ctx):
    """Open heat vs cap, sector bars, clusters, throttle + kill state."""
    reply = CtxReply(ctx)
    await handle_portfolio(reply)
    await send_prefix_tip(ctx, reply)


def weekly_risk_report(week_stats: dict) -> str:
    mc = week_stats.get("mc") or {}
    cluster = week_stats.get("biggest_cluster") or []
    util = week_stats.get("heat_utilization_pct")
    lines = [
        "🛡️ WEEKLY RISK REPORT",
        f"heat utilization: {ui.fmt_pct(util)} of cap" if util is not None else "heat utilization: n/a",
        f"biggest correlated cluster: {', '.join(cluster) if cluster else 'none'}",
        f"throttle activations: {week_stats.get('throttle_activations', 0)}",
    ]
    if mc:
        lines.append(
            "Monte Carlo (updated R history): "
            f"p95 drawdown {ui.fmt_pct(mc['max_dd_p95'] * 100)}, "
            f"p(halve) {ui.fmt_pct(mc['p_ruin'] * 100)}, "
            f"p(10x within 1000 trades) {ui.fmt_pct(mc['p_10x'] * 100)}"
        )
    gd = week_stats.get("growth_delta")
    if gd is not None:
        lines.append(f"growth path this week: {ui.fmt_pct(gd * 100)}")
    lines.append("Projections, not promises.")
    return "\n".join(lines)


def rs_rotation_report(rels: dict, sectors: dict, top_n: int = 10) -> str:
    ranked = sorted(((r, s) for s, r in rels.items() if r is not None), reverse=True)
    lines = ["📈 RS ROTATION — universe leaders / laggards (63d vs SPY)"]
    lines += [f"  {s:<6} {ui.fmt_pct(r * 100)}" for r, s in ranked[:top_n]]
    lines.append("  …")
    lines += [f"  {s:<6} {ui.fmt_pct(r * 100)}" for r, s in ranked[-top_n:]]
    by_sector: dict = {}
    for sym, r in rels.items():
        sec = sectors.get(sym)
        if sec and r is not None:
            by_sector.setdefault(sec, []).append(r)
    lines.append("sector tide:")
    for sec, rs in sorted(by_sector.items(), key=lambda kv: -sum(kv[1]) / len(kv[1])):
        lines.append(f"  {sec:<26} {ui.fmt_pct(sum(rs) / len(rs) * 100)} (n={len(rs)})")
    return "\n".join(lines)


# ──────────────────────────────────────────────
# / slash twins (new in v153)
# ──────────────────────────────────────────────

KILLSWITCH_CHOICES = [
    app_commands.Choice(name="status", value="status"),
    app_commands.Choice(name="on — block all new entries", value="on"),
    app_commands.Choice(name="off — release the kill switch", value="off"),
]


@bot.tree.command(name="growth", description="The honest math to a target multiple at current expectancy and frequency")
@app_commands.describe(target="Target account multiple, above 1 (default 10)")
async def slash_growth(interaction: discord.Interaction, target: float = 10.0):
    await handle_growth(InteractionReply(interaction), target)


# Mirrors !killswitch's runtime check, not just its visibility (spec,
# "Grouping and permissions"): hidden from non-admins in the picker,
# enforced at invocation, and unavailable in DMs where no administrator
# permission exists. SP3's bot.tree.error handler answers the check failures.
@bot.tree.command(name="killswitch", description="Hard pause for all new entries (administrators only)")
@app_commands.describe(action="status (default), on or off")
@app_commands.choices(action=KILLSWITCH_CHOICES)
@app_commands.default_permissions(administrator=True)
@app_commands.checks.has_permissions(administrator=True)
@app_commands.guild_only()
async def slash_killswitch(interaction: discord.Interaction, action: app_commands.Choice[str] = None):
    await handle_killswitch(InteractionReply(interaction), action.value if action else "status")


@bot.tree.command(name="portfolio", description="Open heat vs cap, sector heat, correlated clusters, throttle and kill state")
async def slash_portfolio(interaction: discord.Interaction):
    await handle_portfolio(InteractionReply(interaction))
