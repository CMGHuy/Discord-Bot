import logging
import os

import discord

from swingbot import config
from swingbot.bot_core import bot
from swingbot.core import presentation as ui
from swingbot.core.presentation import kinds
from swingbot.core.presentation.kinds import Kind
from swingbot.core.analytics.rank import rank_plans
from swingbot.core.market.session import market_today

log = logging.getLogger(__name__)

def _ordered_alerts(alerts: list, today=None) -> list:
    """Splits `alerts` (each a (embed, chart_path, plan_or_none) tuple)
    into plan-carrying and legacy groups, ranks the plan-carrying group
    by analytics.rank.rank_plans (THE shared ordering -- see Plan A
    Task A18), and returns plan-carrying alerts first (highest
    follow_score first), then every legacy (no-plan) alert in its
    original scan order, unchanged. rank_plans is given the plan
    objects directly and returns them in ranked order; this function
    re-derives the alert tuple order from that ranked plan-object list
    rather than re-scoring anything itself, so there is exactly one
    place (analytics.rank) that ever computes follow_score."""
    plan_alerts = [a for a in alerts if a[2] is not None]
    legacy_alerts = [a for a in alerts if a[2] is None]

    ranked_plans = rank_plans([a[2] for a in plan_alerts], today=today)
    by_plan_id = {id(a[2]): a for a in plan_alerts}
    ranked_alert_tuples = [by_plan_id[id(p)] for p in ranked_plans]

    return ranked_alert_tuples + legacy_alerts


def digest_payload(plans: list, today, max_n: int) -> list:
    """VALIDATED-only, follow_score-ranked, capped at max_n -- the exact
    same top_plans() ranking (Task B17) with one extra filter: WEAK
    plans never appear in the curated digest even though they stay
    fully visible in !plans and in live alerts (this Part's Global
    Constraint: 'never suppress WEAK plans' applies to the FULL
    surface, not to this one deliberately-curated shortlist)."""
    from swingbot.commands.stats import top_plans

    validated_only = [p for p in plans if p.badge == "VALIDATED"]
    return top_plans(validated_only, max_n, today=today)


async def _post_daily_digest(channel) -> None:
    """Posts the curated 'Top plans today' digest right after the
    trading session closes for the day (see _check_session_transition's
    'session just closed' edge) -- gated on config.DAILY_DIGEST_ENABLED,
    default off. Reuses _fake_item_from_plan/build_embed exactly like
    !top (Task B17) so the digest embeds are pixel-identical to what a
    user would see running !top themselves."""

    from swingbot.core.planning.plan_store import PlanStore
    from swingbot.commands.stats import _fake_item_from_plan
    from swingbot.core.scanning.embeds import build_embed
    from swingbot.commands.views import PlanActionView

    plans = PlanStore().all()
    top = digest_payload(plans, market_today(), config.DIGEST_MAX_PLANS)
    if not top:
        await channel.send(content=kinds.content_line(
            Kind.DIGEST, "", detail="no VALIDATED plans qualified today"))
        return

    # v110 §4: one registry content line for the whole batch, on its first
    # embed -- it replaces the separate "📌 Top plans today" header message.
    header = kinds.content_line(
        Kind.DIGEST, "", detail=f"{len(top)} VALIDATED plan(s), ranked by follow score")
    for index, plan in enumerate(top):
        item = _fake_item_from_plan(plan)
        embed = build_embed(item, "", {"closed": 0}, None, None, layout="compact")
        view = PlanActionView(plan.plan_id, author_id=None)
        kwargs = {"embed": embed, "view": view}
        if index == 0:
            kwargs["content"] = header
        view.message = await channel.send(**kwargs)


def cap_alerts(items: list, max_alerts: int | None = None) -> tuple:
    """Alert-flood control for big universes: full alerts for the best
    `max_alerts` by follow score, a digest line for the rest -- ranked,
    not truncated arbitrarily."""
    cap = max_alerts if max_alerts is not None else getattr(config, "MAX_ALERTS_PER_SCAN", 10)
    ranked = sorted(items, key=lambda i: (getattr(i, "follow_score", None)
                                          or getattr(i, "quality_score", 0) or 0),
                    reverse=True)
    return ranked[:cap], ranked[cap:]


def route_channel_id(item) -> str:
    """Task E86: top-confidence VALIDATED plans stay in the main alerts
    channel; everything else goes to the firehose channel when one is
    configured (empty DISCORD_CHANNEL_FIREHOSE_ID = no behavior change).

    v32 Task 11: was tier-A (quality.py's own top quality_score band,
    score >= 75); tier is retired, replaced by confidence LEVEL 5 (the top
    of the 1-5 legacy scale -- UNIFIED_CONFIDENCE stayed default-off after
    v32's VALIDATION FAIL, see docs/superpowers/plans/
    v32-train-preregistration.md) -- the number that actually gates
    whether an alert fires, which tier never did."""
    firehose = getattr(config, "DISCORD_CHANNEL_FIREHOSE_ID", "") or ""
    plan = getattr(item, "plan", None)
    top_level = plan is not None and getattr(plan, "confidence_level", None) == 5 \
        and getattr(plan, "badge", "") == "VALIDATED"
    if top_level or not firehose:
        return config.DISCORD_CHANNEL_TRADES_ID
    return firehose


def _simple_alert_channel():
    """The channel object for DISCORD_CHANNEL_TRADES_SIMPLE_ID, or None.

    Optional by design, exactly like DISCORD_CHANNEL_FIREHOSE_ID: leaving the
    var blank is the supported way to turn the simple mirror off, so an unset
    value is a debug line, not a warning. A set-but-unresolvable id IS worth a
    warning -- that's a misconfiguration, not a choice. Resolved once per
    batch rather than per alert since get_channel is a cache lookup that
    cannot change mid-batch.
    """
    chan_id = getattr(config, "DISCORD_CHANNEL_TRADES_SIMPLE_ID", "") or ""
    if not chan_id:
        log.debug("DISCORD_CHANNEL_TRADES_SIMPLE_ID not set; simple alerts disabled.")
        return None
    try:
        channel = bot.get_channel(int(chan_id))
    except (TypeError, ValueError):
        log.warning("DISCORD_CHANNEL_TRADES_SIMPLE_ID=%r is not a valid channel id; "
                    "simple alerts disabled for this batch.", chan_id)
        return None
    if channel is None:
        log.warning("Simple-alerts channel %s not found (is the bot in that guild, "
                    "and can it see the channel?); simple alerts skipped.", chan_id)
    return channel


DEEP_SCAN_NOTE = ("Watchlist candidates for Monday -- forming setups at relaxed "
                  "thresholds (NOT alerts, NOT validated signals)")


def deep_scan_report(items: list) -> str:
    """Task E87: renders the Saturday weekend-deep-scan candidate list --
    NOT alerts, just a curated heads-up for Monday. Pure formatting; see
    weekend_deep_scan() for how `items` gets built from a relaxed-threshold
    scan pass. v110: the 🔭 header is the SYSTEM embed's title (recap.py),
    and each candidate leads with its ▲/▼."""
    lines = [DEEP_SCAN_NOTE]
    for it in sorted(items, key=lambda i: -(i.quality_score or 0))[:15]:
        glyph = ui.direction_glyph(getattr(it.plan, "direction", ""))
        lines.append(f"{glyph} {it.ticker:<6} {it.plan.strategy:<18} "
                     f"q{it.quality_score} — {ui.fmt_pct(it.trigger_distance_pct)} from trigger")
    return "\n".join(lines)


def _append_overflow_digest(to_send: list, overflow: list, follow_score) -> None:
    """Name every capped-out plan in the last posted alert's footer.

    Index rather than unpack: engine.py emits 4-tuples, and a fixed 3-name
    unpack once raised before any send, losing every alert."""
    overflow_plans = [a[2] for a in overflow if len(a) > 2 and a[2] is not None]
    digest_items = [(p.ticker, round(follow_score(p))) for p in overflow_plans]
    if not digest_items:
        return
    digest = "+%d more: %s" % (len(digest_items),
                               ", ".join(f"{t} ({s})" for t, s in digest_items))
    last_embed = to_send[-1][0]
    existing_footer = last_embed.footer.text if last_embed.footer else None
    last_embed.set_footer(text=f"{existing_footer} | {digest}" if existing_footer else digest)


def _destination(destination, firehose_channel, firehose_id: str, plan, route_by_confidence: bool):
    """The channel one alert posts to: the caller's, or the firehose (Task E86)."""
    if not (route_by_confidence and firehose_channel is not None and plan is not None):
        return destination
    target_id = route_channel_id(type("I", (), {"plan": plan})())
    return firehose_channel if target_id == firehose_id else destination


async def _mirror(simple_channel, simple_embed, plan) -> bool:
    """Post the simple-channel mirror with its content line; True once it
    landed. A failure never costs the real alert -- it keeps its ping."""
    if simple_channel is None or not simple_embed:
        return False
    try:
        await simple_channel.send(**ui.push_kwargs(simple_embed))
    except Exception as exc:
        log.warning("Could not post simple alert for %s to channel %s: %s "
                    "-- full alert will notify instead.",
                    getattr(plan, "ticker", "?"),
                    getattr(config, "DISCORD_CHANNEL_TRADES_SIMPLE_ID", ""), exc,
                    exc_info=True)
        return False
    return True


async def _post_alert(send_to, embed, chart_path, plan, mirrored: bool, view_cls) -> None:
    """Send one full alert: content line, chart, plan buttons. silent=True
    only once the mirror landed (the alerts channel forces it regardless)."""
    view = view_cls(plan.plan_id, author_id=None) if plan is not None else None
    kwargs = {**ui.push_kwargs(embed), "silent": mirrored}
    if chart_path:
        kwargs["file"] = discord.File(chart_path, filename=os.path.basename(chart_path))
    if view is not None:
        kwargs["view"] = view
    msg = await send_to.send(**kwargs)
    if view is not None:
        view.message = msg


async def _send_alerts(destination, alerts, route_by_confidence: bool = False):
    """alerts: list of (embed, chart_path, plan_or_none, simple_text_or_none)
    tuples; the 4th element is optional (see the unpack below).

    Notification policy: the alerts channel (DISCORD_CHANNEL_TRADES_ID)
    never notifies at all -- it is resolved through silence()
    (swingbot/core/infra/silent_channel.py), which forces silent=True on every
    send regardless of the `silent` kwarg built below. Alerts are still
    delivered and still rendered in full there; they just don't ping.

    The `mirrored` flag below therefore only governs destinations that are
    NOT the alerts channel -- the firehose, and the `ctx` a user ran
    `!check` in: those are silenced only once the signal has actually been
    mirrored to DISCORD_CHANNEL_TRADES_SIMPLE_ID, so a missing or failed
    mirror can never leave a signal unannounced everywhere at once.

    Every plan-carrying alert gets a PlanActionView(plan.plan_id,
    author_id=None) attached (any user may click); legacy (no-plan) alerts
    get no view. PlanActionView is imported lazily here rather than at
    module top to avoid a circular import: views.py imports from
    swingbot.core.planning.plan_store, and scanning.py is imported very early during
    bot startup (bot_core.py registers commands from every
    swingbot/commands/* module) -- a top-level import is safe today (no
    cycle exists), but the lazy import documents the intent and costs
    nothing at this call frequency (once per alert message, not per scan
    tick).

    `route_by_confidence` (Task E86) is opt-in and OFF by default: it re-routes
    below-top-confidence alerts to DISCORD_CHANNEL_FIREHOSE_ID (when configured) via
    route_channel_id(). Only the automatic scheduled/UI-triggered scan
    paths pass True -- a user's own `!check`/`!scan` command result must
    keep posting back to wherever they invoked it (`ctx`), never get
    silently redirected mid-command.
    """
    from swingbot.commands.views import PlanActionView
    from swingbot.core.analytics.rank import follow_score

    # Alert-flood control (Task E77): _ordered_alerts already ranks by
    # follow_score (rank_plans, THE shared ordering), so the cap is applied
    # directly to that ranked list.
    ordered = _ordered_alerts(alerts)
    cap = getattr(config, "MAX_ALERTS_PER_SCAN", 10)
    to_send, overflow = ordered[:cap], ordered[cap:]
    if overflow:
        _append_overflow_digest(to_send, overflow, follow_score)

    firehose_id = getattr(config, "DISCORD_CHANNEL_FIREHOSE_ID", "") or ""
    firehose_channel = bot.get_channel(int(firehose_id)) if route_by_confidence and firehose_id else None
    simple_channel = _simple_alert_channel()

    for alert in to_send:
        # Tolerant unpack: engine.py emits 4-tuples (..., simple_embed), but the
        # legacy 3-tuple shape is still built by hand in tests. A missing 4th
        # element just means "no simple mirror for this one".
        embed, chart_path, plan = alert[0], alert[1], alert[2]
        simple_embed = alert[3] if len(alert) > 3 else None
        send_to = _destination(destination, firehose_channel, firehose_id, plan,
                               route_by_confidence)
        # ONE ping per signal, from the simple channel: the mirror goes FIRST
        # and its success decides whether the full alert is silenced.
        mirrored = await _mirror(simple_channel, simple_embed, plan)
        # v110 s6.2: each send is isolated -- one failure is logged with its
        # traceback and the rest of the batch still posts.
        try:
            await _post_alert(send_to, embed, chart_path, plan, mirrored, PlanActionView)
        except Exception:
            log.warning("Could not post alert for %s -- the rest of the batch still posts.",
                        getattr(plan, "ticker", None) or getattr(embed, "title", "?"),
                        exc_info=True)
