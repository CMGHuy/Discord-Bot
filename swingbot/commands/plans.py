"""!liveplans -- live plan-lifecycle board over PlanStore (v2 plan engine).

Named `liveplans`, not `plans`: `!plans` already exists in history.py for
historical trade-plan lookup (ticker/date-range query against trades.json),
an unrelated pre-existing feature -- this is the intraday PENDING/ACTIVE/
PARTIAL board over the live PlanStore."""
import discord

from swingbot import config
from swingbot.bot_core import bot
from swingbot.core.analytics.rank import rank_plans
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core import presentation as ui
from swingbot.core.scanning.embeds import banked_leg_pct_and_amount, signed_money
from swingbot.commands.views import (
    starred_ids,
    paginate,
    PLAN_BOARD_PAGE_SIZE,
    PlanBoardView,
)

LIVE_STATUSES = ("PENDING", "ACTIVE", "PARTIAL")


def _partial_tail(plan) -> str:
    """The tail of a PARTIAL plan's board row: what was already banked,
    then the runner as a position of its own.

    Once TP1 has fired, the plan's own trigger_price/stop_loss/tp1 are
    stale history -- the money question is what's in the bank and where the
    remaining leg lives, so this replaces that tail rather than adding to
    it. Every figure that can't be computed is omitted, never shown as 0.
    Runner entry is the TP1 leg's actual fill price (which can differ from
    the tp1 level on a gap-through), falling back to plan.tp1 for a PARTIAL
    plan with no recorded leg -- the same defensive fallback
    embeds.partial_position_line() uses."""
    leg = plan.legs_realized[0] if plan.legs_realized else None
    bits = []
    if leg:
        pct, amount = banked_leg_pct_and_amount(plan, leg["exit_price"],
                                                leg["fraction"])
        banked = f"banked {ui.fmt_r(leg['r'])}"
        if pct is not None:
            banked += f"/{ui.fmt_pct(pct)}"
        if amount is not None:
            banked += f"/{signed_money(amount, config.CURRENCY_SYMBOL)}"
        bits.append(f"{banked} on {leg['fraction']:.0%}")

    runner_entry = leg["exit_price"] if leg else plan.tp1
    runner = f"runner entry {ui.fmt_price(runner_entry)}"
    if plan.working_stop is not None:
        runner += f" SL {ui.fmt_price(plan.working_stop)}"
    if plan.tp2 is not None:
        runner += f" TP2 {ui.fmt_price(plan.tp2)}"
    else:
        runner += f" TP1 (no TP2) {ui.fmt_price(plan.tp1)}"
    bits.append(runner)
    return " · ".join(bits)


def _plan_line(plan) -> str:
    from swingbot.core.analytics.rank import follow_score
    import datetime as dt

    star = "⭐" if plan.plan_id in starred_ids() else ""
    score = follow_score(plan, today=dt.date.today())
    direction_word = "LONG" if plan.direction == "bullish" else "SHORT"
    if plan.status == "PARTIAL":
        tail = _partial_tail(plan)
    else:
        tp2_bit = f" TP2 {ui.fmt_price(plan.tp2)}" if plan.tp2 is not None else ""
        tail = (f"entry {ui.fmt_price(plan.trigger_price)} SL {ui.fmt_price(plan.stop_loss)} "
                f"TP1 {ui.fmt_price(plan.tp1)}{tp2_bit}")
    return (
        f"{star}{ui.direction_glyph(plan.direction)} {plan.ticker} {direction_word} · "
        f"{plan.status} · follow {score:.0f} · {tail}"
    )


def render_board(plans: list, *, status: str, level: str, badge: str, page: int, ticker: str = None, today=None) -> tuple:
    """Pure renderer: a fixed list of TradePlanV2s (or v2-shaped stand-
    ins) in, (content_str, discord.Embed) out. Called directly by
    !liveplans (Task B15/B16) and as PlanBoardView's render_fn (Task B13).
    Filtering happens here, BEFORE ranking and BEFORE pagination, so
    the page count in the footer always reflects the filtered set, not
    the whole store.

    v32 Task 11: `tier` (A/B/C) filter retired in favour of `level` (1-5
    confidence level, the number that actually gates whether an alert
    fires). `level` is a string here (matches `status`/`badge`'s "All" or
    a literal value convention from the Discord command args), compared
    against `p.confidence_level` as an int."""
    live = [p for p in plans if p.status in LIVE_STATUSES]
    if status != "All":
        live = [p for p in live if p.status == status]
    if level != "All":
        live = [p for p in live if p.confidence_level == int(level)]
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
        f"📋 **Live plans** — {len(ranked)} match (status={status}, level={level}, badge={badge}), "
        f"page {page_num + 1}/{max_page + 1}\n\n{body}"
    )
    embed = discord.Embed(title="📋 Live Plans Board", description=content[:4000])
    accent_level = page_items[0].confidence_level if page_items else 3
    ui.apply_chrome(embed, accent=ui.accent_for_level(accent_level))
    return content, embed


_VALID_STATUSES = {"PENDING", "ACTIVE", "PARTIAL", "CLOSED", "CANCELLED", "ALL"}
_VALID_LEVELS = {"1", "2", "3", "4", "5"}
_VALID_BADGES = {"VALIDATED", "WEAK"}


def _parse_board_args(args: tuple) -> dict:
    """Case-insensitive board-mode arg parser for !liveplans."""
    parsed: dict = {}
    for token in args:
        tl = token.lower()
        if tl.startswith("level:"):
            val = tl[6:]
            if val in _VALID_LEVELS:
                parsed["level"] = val
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
    parsed_level = parsed.get("level", "All")
    parsed_badge = parsed.get("badge", "All")
    parsed_ticker = parsed.get("ticker")

    store = PlanStore()
    plans = store.open_plans()
    content, embed = render_board(
        plans, status=parsed_status, level=parsed_level, badge=parsed_badge, ticker=parsed_ticker, page=0,
    )
    view = PlanBoardView(
        render_fn=lambda status, level, badge: render_board(
            plans, status=status, level=level, badge=badge, ticker=parsed_ticker, page=0,
        ),
        author_id=ctx.author.id,
        items=plans,
    )
    view.message = await ctx.send(content=content, embed=embed, view=view)
