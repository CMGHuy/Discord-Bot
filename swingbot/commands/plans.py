"""!liveplans -- live plan-lifecycle board over PlanStore (v2 plan engine).

Named `liveplans`, not `plans`: `!plans` already exists in history.py for
historical trade-plan lookup (ticker/date-range query against trades.json),
an unrelated pre-existing feature -- this is the intraday PENDING/ACTIVE/
PARTIAL board over the live PlanStore."""
import discord

from swingbot.bot_core import bot
from swingbot.core.analytics.rank import rank_plans
from swingbot.core.plan_engine import PlanStatus
from swingbot.core.plan_store import PlanStore
from swingbot.core.scanning import embed_theme as theme
from swingbot.commands.views import (
    starred_ids,
    paginate,
    PLAN_BOARD_PAGE_SIZE,
    PlanBoardView,
)


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


LIVE_STATUSES = ("PENDING", "ACTIVE", "PARTIAL")


def _plan_line(plan) -> str:
    from swingbot.core.analytics.rank import follow_score
    import datetime as dt

    star = "⭐" if plan.plan_id in starred_ids() else ""
    score = follow_score(plan, today=dt.date.today())
    direction_word = "LONG" if plan.direction == "bullish" else "SHORT"
    tp2_bit = f" TP2 {plan.tp2:.2f}" if plan.tp2 is not None else ""
    return (
        f"{star}{theme.tier_chip(plan.tier)}{theme.badge_chip(plan.badge)} {plan.ticker} {direction_word} · "
        f"{plan.status} · follow {score:.0f} · entry {plan.trigger_price:.2f} SL {plan.stop_loss:.2f} "
        f"TP1 {plan.tp1:.2f}{tp2_bit}"
    )


def render_board(plans: list, *, status: str, tier: str, badge: str, page: int, ticker: str = None, today=None) -> tuple:
    """Pure renderer: a fixed list of TradePlanV2s (or v2-shaped stand-
    ins) in, (content_str, discord.Embed) out. Called directly by
    !liveplans (Task B15/B16) and as PlanBoardView's render_fn (Task B13).
    Filtering happens here, BEFORE ranking and BEFORE pagination, so
    the page count in the footer always reflects the filtered set, not
    the whole store."""
    live = [p for p in plans if p.status in LIVE_STATUSES]
    if status != "All":
        live = [p for p in live if p.status == status]
    if tier != "All":
        live = [p for p in live if p.tier == tier]
    if badge != "All":
        live = [p for p in live if p.badge == badge]
    if ticker:
        live = [p for p in live if p.ticker == ticker]

    ranked = rank_plans(live, today=today)
    starred = starred_ids()
    from swingbot.core.analytics.rank import follow_score
    import datetime as _dt
    _today = today or _dt.date.today()
    ranked.sort(key=lambda p: (-round(follow_score(p, today=_today)), p.plan_id not in starred))

    page_items, page_num, max_page = paginate(ranked, page, PLAN_BOARD_PAGE_SIZE)

    lines_by_status: dict = {s: [] for s in LIVE_STATUSES}
    for p in page_items:
        lines_by_status[p.status].append(_plan_line(p))

    body_parts = []
    for s in LIVE_STATUSES:
        if lines_by_status[s]:
            body_parts.append(f"**{s}**\n" + "\n".join(lines_by_status[s]))
    body = "\n\n".join(body_parts) if body_parts else "No live plans match this filter."

    content = (
        f"📋 **Live plans** — {len(ranked)} match (status={status}, tier={tier}, badge={badge}), "
        f"page {page_num + 1}/{max_page + 1}\n\n{body}"
    )
    embed = discord.Embed(
        title="📋 Live Plans Board", description=content[:4000],
        color=discord.Color.blurple(),
    )
    return content, embed


_VALID_STATUSES = {"PENDING", "ACTIVE", "PARTIAL", "CLOSED", "CANCELLED", "ALL"}
_VALID_TIERS = {"A", "B", "C"}
_VALID_BADGES = {"VALIDATED", "WEAK"}


def _parse_board_args(args: tuple) -> dict:
    """Case-insensitive board-mode arg parser for !liveplans."""
    parsed: dict = {}
    for token in args:
        tl = token.lower()
        if tl.startswith("tier:"):
            val = tl[5:].upper()
            if val in _VALID_TIERS:
                parsed["tier"] = val
            continue
        if tl.startswith("badge:"):
            val = tl[6:].upper()
            if val in _VALID_BADGES:
                parsed["badge"] = val
            continue
        if tl.upper() in _VALID_STATUSES and tl.upper() != "ALL":
            parsed["status"] = tl.upper()
            continue
        parsed["ticker"] = token.upper()
    return parsed


@bot.command(name="liveplans")
async def liveplans_cmd(ctx, *args: str):
    parsed = _parse_board_args(args)
    parsed_status = parsed.get("status", "All")
    parsed_tier = parsed.get("tier", "All")
    parsed_badge = parsed.get("badge", "All")
    parsed_ticker = parsed.get("ticker")

    store = PlanStore()
    plans = store.open_plans()
    content, embed = render_board(
        plans, status=parsed_status, tier=parsed_tier, badge=parsed_badge, ticker=parsed_ticker, page=0,
    )
    view = PlanBoardView(
        render_fn=lambda status, tier, badge: render_board(
            plans, status=status, tier=tier, badge=badge, ticker=parsed_ticker, page=0,
        ),
        author_id=ctx.author.id,
        items=plans,
    )
    view.message = await ctx.send(content=content, embed=embed, view=view)
