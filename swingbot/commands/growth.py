"""!growth — the compounding reality dashboard (Edge plan E2)."""
import asyncio
import os
from datetime import date

import discord
from discord.ext import commands

from swingbot import config
from swingbot.bot_core import bot
from swingbot.core import account as account_module
from swingbot.core.edge.growth import AVG_DAYS_PER_MONTH, growth_report, growth_path
from swingbot.core.performance import TradeLog

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
        rs = [r for t in TradeLog().get_trades(limit=None)
              if (r := _r_multiple(t)) is not None]
        if len(rs) >= MC_MIN_CLOSED_TRADES and base:
            sim = _mc_simulate(rs, risk_pct=stats["risk_pct"], return_paths=True)
            stats["mc_chart_path"] = render_mc_fan(
                sim, base, config.EXPORT_DIR, percentile_paths=sim["percentile_paths"])
    except Exception:
        pass
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
    chart_path = stats.get("mc_chart_path")
    file = discord.File(chart_path, filename=os.path.basename(chart_path)) if chart_path else None
    await ctx.send(f"```\n{report}\n```", file=file)


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


def _collect_portfolio_state() -> dict:
    """Assemble the !portfolio survival-dashboard state from the E7/E8/E45/
    E47/E9 accessors over the open-trade list. Mirrors _collect_stats's
    soft-import style: every sub-collector try/excepted to a safe default
    so a missing/broken piece never kills the whole command."""
    from swingbot.core.edge import correlation, heat, throttle
    from swingbot.core.data import get_daily_data
    from swingbot.core import universe

    state: dict = {}

    try:
        cfg = account_module.load_account_config()
        balance = cfg.get("balance", cfg.get("base_balance", 0.0))
    except Exception:
        cfg = {}
        balance = 0.0

    open_trades: list = []
    try:
        open_trades = TradeLog().get_trades(status="open", limit=None)
    except Exception:
        open_trades = []

    try:
        state["open_heat"] = heat.open_heat(open_trades, balance)
    except Exception:
        state["open_heat"] = 0.0
    state["heat_cap"] = getattr(config, "PORTFOLIO_HEAT_CAP_PCT", 6.0)

    sectors: dict = {}
    try:
        sectors = universe.sector_map(getattr(config, "SCAN_UNIVERSE", "watchlist") or "watchlist")
    except Exception:
        sectors = {}

    try:
        state["sector_heat"] = heat.sector_heat(open_trades, balance, sectors)
    except Exception:
        state["sector_heat"] = {}

    try:
        equity_points = [bal for _, bal in account_module.get_balance_history_points()]
        mult, paused = throttle.current_throttle(equity_points, was_paused=False)
        state["throttle_mult"] = mult
        state["paused"] = paused
    except Exception:
        state["throttle_mult"] = 1.0
        state["paused"] = False

    try:
        state["kill"] = throttle.kill_state()
    except Exception:
        state["kill"] = {"on": False, "reason": None}

    try:
        base = cfg.get("base_balance")
        if base:
            state["growth"] = growth_path(
                account_module.get_balance_history_points(), base, target_multiple=10.0)
        else:
            state["growth"] = {}
    except Exception:
        state["growth"] = {}

    try:
        clusters: list = []
        tickers = sorted({t.get("ticker") for t in open_trades if t.get("ticker")})
        dfs: dict = {}
        for ticker in tickers:
            try:
                dfs[ticker] = get_daily_data(ticker)
            except Exception:
                continue
        seen: set = set()
        for ticker in tickers:
            result = correlation.cluster_exposure(
                open_trades, ticker, dfs, balance, sectors=sectors)
            cluster = result.get("cluster") or []
            if not cluster:
                continue
            group = frozenset({ticker}) | frozenset(cluster)
            if len(group) < 2 or group in seen:
                continue
            seen.add(group)
            clusters.append(sorted(group))
        state["clusters"] = clusters
    except Exception:
        state["clusters"] = []

    return state


def portfolio_report(state: dict) -> str:
    """Survival dashboard: heat, sectors, clusters, throttle, kill, growth."""
    lines = ["PORTFOLIO SURVIVAL DASHBOARD"]
    if state.get("kill", {}).get("on"):
        lines.append(f"🔴 KILL SWITCH ON — {state['kill'].get('reason')} — no new entries")
    lines.append(f"heat: {state.get('open_heat', 0.0):.1f}% / {state.get('heat_cap', 6.0):.1f}% cap")
    for sec, h in sorted(state.get("sector_heat", {}).items(), key=lambda kv: -kv[1]):
        bar = "█" * int(round(h * 4))
        lines.append(f"  {sec:<24} {h:.1f}% {bar}")
    for cluster in state.get("clusters", []):
        lines.append(f"  ⚠ correlated cluster: {', '.join(cluster)}")
    mult = state.get("throttle_mult", 1.0)
    lines.append(f"throttle: x{mult:.2f}" + (" (PAUSED)" if state.get("paused") else ""))
    g = state.get("growth") or {}
    if g:
        lines.append(f"growth path: {g.get('current_multiple', 1.0):.2f}x — "
                     f"{g.get('pct_to_target', 0.0):.1f}% of the way to 10x (log scale)")
    lines.append("Projections from backtests/paper — real results will differ.")
    return "\n".join(lines)


@bot.command(name="portfolio")
async def portfolio_command(ctx):
    """Open heat vs cap, sector bars, clusters, throttle + kill state."""
    state = await asyncio.to_thread(_collect_portfolio_state)
    await ctx.send(f"```\n{portfolio_report(state)}\n```")


def weekly_risk_report(week_stats: dict) -> str:
    mc = week_stats.get("mc") or {}
    cluster = week_stats.get("biggest_cluster") or []
    util = week_stats.get("heat_utilization_pct")
    lines = [
        "🛡️ WEEKLY RISK REPORT",
        f"heat utilization: {util:.0f}% of cap" if util is not None else "heat utilization: n/a",
        f"biggest correlated cluster: {', '.join(cluster) if cluster else 'none'}",
        f"throttle activations: {week_stats.get('throttle_activations', 0)}",
    ]
    if mc:
        lines.append(f"Monte Carlo (updated R history): p95 drawdown {mc['max_dd_p95']:.0%}, "
                     f"p(halve) {mc['p_ruin']:.1%}, p(10x within 1000 trades) {mc['p_10x']:.0%}")
    gd = week_stats.get("growth_delta")
    if gd is not None:
        lines.append(f"growth path this week: {gd:+.1%}")
    lines.append("Projections, not promises.")
    return "\n".join(lines)


def rs_rotation_report(rels: dict, sectors: dict, top_n: int = 10) -> str:
    ranked = sorted(((r, s) for s, r in rels.items() if r is not None), reverse=True)
    lines = ["📈 RS ROTATION — universe leaders / laggards (63d vs SPY)"]
    lines += [f"  {s:<6} {r:+.1%}" for r, s in ranked[:top_n]]
    lines.append("  …")
    lines += [f"  {s:<6} {r:+.1%}" for r, s in ranked[-top_n:]]
    by_sector: dict = {}
    for sym, r in rels.items():
        sec = sectors.get(sym)
        if sec and r is not None:
            by_sector.setdefault(sec, []).append(r)
    lines.append("sector tide:")
    for sec, rs in sorted(by_sector.items(), key=lambda kv: -sum(kv[1]) / len(kv[1])):
        lines.append(f"  {sec:<26} {sum(rs) / len(rs):+.1%} (n={len(rs)})")
    return "\n".join(lines)
