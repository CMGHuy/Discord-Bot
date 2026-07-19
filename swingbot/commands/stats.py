"""!top, !stats, !lessons, !calibration, !journal -- the analytics-facing
command surface. Every number here is read from a Plan A function or
the analytics snapshot; nothing in this module computes a stat from
raw trades itself (see this Part's Global Constraints)."""
import datetime as dt
import types

import discord

from swingbot import config
from swingbot.bot_core import bot
from swingbot.core.analytics.rank import rank_plans
from swingbot.core.plan_store import PlanStore
from swingbot.commands.views import PlanActionView
from swingbot.core.scanning.embeds import build_embed

_plan_store = PlanStore()

LIVE_STATUSES = ("PENDING", "ACTIVE")


def top_plans(plans: list, n: int, today=None) -> list:
    """The n highest-follow_score PENDING/ACTIVE plans, ranked by
    analytics.rank.rank_plans (the one shared ordering -- see this
    Part's Global Constraints). Shared between !top (this task) and
    the daily digest (Task B37) so both ever answer "what's worth
    following right now" identically."""
    eligible = [p for p in plans if p.status in LIVE_STATUSES]
    ranked = rank_plans(eligible, today=today)
    return ranked[:max(0, n)]


def _fake_item_from_plan(plan):
    """Bridges a bare TradePlanV2 (as returned by PlanStore, with no
    ScanItem context -- there was no live scan producing this !top
    listing) into the shape build_embed expects. build_embed reads
    TWO separate plan slots on `item`: `item.plan` (the legacy
    scenario-shaped object _build_trade_plan_table's numbers come
    from -- entry/stop_loss/take_profit/target2_price/*_distance_pct/
    risk_reward_ratio/target_sources/stop_sources) and `item.plan_v2`
    (the real TradePlanV2, read by _v2_plan() for tier/badge theming,
    the quality section, and the follow-score field). There is no
    confluence/HTF context outside a live scan, so target_sources/
    stop_sources are empty (_sources_str renders "n/a" for an empty
    list, no crash) and the legacy numbers are derived directly from
    this same plan's own entry/stop/tp1/tp2 -- they describe the
    identical trade, just in the older field-name shape the table
    renderer still expects."""
    entry = plan.entry_price if plan.entry_price is not None else plan.trigger_price
    stop_loss = plan.stop_loss
    take_profit = plan.tp1
    target2 = plan.tp2
    risk = abs(entry - stop_loss)
    stop_distance_pct = (risk / entry * 100) if entry else 0.0
    target_distance_pct = (abs(take_profit - entry) / entry * 100) if entry else 0.0
    target2_distance_pct = (
        abs(target2 - entry) / entry * 100 if (target2 is not None and entry) else None
    )
    risk_reward_ratio = round(abs(take_profit - entry) / risk, 2) if risk else 0.0

    legacy_plan = types.SimpleNamespace(
        entry=entry, stop_loss=stop_loss, take_profit=take_profit, target2_price=target2,
        target_sources=[], stop_sources=[],
        risk_reward_ratio=risk_reward_ratio, stop_distance_pct=stop_distance_pct,
        target_distance_pct=target_distance_pct, target2_distance_pct=target2_distance_pct,
    )
    return types.SimpleNamespace(
        result=types.SimpleNamespace(ticker=plan.ticker, trend=plan.direction,
                                     strategy=plan.strategy, horizon_key=plan.horizon_key,
                                     horizon_label=plan.horizon_key),
        plan=legacy_plan, plan_v2=plan,
        conf=types.SimpleNamespace(level=3, label="n/a", score=0),
        requirements=[], combined_from=[{"strategy": plan.strategy, "horizon_key": plan.horizon_key}],
        all_requirements_met=True, htf_info=None,
    )


@bot.command(name="top")
async def top_cmd(ctx, n: int = None):
    n = n or config.DIGEST_MAX_PLANS
    plans = _plan_store.all()
    top = top_plans(plans, n, today=dt.date.today())
    if not top:
        await ctx.send("No PENDING/ACTIVE plans right now.")
        return

    await ctx.send(f"📌 **Top {len(top)} plan(s) by follow score:**")
    for plan in top:
        item = _fake_item_from_plan(plan)
        embed = build_embed(item, "", {"closed": 0}, None, None, layout="compact")
        view = PlanActionView(plan.plan_id, author_id=ctx.author.id)
        view.message = await ctx.send(embed=embed, view=view)


def _dash(x, fmt="{:.1f}"):
    return fmt.format(x) if x is not None else "—"


def _mini_table(rows: list, cols=("key", "n", "win_rate", "expectancy_r")) -> str:
    headers = {"key": "Group", "n": "N", "win_rate": "WR%", "expectancy_r": "ExpR"}
    header_line = " ".join(f"{headers[c]:>8s}" for c in cols)
    lines = [header_line]
    for row in rows:
        cells = []
        for c in cols:
            v = row.get(c)
            if c == "key":
                cells.append(f"{str(v):>8s}")
            elif c == "win_rate":
                cells.append(f"{_dash(v, '{:.1f}%'):>8s}")
            elif c == "expectancy_r":
                cells.append(f"{_dash(v, '{:+.2f}'):>8s}")
            else:
                cells.append(f"{v:>8}")
        lines.append(" ".join(cells))
    return "```\n" + "\n".join(lines) + "\n```"


def stats_embed(snap: dict) -> discord.Embed:
    o = snap["overall"]
    embed = discord.Embed(
        title="📐 Analytics — overall performance",
        description=(
            f"**N** {o['n']} ({o['wins']}W/{o['losses']}L)  ·  **Win rate** {_dash(o['win_rate'], '{:.1f}%')}  ·  "
            f"**Expectancy** {_dash(o['expectancy_r'], '{:+.3f}')}R  ·  **Profit factor** {_dash(o['profit_factor'], '{:.2f}')}\n"
            f"**Sharpe** {_dash(o['sharpe'], '{:.2f}')}  ·  **Sortino** {_dash(o['sortino'], '{:.2f}')}  ·  "
            f"**Max DD** {_dash(o['max_drawdown_pct'], '{:.1f}%')}  ·  **Total P&L** {o['total_pnl']:+.2f}"
        ),
        color=discord.Color.blurple(),
    )
    streak = o["streaks"]
    streak_word = streak["current_kind"] or "none"
    embed.add_field(name="🔥 Current streak", value=f"{streak['current']} {streak_word} "
                     f"(best win streak {streak['best_win_streak']}, worst loss streak {streak['worst_loss_streak']})",
                     inline=False)

    tier_rows = snap["by"].get("tier", [])
    if tier_rows:
        embed.add_field(name="By tier", value=_mini_table(tier_rows), inline=False)

    strat_rows = sorted(snap["by"].get("strategy", []), key=lambda r: r["n"], reverse=True)[:5]
    if strat_rows:
        embed.add_field(name="By strategy (top 5 by N)", value=_mini_table(strat_rows), inline=False)

    embed.set_footer(text=f"Snapshot built {snap['built_at']}")
    return embed


def _since(period: str, today: dt.date) -> "dt.date | None":
    """Start date for a !stats period filter. 'all' (and anything
    unrecognized -- degrade gracefully, never raise on a typo'd
    argument) means no filter at all: None."""
    if period == "7d":
        return today - dt.timedelta(days=7)
    if period == "30d":
        return today - dt.timedelta(days=30)
    if period == "90d":
        return today - dt.timedelta(days=90)
    if period == "ytd":
        return dt.date(today.year, 1, 1)
    return None


@bot.command(name="stats")
async def stats_cmd(ctx, period: str = "all"):
    period = period.lower()
    if period == "all":
        from swingbot.core.analytics.snapshots import load_snapshot, refresh_snapshot
        import asyncio

        snap = load_snapshot()
        if snap is None:
            await asyncio.to_thread(refresh_snapshot)
            snap = load_snapshot()
        if snap is None:
            await ctx.send("No analytics snapshot available yet — not enough closed trades, or the snapshot build failed. Check logs.")
            return
        await ctx.send(embed=stats_embed(snap))
        return

    since = _since(period, dt.date.today())
    if since is None:
        await ctx.send(f"Unrecognized period `{period}`. Use one of: 7d, 30d, 90d, ytd, all.")
        return

    from swingbot.core.scanning import engine as scan_engine
    from swingbot.core.analytics import metrics as m

    all_trades = scan_engine.trade_log.get_trades(status="all", limit=None)
    closed = [t for t in all_trades if t.get("status") in ("win", "loss")
             and t.get("closed_at", "")[:10] >= since.isoformat()]
    if not closed:
        await ctx.send(f"No closed trades in the last `{period}` window.")
        return

    embed = discord.Embed(
        title=f"📐 Analytics — last {period}",
        description=(
            f"**N** {len(closed)}  ·  **Win rate** {_dash(m.win_rate(closed), '{:.1f}%')}  ·  "
            f"**Expectancy** {_dash(m.expectancy_r(closed), '{:+.3f}')}R  ·  "
            f"**Profit factor** {_dash(m.profit_factor(closed), '{:.2f}')}"
        ),
        color=discord.Color.blurple(),
    )
    await ctx.send(embed=embed)
