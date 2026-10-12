"""
Interactive discord.ui.View subclasses for the plan-centric UX: a
per-alert action panel (chart / breakdown / watch / dismiss buttons --
PlanActionView) and the filterable/paginated !plans board (PlanBoardView).

v152 D2: the plan panel is persistent. Each of its buttons is a
discord.ui.DynamicItem whose custom_id carries the plan id (plus the author
id for an author-locked `!top` panel), registered once in bot_core's
setup_hook, so a press on an alert posted before a restart still works.
LegacyPlanPanel answers the static ids pre-v152 alerts carry. PlanBoardView
keeps the TradesPaginator author-lock / timeout pattern
(swingbot/commands/trades.py:83).
"""
import asyncio
import datetime as dt
import logging
import os
import re

import discord

from swingbot import config
from swingbot.core import presentation as ui
from swingbot.core.marketdata.data import get_currency_symbol, get_daily_data
from swingbot.core.charts.trade_chart import DEFAULT_TRENDLINE_LOOKBACK_DAYS, generate_trade_chart
from swingbot.core.backtesting.registry import decay_for, decay_note
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.planning.plan_types import PlanStatus
from swingbot.core.market.strategy import HORIZONS
from swingbot.core.market.session import market_today, nyse_calendar

log = logging.getLogger(__name__)

_plan_store = PlanStore()

def starred_ids() -> set:
    from swingbot.core.db.repositories.starred import starred_repo
    return starred_repo().ids()


def star_plan(plan_id: str) -> None:
    from swingbot.core.db.repositories.starred import starred_repo
    starred_repo().star(plan_id)


def unstar_plan(plan_id: str) -> None:
    from swingbot.core.db.repositories.starred import starred_repo
    starred_repo().unstar(plan_id)


PLAN_TEMPLATE_RE = r"plan:{action}:(?P<plan_id>[0-9a-f-]{{36}})(?::(?P<author>\d{{17,20}}))?"
LEGACY_REPLY = "This alert predates v152 — use the plan page or `!plans`."
NOT_YOUR_PANEL = "Not your panel."
PLAN_GONE = "This plan no longer exists."
WATCH_ON = ("⭐ Watching — it sorts first on `!plans` at equal follow score; "
            "`/notify` sets which plan updates name you.")
WATCH_OFF = "No longer watching."
FOLLOWABLE_STATUSES = frozenset({PlanStatus.PENDING, PlanStatus.ACTIVE, PlanStatus.PARTIAL})
FOLLOW_RECORDED = "Recorded as followed — paper plan, not your fill."
FOLLOW_REMOVED = "No longer recorded as followed."
FOLLOW_REFUSED = ("This plan is already {status}: following is recorded only while a plan is "
                  "pending, active or partial, so a press after the outcome is known is not counted.")
FOLLOW_FAILED = "Could not record that just now; please try again."
_DIRECTION_WORD = {"bullish": "long", "bearish": "short"}


def _template(action: str) -> str:
    return PLAN_TEMPLATE_RE.format(action=action)


def custom_id_for(action: str, plan_id: str, author_id: int | None) -> str:
    """The persistent custom_id of one plan button: always the plan id, and
    the author id only for an author-locked (`!top`) panel."""
    base = f"plan:{action}:{plan_id}"
    return base if author_id is None else f"{base}:{author_id}"


def _persistable(plan_id: str, author_id: int | None) -> bool:
    return re.fullmatch(_template("chart"), custom_id_for("chart", plan_id, author_id)) is not None


def _get_plan(plan_id: str):
    """Sync plan read; every button calls it through asyncio.to_thread."""
    return PlanStore().get(plan_id)


class _PlanButtonMixin:
    """The body every persistent plan button shares. A concrete button sets
    ACTION/LABEL/STYLE and passes `template=_template(ACTION)` to
    DynamicItem; this mixin must come first in the bases so its
    interaction_check overrides DynamicItem's pass-through."""

    ACTION = ""
    LABEL = ""
    STYLE = discord.ButtonStyle.secondary

    def __init__(self, plan_id: str, author_id: int | None = None):
        super().__init__(discord.ui.Button(
            label=self.LABEL, style=self.STYLE,
            custom_id=custom_id_for(self.ACTION, plan_id, author_id)))
        self.plan_id = plan_id
        self.author_id = author_id

    @classmethod
    async def from_custom_id(cls, interaction, item, match, /):
        author = match["author"]
        return cls(match["plan_id"], int(author) if author else None)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.author_id is None or interaction.user.id == self.author_id:
            return True
        await interaction.response.send_message(NOT_YOUR_PANEL, ephemeral=True)
        return False


async def _send_chart(interaction: discord.Interaction, plan_id: str) -> None:
    await interaction.response.defer(ephemeral=True, thinking=True)
    plan = await asyncio.to_thread(_get_plan, plan_id)
    if plan is None:
        await interaction.followup.send("This plan no longer exists (closed/cancelled and pruned).", ephemeral=True)
        return
    try:
        df = await asyncio.to_thread(get_daily_data, plan.ticker)
    except Exception as exc:
        log.warning("plan panel %s: could not fetch price data for %s", plan_id, plan.ticker, exc_info=True)
        await interaction.followup.send(f"Could not fetch price data for {plan.ticker}: {exc}", ephemeral=True)
        return
    h = HORIZONS.get(plan.horizon_key, {})
    filename = f"{plan.ticker}_{plan.plan_id}_panel.png"
    try:
        chart_path = await asyncio.to_thread(
            generate_trade_chart,
            plan.ticker, df, plan.trigger_price, plan.stop_loss, plan.tp1,
            plan.direction, plan.strategy, h.get("label", plan.horizon_key), config.TRADE_CHART_DIR,
            filename=filename, currency_symbol=get_currency_symbol(plan.ticker, config.CURRENCY_SYMBOL),
            target2=plan.tp2, trendline_lookback=h.get("fib_lookback", DEFAULT_TRENDLINE_LOOKBACK_DAYS),
            horizon=h, plan_v2=plan,
        )
    except Exception as exc:
        log.warning("plan panel %s: chart render failed", plan_id, exc_info=True)
        await interaction.followup.send(f"Chart render failed: {exc}", ephemeral=True)
        return
    await interaction.followup.send(
        file=discord.File(chart_path, filename=os.path.basename(chart_path)), ephemeral=True,
    )


def _sessions_left(plan, now: dt.datetime | None = None) -> int:
    """Sessions left of `expiry_bars`: NYSE sessions after the creation date
    up to today's market date count as spent. Informational only."""
    created = dt.date.fromisoformat(str(plan.created_at)[:10])
    spent = len(nyse_calendar().sessions(created + dt.timedelta(days=1), market_today(now)))
    return max(0, int(plan.expiry_bars) - spent)


def _pending_detail(plan, price, now) -> str:
    left = _sessions_left(plan, now)
    line = (f"Entry trigger {plan.trigger_price:.2f}; "
            f"{left} of {plan.expiry_bars} session(s) left before it expires.")
    return f"{line} Plan stale." if left <= 1 else line


def _open_detail(plan, price, now) -> str:
    if price is None:
        return ""
    entry = plan.entry_price if plan.entry_price is not None else plan.trigger_price
    line = f"Last {price:.2f} vs entry {entry:.2f}."
    risk = abs(entry - plan.stop_loss)
    sign = 1 if plan.direction == "bullish" else -1
    beyond = (price - entry) * sign / risk if risk else 0.0
    return f"{line} Price already beyond entry by {beyond:.2f}R." if beyond > 0 else line


_STATUS_DETAIL = {
    PlanStatus.PENDING: _pending_detail,
    PlanStatus.ACTIVE: _open_detail,
    PlanStatus.PARTIAL: _open_detail,
}


def following_reply(plan, price: float | None, now: dt.datetime | None = None) -> str:
    """The Following button's ephemeral reply: status and entry validity as
    facts. It informs and never blocks; `price=None` drops the price line."""
    word = _DIRECTION_WORD.get(plan.direction, plan.direction)
    head = f"{plan.ticker} {word} paper plan, status {plan.status}."
    detail = _STATUS_DETAIL.get(plan.status, lambda *_: "")(plan, price, now)
    return "\n".join(line for line in (head, detail, FOLLOW_RECORDED) if line)


def _followers():
    from swingbot.core.db.repositories.followers import followers_repo
    return followers_repo()


def _toggle_watch(plan, user_id: int) -> bool:
    """Toggle the presser's watch row. True = now watching. The first
    watcher stars the plan; the last one leaving unstars it."""
    repo = _followers()
    if repo.has(plan.plan_id, user_id, "watch"):
        repo.remove(plan.plan_id, user_id, "watch")
        if not repo.user_ids(plan.plan_id, ("watch",)):
            unstar_plan(plan.plan_id)
        return False
    first = not repo.user_ids(plan.plan_id, ("watch",))
    repo.add(plan.plan_id, user_id, "watch", status_at_press=plan.status)
    if first:
        star_plan(plan.plan_id)
    return True


def _copy_taken_to_trade(plan_id: str, repo) -> None:
    from swingbot.core.tracking.performance import TradeLog
    try:
        TradeLog().mark_taken(plan_id, repo.user_ids(plan_id, ("taken",)))
    except Exception:
        log.warning("Following: could not copy followers onto plan %s's trade"
                    " -- close_plan_trade re-stamps it", plan_id, exc_info=True)


def _toggle_following(plan, user_id: int) -> bool:
    """Toggle the presser's `taken` row, then rewrite the trade copy from the
    table. True = now following. Callers have checked FOLLOWABLE_STATUSES."""
    repo = _followers()
    following = not repo.has(plan.plan_id, user_id, "taken")
    if following:
        repo.add(plan.plan_id, user_id, "taken", status_at_press=plan.status)
    else:
        repo.remove(plan.plan_id, user_id, "taken")
    _copy_taken_to_trade(plan.plan_id, repo)
    return following


def _last_close(ticker: str) -> float | None:
    """Latest cached daily close, None on any failure (the reply drops the line)."""
    try:
        return float(get_daily_data(ticker)["Close"].iloc[-1])
    except Exception:
        log.debug("Following: no cached close for %s", ticker, exc_info=True)
        return None


class ChartButton(_PlanButtonMixin, discord.ui.DynamicItem[discord.ui.Button],
                  template=_template("chart")):
    ACTION = "chart"
    LABEL = "📊 Chart"
    STYLE = discord.ButtonStyle.primary

    async def callback(self, interaction: discord.Interaction) -> None:
        await _send_chart(interaction, self.plan_id)


class BreakdownButton(_PlanButtonMixin, discord.ui.DynamicItem[discord.ui.Button],
                      template=_template("breakdown")):
    ACTION = "breakdown"
    LABEL = "🔍 Breakdown"

    async def callback(self, interaction: discord.Interaction) -> None:
        plan = await asyncio.to_thread(_get_plan, self.plan_id)
        if plan is None:
            await interaction.response.send_message(PLAN_GONE, ephemeral=True)
            return
        await interaction.response.send_message(embed=breakdown_embed(plan), ephemeral=True)


class WatchButton(_PlanButtonMixin, discord.ui.DynamicItem[discord.ui.Button],
                  template=_template("watch")):
    ACTION = "watch"
    LABEL = "⭐ Watch"

    async def callback(self, interaction: discord.Interaction) -> None:
        plan = await asyncio.to_thread(_get_plan, self.plan_id)
        if plan is None:
            await interaction.response.send_message(PLAN_GONE, ephemeral=True)
            return
        watching = await asyncio.to_thread(_toggle_watch, plan, interaction.user.id)
        await interaction.response.send_message(WATCH_ON if watching else WATCH_OFF, ephemeral=True)


class FollowingButton(_PlanButtonMixin, discord.ui.DynamicItem[discord.ui.Button],
                      template=_template("follow")):
    """Records that the presser followed this paper plan -- intent, never a
    fill -- while the plan is still open."""

    ACTION = "follow"
    LABEL = "✅ Following"
    STYLE = discord.ButtonStyle.success

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        plan = await asyncio.to_thread(_get_plan, self.plan_id)
        reply = await self._reply_for(plan, interaction.user.id)
        await interaction.followup.send(reply, ephemeral=True)

    async def _reply_for(self, plan, user_id: int) -> str:
        if plan is None:
            return PLAN_GONE
        if plan.status not in FOLLOWABLE_STATUSES:
            return FOLLOW_REFUSED.format(status=plan.status)
        try:
            following = await asyncio.to_thread(_toggle_following, plan, user_id)
        except Exception:
            log.warning("Following: could not toggle plan %s for user %s", self.plan_id, user_id, exc_info=True)
            return FOLLOW_FAILED
        if not following:
            return FOLLOW_REMOVED
        price = await asyncio.to_thread(_last_close, plan.ticker)
        return following_reply(plan, price)


class DismissButton(_PlanButtonMixin, discord.ui.DynamicItem[discord.ui.Button],
                    template=_template("dismiss")):
    ACTION = "dismiss"
    LABEL = "🔕 Dismiss"

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(view=None)


PLAN_BUTTONS: tuple[type, ...] = (ChartButton, BreakdownButton, WatchButton, FollowingButton, DismissButton)


class PlanActionView(discord.ui.View):
    """One persistent action panel per posted plan. `author_id=None` lets
    any user press (scan and digest alerts: nobody ran a command);
    `!top` passes the caller's id, which rides in every custom_id so the
    lock survives a restart."""

    def __init__(self, plan_id: str, author_id: int | None):
        super().__init__(timeout=None)
        self.plan_id = plan_id
        self.author_id = author_id
        self.message: discord.Message | None = None
        if not _persistable(plan_id, author_id):
            log.warning("plan panel: plan %r / author %r cannot form a persistent custom_id"
                        " -- posting without buttons", plan_id, author_id)
            return
        for button_cls in PLAN_BUTTONS:
            self.add_item(button_cls(plan_id, author_id))


def chart_only_view(plan_id: str) -> discord.ui.View:
    """A persistent view with just the Chart button (the notify channel's
    messages, V152-17)."""
    view = discord.ui.View(timeout=None)
    if _persistable(plan_id, None):
        view.add_item(ChartButton(plan_id))
    return view


async def _legacy_reply(interaction: discord.Interaction) -> None:
    await interaction.response.send_message(LEGACY_REPLY, ephemeral=True)


class LegacyPlanPanel(discord.ui.View):
    """Claims the four static ids every pre-v152 alert carries, so pressing
    one never shows "This interaction failed". Those ids hold no plan id:
    Chart/Breakdown/Watch can only point at the plan page; Dismiss needs no
    plan and still removes the panel."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📊 Chart", style=discord.ButtonStyle.primary, custom_id="plan:chart")
    async def chart_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _legacy_reply(interaction)

    @discord.ui.button(label="🔍 Breakdown", style=discord.ButtonStyle.secondary, custom_id="plan:breakdown")
    async def breakdown_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _legacy_reply(interaction)

    @discord.ui.button(label="⭐ Watch", style=discord.ButtonStyle.secondary, custom_id="plan:watch")
    async def watch_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _legacy_reply(interaction)

    @discord.ui.button(label="🔕 Dismiss", style=discord.ButtonStyle.secondary, custom_id="plan:dismiss")
    async def dismiss_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(view=None)


def register_persistent_views(bot) -> None:
    """Called once from bot_core.setup_hook, before the gateway connects.
    Reads PLAN_BUTTONS at call time, so a button appended later registers too."""
    bot.add_dynamic_items(*PLAN_BUTTONS)
    bot.add_view(LegacyPlanPanel())


def breakdown_embed(plan) -> discord.Embed:
    """Pure renderer (plan in, Embed out) so this is unit-testable
    without any Interaction plumbing -- the button callback below is a
    thin wrapper that just calls this and sends it ephemeral."""
    from swingbot.core.analytics.rank import follow_score, follow_breakdown

    embed = discord.Embed(title=f"🔍 Breakdown — {plan.ticker} ({plan.badge})")

    quality_lines = "\n".join(f"{label}: {pts:+d}" for label, pts in (plan.quality_breakdown or [])) or "no components recorded"
    embed.add_field(name=f"📐 Quality score ({plan.quality_score}/100)", value=quality_lines, inline=False)

    stats = plan.badge_stats or {}
    badge_lines = (
        f"Status: {stats.get('status', plan.badge)}\n"
        f"OOS N={stats.get('n', 0)}, WR {stats.get('win_rate', 0):.1f}%, "
        f"ExpR {stats.get('expectancy_r', 0):+.3f}"
        f"{decay_note(decay_for(stats.get('run_date', '')))}"
        f"\nWindow: {stats.get('window', 'n/a')}"
    )
    embed.add_field(name="🏷️ Badge / track record", value=badge_lines, inline=False)

    today = market_today()
    score = follow_score(plan, today=today)
    breakdown = follow_breakdown(plan, today)
    breakdown_lines = "\n".join(f"{label}: +{pts:.0f}" for label, pts in breakdown) or "no components"
    embed.add_field(name=f"🧭 Follow score ({score:.0f})", value=breakdown_lines, inline=False)

    history = (plan.status_history or [])[-5:]
    if history:
        timeline_lines = []
        for i, entry in enumerate(history):
            frm = history[i - 1]["status"] if i > 0 else "—"
            timeline_lines.append(f"{entry.get('at', '?')} {frm}→{entry['status']} ({entry.get('reason') or 'n/a'})")
        timeline = "\n".join(timeline_lines)
    else:
        timeline = "No transitions recorded yet."
    embed.add_field(name="🕒 Status timeline", value=timeline[:1024], inline=False)

    ui.apply_chrome(embed, accent=ui.accent_for_level(plan.confidence_level),
                    plan_id=plan.plan_id, link_base=config.ADMIN_PUBLIC_URL)
    return embed


PLAN_BOARD_PAGE_SIZE = 8


def paginate(items: list, page: int, per_page: int) -> tuple:
    """Same slicing/clamping semantics as TradesPaginator's inline page
    logic (trades.py:83-113), extracted here so PlanBoardView can reuse
    it without duplicating the arithmetic. TradesPaginator itself is
    intentionally left untouched by this task -- a follow-up could have
    it import this helper too, but that's out of scope here."""
    max_page = max(0, (len(items) - 1) // per_page) if items else 0
    page = max(0, min(page, max_page))
    start = page * per_page
    return items[start:start + per_page], page, max_page


class PlanBoardView(discord.ui.View):
    """
    Filterable !plans board (Task B15 supplies render_fn). Three
    dropdowns hold the current status/level/badge filter state; every
    selection change and the Refresh button all funnel through the
    same `_apply` method, which calls `render_fn` and edits the
    message in place -- one render path regardless of which control
    triggered it, so there's no risk of the three selects drifting out
    of sync with each other.

    v32 Task 11: the tier (A/B/C) dropdown is replaced by a confidence
    level (1-5) dropdown -- level is the number that actually gates
    whether an alert fires, tier never did.
    """

    def __init__(self, render_fn, author_id: int, *, items: list = None, timeout: int = 180):
        super().__init__(timeout=timeout)
        self.render_fn = render_fn
        self.author_id = author_id
        self.status = "All"
        self.level = "All"
        self.badge = "All"
        self.items = items or []
        self.page = 0
        self.message: discord.Message | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.author_id:
            return True
        await interaction.response.send_message("Not your panel.", ephemeral=True)
        return False

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    async def _apply(self, *, status=None, level=None, badge=None, interaction: discord.Interaction = None):
        if status is not None:
            self.status = status
        if level is not None:
            self.level = level
        if badge is not None:
            self.badge = badge
        content, embed = self.render_fn(self.status, self.level, self.badge)
        if interaction is not None:
            await interaction.response.edit_message(content=content, embed=embed, view=self)
        return content, embed

    @discord.ui.select(
        placeholder="Status: All", custom_id="board:status",
        options=[discord.SelectOption(label=v, value=v) for v in ("All", "PENDING", "ACTIVE", "PARTIAL")],
    )
    async def status_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        await self._apply(status=select.values[0], interaction=interaction)

    @discord.ui.select(
        placeholder="Level: All", custom_id="board:level",
        options=[discord.SelectOption(label=v, value=v) for v in ("All", "1", "2", "3", "4", "5")],
    )
    async def level_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        await self._apply(level=select.values[0], interaction=interaction)

    @discord.ui.select(
        placeholder="Badge: All", custom_id="board:badge",
        options=[discord.SelectOption(label=v, value=v) for v in ("All", "VALIDATED", "WEAK")],
    )
    async def badge_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        await self._apply(badge=select.values[0], interaction=interaction)

    @discord.ui.button(label="🔄 Refresh", style=discord.ButtonStyle.secondary, custom_id="board:refresh")
    async def refresh_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._apply(interaction=interaction)

    @discord.ui.button(label="◀ Prev", style=discord.ButtonStyle.secondary, custom_id="board:prev")
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = max(0, self.page - 1)
        await self._apply(interaction=interaction)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary, custom_id="board:next")
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        _, _, max_page = paginate(self.items, self.page, PLAN_BOARD_PAGE_SIZE)
        self.page = min(max_page, self.page + 1)
        await self._apply(interaction=interaction)
