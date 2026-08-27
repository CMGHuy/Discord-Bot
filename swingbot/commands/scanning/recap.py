from swingbot import config
from swingbot.bot_core import bot, log
from swingbot.core.scanning import engine as scan_engine
from .alerts import deep_scan_report

trade_log = scan_engine.trade_log

async def _resolve_retrospective_channel(channel_id_override: int | None = None, *, caller: str = "daily_recap"):
    """Explicit override -> DISCORD_CHANNEL_RETROSPECTIVE_ID -> DISCORD_CHANNEL_TRADES_HISTORY_ID.
    Shared by _post_retrospective and weekend_deep_scan (Task E87) -- both
    post to the same "end-of-day/week wrap-up" channel."""
    cid = channel_id_override
    if not cid:
        rc = getattr(config, "DISCORD_CHANNEL_RETROSPECTIVE_ID", None)
        if rc:
            try:
                cid = int(rc)
            except (ValueError, TypeError):
                pass
    if not cid:
        cc = getattr(config, "DISCORD_CHANNEL_TRADES_HISTORY_ID", None)
        if cc:
            try:
                cid = int(cc)
            except (ValueError, TypeError):
                pass
    if not cid:
        log.warning("%s: no channel configured (set DISCORD_CHANNEL_RETROSPECTIVE_ID or DISCORD_CHANNEL_TRADES_HISTORY_ID).", caller)
        return None

    channel = bot.get_channel(cid)
    if channel is None:
        try:
            channel = await bot.fetch_channel(cid)
        except Exception as exc:
            log.warning("%s: cannot resolve channel %s: %s", caller, cid, exc)
            return None
    return channel


async def _post_retrospective(channel_id_override: int | None = None, today=None):
    """Build and post today's (or `today`'s, if given) retrospective. Called
    by daily_recap task and !recap command."""
    from swingbot.core.tracking.retrospective import build_daily_retrospective

    all_trades = trade_log.get_trades(limit=10_000)
    messages   = build_daily_retrospective(all_trades, today=today)

    channel = await _resolve_retrospective_channel(channel_id_override)
    if channel is None:
        return

    for msg in messages:
        if not msg.strip():
            continue
        # Discord message limit is 2000 chars; chunk if needed
        while len(msg) > 1990:
            split_at = msg.rfind("\n", 0, 1990)
            if split_at == -1:
                split_at = 1990
            await channel.send(msg[:split_at])
            msg = msg[split_at:]
        if msg.strip():
            await channel.send(msg)


async def weekend_deep_scan() -> str:
    """Task E87: Saturday-only job. Full-universe scan at relaxed
    thresholds (SIGNAL_CONFIRMATION_SCANS forced to 1, MIN_ALERT_CONFIDENCE_LEVEL
    lowered by 1) producing a watchlist-candidates report for Monday --
    posted, not alerted (require_confirmation=False bypasses the debounce
    counter but every item still has to pass the real entry/stop/reward/
    confluence gates, so these are real, currently-valid setups, not noise).

    HONEST GAP vs the brief's "quality floor lowered by 10": this codebase
    has no 0-100 quality_score gate on whether an item becomes an alert --
    quality_score is purely informational/ranking. The only real gate that
    controls "does this item qualify at all" is MIN_ALERT_CONFIDENCE_LEVEL
    (a 1-5 tier), so that's what gets relaxed here, by 1 tier, floored at 1.

    trigger_distance_pct is likewise not stored on a built plan (it's a
    transient scoring input inside _build_quality_inputs, discarded after
    quality.score_plan runs) and run_scan doesn't expose its raw pre-alert
    candidate list -- so this recomputes it fresh from each returned
    alert's own trigger_price vs. current price, the same formula
    _build_quality_inputs uses.

    Goes through scan_engine.run_scan() (not the raw _sync_run_scan) so
    this gets the same _scan_lock mutex, is_scan_running() flag, and
    closed-trade/near-close notifications every other scan path gets --
    a relaxed-threshold scan is still a real scan, not a side query.

    Returns the report string that was posted (empty string if there was
    nothing to report or the channel couldn't be resolved) -- for the
    scheduler branch to log, and for testability without a live bot.
    """
    from swingbot.core.marketdata.data import get_current_price

    old_confirm = config.SIGNAL_CONFIRMATION_SCANS
    old_min_conf = config.MIN_ALERT_CONFIDENCE_LEVEL
    relaxed_min_conf = max(1, old_min_conf - 1)
    config.SIGNAL_CONFIRMATION_SCANS = 1
    config.MIN_ALERT_CONFIDENCE_LEVEL = relaxed_min_conf
    try:
        alerts = await scan_engine.run_scan(horizon_filter="all", require_confirmation=False, bot=bot)
    finally:
        # Do not overwrite values a concurrent hot reload applied while this
        # temporary scheduler override was running.
        if config.SIGNAL_CONFIRMATION_SCANS == 1:
            config.SIGNAL_CONFIRMATION_SCANS = old_confirm
        if config.MIN_ALERT_CONFIDENCE_LEVEL == relaxed_min_conf:
            config.MIN_ALERT_CONFIDENCE_LEVEL = old_min_conf

    items = []
    for alert in alerts:
        # Indexed, not unpacked: engine.py emits 4-tuples, so a 3-name unpack
        # raised ValueError on the first alert -- and weekend_deep_scan_task
        # marks the day fired before calling this, so the Saturday report was
        # never posted on any weekend that actually found something.
        plan = alert[2] if len(alert) > 2 else None
        if plan is None:
            continue
        try:
            current = get_current_price(plan.ticker)
            dist = abs(plan.trigger_price - current) / current * 100 if current else 0.0
        except Exception:
            dist = 0.0
        items.append(type("DeepScanItem", (), {
            "ticker": plan.ticker, "quality_score": plan.quality_score,
            "trigger_distance_pct": dist, "plan": plan,
        })())

    if not items:
        return ""

    report = deep_scan_report(items)
    channel = await _resolve_retrospective_channel(caller="weekend_deep_scan")
    if channel is not None:
        await channel.send(report)
    return report
