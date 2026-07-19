"""!top, !stats, !lessons, !calibration, !journal -- the analytics-facing
command surface. Every number here is read from a Plan A function or
the analytics snapshot; nothing in this module computes a stat from
raw trades itself (see this Part's Global Constraints)."""
import datetime as dt
import types

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
