"""!growth — the compounding reality dashboard (Edge plan E2)."""
import asyncio
from datetime import date

from discord.ext import commands

from swingbot import config
from swingbot.bot_core import bot
from swingbot.core import account as account_module
from swingbot.core.edge.growth import AVG_DAYS_PER_MONTH, growth_report, growth_path
from swingbot.core.performance import TradeLog


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


def _collect_portfolio_state() -> dict:
    """Assemble the !portfolio survival-dashboard state from the E7/E8/E45/
    E47/E9 accessors over the open-trade list. Mirrors _collect_stats's
    soft-import style: every sub-collector try/excepted to a safe default
    so a missing/broken piece never kills the whole command."""
    from swingbot.core.edge import correlation, heat, throttle
    from swingbot.core.data import get_daily_data
    from swingbot.core import universe

    state: dict = {}

    cfg = account_module.load_account_config()
    balance = cfg.get("balance", cfg.get("base_balance", 0.0))

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
