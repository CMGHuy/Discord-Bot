import asyncio
import datetime as dt
import json
import os

import discord
from discord.ext import tasks

from swingbot import config
from swingbot.config import auto_reload_if_changed
from swingbot.core.scanning import engine as scan_engine
from swingbot.bot_core import bot, in_session, log, SESSION_TZ, install_reload_signal_handler, on_config_reload
from swingbot.core.marketdata.data import get_current_price
from swingbot.core.infra.silent_channel import silence
from swingbot.core.infra.jsonio import atomic_write_json, read_json
from swingbot.core.marketdata.watchlist import load_watchlist
from . import alerts, presence, recap, runstate
from .alerts import _send_alerts

trade_log = scan_engine.trade_log
_ready_announcement_sent = False

@tasks.loop(minutes=config.SCAN_INTERVAL_MINUTES)
async def session_scan():
    # The entire tick's real work is wrapped in a try/except (see below) so
    # ONE bad tick -- a transient network error, a malformed price bar, any
    # unhandled exception anywhere inside run_scan()'s pandas/network-heavy
    # pipeline -- can never take the whole loop down. Without this,
    # discord.py's tasks.Loop logs the traceback once and then just STOPS
    # calling this function forever (reconnect=True only auto-retries
    # discord-connection-related errors, not a generic exception raised by
    # our own scan code) -- silently, with no further log lines at all,
    # which is exactly the "bot went quiet and never scanned again" failure
    # mode seen before. Catching everything here guarantees a scan attempt
    # every SCAN_INTERVAL_MINUTES no matter what happened on the last one.
    try:
        await _session_scan_tick()
    except Exception:
        log.exception("session_scan tick failed -- will retry on the next scheduled tick "
                       "(every %d min) instead of stopping the loop entirely", config.SCAN_INTERVAL_MINUTES)
        runstate.record_tick_failure()
    else:
        runstate.record_tick_success()


def _refresh_snapshot_safely() -> None:
    try:
        from swingbot.core.analytics.snapshots import refresh_snapshot
        refresh_snapshot()
    except Exception:
        log.warning("post-scan snapshot refresh failed", exc_info=True)


async def _session_scan_tick():
    # Always refresh the live-status presence first, even on the early-return
    # paths below (paused / outside session / missing channel config) -- the
    # whole point is that this reflects the bot's real current state at least
    # once every SCAN_INTERVAL_MINUTES no matter what else happens this tick.
    await presence._refresh_presence()
    # Write heartbeat file so the admin dashboard can show a live green/red
    # status dot even when the bot is paused or outside the session window.
    runstate._write_heartbeat()

    # Resolved once, up front, so the session welcome/goodbye check below
    # can run regardless of pause state (the session boundary is about
    # market hours, not whether scanning itself is paused) -- the rest of
    # the tick still early-returns on paused/off-session/missing-config
    # exactly as before.
    channel = None
    if config.DISCORD_CHANNEL_TRADES_ID:
        # silence() -> nothing posted to the alerts channel notifies; see
        # swingbot/core/infra/silent_channel.py. Wrapped here, at the single place
        # this tick resolves the channel, so the session transition, the
        # healthcheck and every alert below inherit it.
        channel = silence(bot.get_channel(int(config.DISCORD_CHANNEL_TRADES_ID)))
    if channel is not None:
        await presence._check_session_transition(channel)

    if runstate.is_scan_paused():
        log.debug("session_scan tick skipped -- scanning is paused")
        return
    if not in_session():
        log.debug("session_scan tick skipped -- outside the session window")
        return
    if channel is None:
        log.warning("DISCORD_CHANNEL_TRADES_ID not set or channel not found; skipping scheduled post.")
        return

    now_str = dt.datetime.now(SESSION_TZ).strftime("%H:%M")
    log.info("Running session scan at %s…", now_str)
    progress = scan_engine.ScanProgress()
    alerts = await scan_engine.run_scan(require_confirmation=True, bot=bot, progress=progress)
    await _send_alerts(channel, alerts, route_by_confidence=True)

    from swingbot.core.charts.cache import purge
    await asyncio.to_thread(purge)

    _refresh_snapshot_safely()

    f = progress.funnel
    if alerts:
        log.info("Posted %d new confirmed signal(s).", len(alerts))
        if f:
            # "qualifying" and "alerts posted" can legitimately differ:
            # qualifying scenarios found for the same ticker+trend with a
            # near-identical entry/stop/target get merged into one alert by
            # dedup_scan_items() (same real setup, confirmed by more than one
            # strategy/horizon), and a qualifying scenario for a ticker that
            # already has an open trade is skipped rather than re-alerted.
            # Spelling that out here so "why did qualifying=2 but alerts=1"
            # is answerable at a glance instead of looking like a bug.
            gap_parts = []
            merged = max(0, f.get("fully_qualifying", 0) - f.get("deduped", f.get("fully_qualifying", 0)))
            if merged:
                gap_parts.append(f"{merged} merged as duplicate setup(s)")
            if f.get("skipped_already_open", 0):
                gap_parts.append(f"{f['skipped_already_open']} already open")
            gap_str = f" ({', '.join(gap_parts)})" if gap_parts else ""
            # A little more visual variety than a single 🔍 -- a quick
            # traffic-light-style read (🟢 several new alerts, 🟡 just one,
            # plus a ✨ sparkle when at least one is a priority ⭐ setup) so
            # the channel doesn't read as one flat wall of identical emoji.
            n = len(alerts)
            headline_icon = "🟢" if n >= 3 else "🟡" if n >= 1 else "⚪"
            sparkle = " ✨" if any("⭐" in (a[0].title or "") for a in alerts) else ""
            summary = (
                f"{headline_icon} 🔍 **Scan** ({now_str}) — 📡 {f['tickers']} tickers, {f['checked']} combos checked → "
                f"🧮 {f['scenarios_found']} scenario(s) found (✅ {f['fully_qualifying']} qualifying) → "
                f"**🚨 {n} new alert(s) posted above**{sparkle}{gap_str}"
            )
            await channel.send(summary)
    else:
        log.info("Session scan complete at %s — nothing new to post.", now_str)
        not_ready_parts = []
        if f and (f["scenarios_found"] > 0 or f["tickers"] > 0):
            if f.get("failed_min_confluence", 0):
                not_ready_parts.append(f"{f['failed_min_confluence']} below min strategies")
            if f.get("failed_min_confidence", 0):
                not_ready_parts.append(f"{f['failed_min_confidence']} below min confidence")
            if f.get("awaiting_confirmation", 0):
                not_ready_parts.append(f"{f['awaiting_confirmation']} awaiting confirmation")
            not_ready_log_str = (", ".join(not_ready_parts) + " — ") if not_ready_parts else ""
            log.info(
                "Scan detail (%s): %d tickers -> %d scenario(s) found (%d qualifying), %snothing new to post",
                now_str, f["tickers"], f["scenarios_found"], f["fully_qualifying"], not_ready_log_str,
            )

        # Healthcheck post -- one short message every scan tick (every
        # SCAN_INTERVAL_MINUTES), even when nothing qualified. Earlier this
        # branch deliberately posted NOTHING to avoid channel noise (see
        # _presence_text()'s docstring -- the bot's Discord presence dot was
        # meant to be the liveness signal instead). Brought back on request:
        # a live presence dot is easy to miss, and watching a message land
        # in the channel every 5 minutes is a much more obvious "yes, it's
        # still alive and actually scanning" signal than checking a status
        # dot next to the bot's name. Kept to one compact line (no embed, no
        # chart) specifically so it doesn't turn into the same noise problem
        # that got this removed the first time.
        open_count = trade_log.get_stats()["open"]
        if f:
            # Rewritten for clarity -- the old one-line version packed
            # "qualifying" and "awaiting confirmation" next to each other
            # with no explanation, which reads as a contradiction ("if it
            # qualified, why wasn't it shown?"). They're not mutually
            # exclusive: "qualifying" = passed every hard requirement
            # (min strategies confirmed, min confidence, min reward:risk,
            # etc.); "awaiting confirmation" is a SUBSET of qualifying --
            # a scenario that passed everything but hasn't yet reappeared
            # for SIGNAL_CONFIRMATION_SCANS consecutive scans in a row
            # (the automatic scan's debounce filter, meant to skip
            # intraday flicker -- see engine.py's module docstring).
            # "below min strategies"/"below min confidence" are separate
            # FAILURE tallies, not a partition of scenarios_found -- one
            # scenario can fail more than one requirement at once, so
            # those numbers can (and often do) add up to more than the
            # total scenario count. Spelling all of this out in the
            # message itself so the numbers don't need a code-read to make
            # sense of.
            awaiting = f.get("awaiting_confirmation", 0)
            confirm_note = (
                f" (needs to reappear {config.SIGNAL_CONFIRMATION_SCANS} scan(s) in a row before it posts)"
                if awaiting else ""
            )
            fail_bits = []
            if f.get("failed_min_confluence", 0):
                fail_bits.append(f"{f['failed_min_confluence']} below min strategies")
            if f.get("failed_min_confidence", 0):
                fail_bits.append(f"{f['failed_min_confidence']} below min confidence")
            if f.get("rs_blocked", 0):
                fail_bits.append(f"{f['rs_blocked']} blocked by RS gate")
            bullets = [
                f"📡 {f['tickers']} tickers scanned",
                f"🧮 {f['scenarios_found']} scenario(s) found",
                f"✅ {f['fully_qualifying']} fully qualifying (⏳ {awaiting} still awaiting confirmation{confirm_note})",
            ]
            if fail_bits:
                bullets.append(f"❌ failed a requirement: {', '.join(fail_bits)}")
            bullets.append(f"📂 {open_count} open trade(s)")
            healthcheck = (
                f"💓 **Healthcheck** ({now_str}) — nothing new this tick\n"
                + "\n".join(f"• {b}" for b in bullets)
            )
        else:
            healthcheck = (
                f"💓 **Healthcheck** ({now_str}) — scan complete, nothing new\n"
                f"• 📂 {open_count} open trade(s)"
            )
        await presence._post_healthcheck(channel, healthcheck)

    # Refresh again now that this tick's own scan may have changed the open-
    # trade count (a trade closing mid-scan shouldn't have to wait for next
    # tick's presence update to be reflected).
    await presence._refresh_presence()


@session_scan.error
async def _session_scan_error(exc: Exception):
    """
    Last-resort safety net -- _session_scan_tick()'s own try/except above
    should catch everything and let the loop keep ticking on schedule, but
    if something still manages to escape (e.g. an exception raised by
    discord.py's own task-loop machinery, outside our function body), this
    logs it AND explicitly restarts the loop rather than letting
    discord.ext.tasks quietly stop calling session_scan forever.
    """
    log.exception("session_scan loop raised past its own try/except -- restarting the loop: %s", exc)
    if not session_scan.is_running():
        session_scan.restart()

@tasks.loop(minutes=15)
async def heartbeat():
    """
    Periodic "still alive and here's the state" LOG line only (never posted
    to Discord) -- makes it easy to confirm from the logs alone (Discord UI
    or the admin UI's Logs page) that the process is actually running and
    see its basic status at a glance, without needing to correlate scan-tick
    timestamps. The user-visible "is the bot alive" signal lives on the
    bot's own Discord presence instead (see _refresh_presence(), refreshed
    every session_scan tick -- i.e. at least every SCAN_INTERVAL_MINUTES),
    not in a channel message; this log-only heartbeat is a slower (15 min),
    log-file-only companion to that, unrelated to anything posted in Discord.
    """
    open_count = trade_log.get_stats()["open"]
    watchlist_size = len(load_watchlist())
    latency_ms = round(bot.latency * 1000) if bot.latency else None
    log.info(
        "Heartbeat -- session=%s scan=%s watchlist=%d open_trades=%d gateway_latency=%sms",
        "active" if in_session() else "inactive", "paused" if runstate.is_scan_paused() else "running",
        watchlist_size, open_count,
        latency_ms if latency_ms is not None else "n/a",
    )

@tasks.loop(seconds=30)
async def config_watcher():
    """
    Polls .env mtime every 30 seconds so settings saved via the admin UI
    apply quickly even when the Docker socket isn't mounted (which would
    have allowed an immediate SIGHUP). Without this, changes would only
    take effect at the next scan tick (up to SCAN_INTERVAL_MINUTES away).
    The mtime check is a single stat() syscall -- no file I/O -- so the
    overhead is negligible.

    Also watches for a trigger file written by the admin UI's "Run !check now"
    button. When found, runs a full scan immediately (same as !check all) and
    deletes the trigger file so it doesn't fire again next tick.
    """
    changed = await asyncio.to_thread(auto_reload_if_changed)
    if changed:
        # LOG_LEVEL change needs the Python logging level updated too
        if "LOG_LEVEL" in changed:
            import logging
            logging.getLogger().setLevel(getattr(logging, config.LOG_LEVEL, logging.INFO))
        if "SCAN_INTERVAL_MINUTES" in changed and session_scan.is_running():
            session_scan.change_interval(minutes=config.SCAN_INTERVAL_MINUTES)
            log.info("Scan interval hot-reloaded to every %d min (takes effect next tick).",
                     config.SCAN_INTERVAL_MINUTES)
        _apply_market_data_refresh_config(changed)

        log.info("Config auto-reloaded from .env -- %d setting(s) changed: %s",
                 len(changed), ", ".join(f"{k}={v[1]!r}" for k, v in changed.items()))

        # Notify Discord channel about key setting changes so the user can
        # confirm the new value is live without needing to check the logs.
        _notify_keys = {
            "MIN_ALERT_CONFIDENCE_LEVEL": (
                lambda old, new: (
                    f"⚙️ **Min confidence level** updated: Lv{old} → Lv{new}  "
                    f"(next `!check` and scheduled scans will use Lv{new}+)"
                )
            ),
            "MIN_TARGET_CONFLUENCE_COUNT": (
                lambda old, new: (
                    f"⚙️ **Min strategies confirmed** updated: {old} → {new}"
                )
            ),
            "SCAN_INTERVAL_MINUTES": (
                lambda old, new: (
                    f"⚙️ **Scan interval** updated: every {old} min → every {new} min"
                )
            ),
            "MIN_RISK_REWARD_RATIO": (
                lambda old, new: (
                    f"⚙️ **Min R:R ratio** updated: {old} → {new}"
                )
            ),
        }
        if config.DISCORD_CHANNEL_TRADES_ID:
            channel = silence(bot.get_channel(int(config.DISCORD_CHANNEL_TRADES_ID)))
            if channel:
                for attr_key, fmt_fn in _notify_keys.items():
                    if attr_key in changed:
                        old_val, new_val = changed[attr_key]
                        try:
                            await channel.send(fmt_fn(old_val, new_val))
                        except Exception as _e:
                            log.warning("Could not post config-change notice to Discord: %s", _e)

    # --- Admin UI manual-close notification queue ---
    if os.path.exists(runstate._MANUAL_CLOSE_QUEUE):
        try:
            with open(runstate._MANUAL_CLOSE_QUEUE, "r") as _qf:
                _queued = json.load(_qf)
        except Exception as _qe:
            log.warning("Could not read manual_close_notify queue: %s", _qe)
            _queued = []
        if _queued:
            try:
                os.remove(runstate._MANUAL_CLOSE_QUEUE)
            except OSError:
                pass
            from swingbot.core.scanning.embeds import notify_closed_trades
            try:
                await notify_closed_trades(bot, _queued)
                log.info("Posted %d manually-closed trade notification(s) to Discord.", len(_queued))
            except Exception as _ne:
                log.warning("Failed to post manual-close notifications: %s", _ne)

    # --- Admin UI "Run !check now" trigger ---
    if os.path.exists(runstate._TRIGGER_FILE):
        try:
            os.remove(runstate._TRIGGER_FILE)
        except OSError:
            pass  # already removed by a parallel tick or a concurrent process
        else:
            log.info("Admin UI triggered a manual !check scan.")
            if not config.DISCORD_CHANNEL_TRADES_ID:
                log.warning("CHANNEL_ID not set; cannot post scan results.")
                return
            channel = silence(bot.get_channel(int(config.DISCORD_CHANNEL_TRADES_ID)))
            if channel is None:
                try:
                    channel = silence(await bot.fetch_channel(int(config.DISCORD_CHANNEL_TRADES_ID)))
                except Exception as _ce:
                    log.warning("Could not resolve channel %s for triggered scan: %s", config.DISCORD_CHANNEL_TRADES_ID, _ce)
                    return
            min_lv = config.MIN_ALERT_CONFIDENCE_LEVEL
            # Post a live-updating progress message — same UX as the Discord
            # !check command so the user sees per-ticker progress in real time.
            progress_msg = await channel.send(
                f"🔍 **Manual scan triggered from admin UI** · min confidence Lv{min_lv}"
                f" · crawling data… 0%"
            )
            progress = scan_engine.ScanProgress()

            async def _ui_poll_progress():
                last_shown = None
                while True:
                    await asyncio.sleep(2.0)
                    if progress.stage == "starting":
                        # Same fix as check_cmd's own poller (v56) -- the
                        # default stage before _sync_run_scan's thread has
                        # done anything, most commonly while queued behind
                        # another scan holding _scan_lock. Without this
                        # branch the generic "Analyzing" label below fires
                        # with a literal 0/0 (0%), indistinguishable from
                        # a genuinely stuck scan.
                        label = "⏳ **Waiting to start** (UI trigger) — queued behind another scan"
                    elif progress.stage == "crawling data":
                        pct = round(progress.done / progress.total * 100) if progress.total else 0
                        ticker_bit = f" `{progress.current_ticker}`" if progress.current_ticker else ""
                        label = (
                            f"📡 **Crawling** (UI trigger) — {progress.done}/{progress.total} "
                            f"ticker(s) fetched ({pct}%){ticker_bit}"
                        )
                    elif progress.stage == "building alerts":
                        if progress.alerts_total:
                            label = (
                                f"📊 **Building alerts** (UI trigger) — "
                                f"{progress.alerts_done}/{progress.alerts_total} done (generating charts…)"
                            )
                        else:
                            label = (
                                f"📊 **Deduplicating** (UI trigger) — "
                                f"{progress.qualifying_found} qualifying scenario(s) found, merging…"
                            )
                    else:
                        ticker_bit = f" `{progress.current_ticker}`" if progress.current_ticker else ""
                        found_bit = (
                            f" · **{progress.qualifying_found} qualifying** so far"
                            if progress.qualifying_found else ""
                        )
                        label = (
                            f"🔬 **Analyzing** (UI trigger) — {progress.done}/{progress.total} "
                            f"ticker·horizon combo(s) ({progress.pct}%){ticker_bit}{found_bit}"
                        )
                    if label != last_shown:
                        try:
                            await progress_msg.edit(content=label)
                        except discord.NotFound:
                            return
                        last_shown = label

            poller = asyncio.create_task(_ui_poll_progress())
            try:
                alerts = await scan_engine.run_scan(require_confirmation=False, bot=bot, progress=progress)
            finally:
                poller.cancel()

            await _send_alerts(channel, alerts, route_by_confidence=True)
            f = progress.funnel
            if progress.stopped:
                summary = (
                    f"🛑 **Triggered scan stopped early** (by the admin UI's Stop button or `!stop`) — "
                    f"**{len(alerts)} alert(s)** built from what completed before the stop."
                )
            elif f:
                lv_counts = f.get("conf_level_counts", {})
                lv_breakdown = (
                    "  ".join(f"Lv{lv}:{cnt}" for lv, cnt in sorted(lv_counts.items()))
                    if lv_counts else "none"
                )
                summary = (
                    f"✅ **Triggered scan complete** — {f['tickers']} ticker(s) · "
                    f"{f['fully_qualifying']} fully qualifying → **{len(alerts)} alert(s)**\n"
                    f"Confidence breakdown: {lv_breakdown}  (min Lv{min_lv})"
                )
            else:
                summary = f"✅ **Triggered scan complete** — {len(alerts)} alert(s) found (min confidence: Lv{min_lv})."
            try:
                await progress_msg.edit(content=summary)
            except discord.NotFound:
                await channel.send(summary)
            log.info("Triggered scan complete — %d alert(s) posted%s.", len(alerts),
                      " (stopped early)" if progress.stopped else "")


@config_watcher.error
async def _config_watcher_error(exc: Exception):
    log.exception("config_watcher loop escaped -- restarting: %s", exc)
    if not config_watcher.is_running():
        config_watcher.restart()

@tasks.loop(seconds=60)
async def trade_monitor():
    """
    Lightweight SL/TP price monitor — runs every 60 seconds, entirely
    separate from the full scan cycle.  For every open trade it fetches
    the live price (incl. premarket/aftermarket via get_current_price),
    calls close_if_live_price_hit() for an exact SL/TP hit, and then
    check_near_tp_timeout() for whatever's still open -- closing early,
    as a win at the live price, any trade that's gotten most of the way
    to its target and then stalled there instead of actually tapping it
    (see config.NEAR_TP_TIMEOUT_*). If any trade closes either way, a
    notification is posted to DISCORD_CHANNEL_TRADES_HISTORY_ID immediately,
    without waiting for the next scheduled scan.

    Runs regardless of whether a full scan is in progress. It used to skip
    whenever scan_engine.is_scan_running() was true, on the theory that the
    full scan's own SL/TP check (TradeLog.update_open_trades) already
    covered this tick -- but that function deliberately EXCLUDES every
    trade with a plan_id (see its own docstring: a v2 plan's real stop/
    target moves after TP1 and update_open_trades only ever sees the
    stale original levels), which is every trade once PLAN_ENGINE_V2 is
    on. With scans now taking minutes, the skip left plan-linked trades'
    stops and targets unmonitored for most of the day -- production
    incident, 2026-08-24: two trades sat "open" for hours after clearly
    breaching their stop. close_if_live_price_hit() and run_manager_tick()
    both write through their own store's lock (TradeLog._LOCK,
    plan_store._LOCK) and no-op on a trade/plan a concurrent scan already
    closed, so running alongside a scan is safe, not just tolerated.

    Also skips when there are no open trades, keeping the overhead
    proportional to actual activity.
    """
    open_trades = trade_log.get_trades(status="open", limit=200)
    if not open_trades:
        return

    tickers = list({t["ticker"] for t in open_trades})
    all_newly_closed = []

    for ticker in tickers:
        try:
            live = await asyncio.to_thread(get_current_price, ticker)
        except Exception as exc:
            log.debug("trade_monitor: price fetch failed for %s: %s", ticker, exc)
            continue
        if not live or live <= 0:
            continue
        try:
            closed = await asyncio.to_thread(trade_log.close_if_live_price_hit, ticker, live)
        except Exception as exc:
            log.warning("trade_monitor: close_if_live_price_hit failed for %s: %s", ticker, exc)
            continue
        if closed:
            log.info("trade_monitor: %d trade(s) closed for %s (live=%.4f)", len(closed), ticker, live)
            all_newly_closed.extend(closed)

        # Near-TP timeout exit: for whatever's STILL open on this ticker
        # after the exact SL/TP check above (a trade that just tapped its
        # real target this same tick is already gone from "open" status by
        # the time this runs) -- locks in profit on a trade that got most
        # of the way to target and then stalled instead of actually
        # touching it. See config.NEAR_TP_TIMEOUT_* / performance.py's
        # check_near_tp_timeout docstring for the exact rule.
        try:
            near_tp_closed = await asyncio.to_thread(trade_log.check_near_tp_timeout, ticker, live)
        except Exception as exc:
            log.warning("trade_monitor: check_near_tp_timeout failed for %s: %s", ticker, exc)
            continue
        if near_tp_closed:
            log.info("trade_monitor: %d trade(s) closed for %s via near-TP timeout (live=%.4f)",
                      len(near_tp_closed), ticker, live)
            all_newly_closed.extend(near_tp_closed)

    # v2 plan lifecycle tick (flag-gated; no-op while INTRADAY_MANAGER_V2=false)
    from swingbot.core.planning import plan_manager
    try:
        plan_events = await asyncio.to_thread(plan_manager.run_manager_tick)
    except Exception as exc:
        log.warning("trade_monitor: plan manager tick failed: %s", exc)
        plan_events = []
    if plan_events:
        from swingbot.core.scanning.embeds import notify_plan_events
        try:
            await notify_plan_events(bot, plan_events)   # Task 72
        except Exception as exc:
            log.warning("trade_monitor: failed to post plan events: %s", exc)

    if all_newly_closed:
        from swingbot.core.scanning.embeds import notify_closed_trades
        try:
            await notify_closed_trades(bot, all_newly_closed)
        except Exception as exc:
            log.warning("trade_monitor: failed to post close notifications: %s", exc)
        await presence._refresh_presence()


@trade_monitor.error
async def _trade_monitor_error(exc: Exception):
    log.exception("trade_monitor loop escaped -- restarting: %s", exc)
    if not trade_monitor.is_running():
        trade_monitor.restart()


_recap_fired_date: dt.date | None = None   # process-local fast path; persisted below for restart safety
_weekend_scan_fired_date: dt.date | None = None


def _scheduled_jobs_path() -> str:
    """Resolve at call time so config/test data directories remain respected."""
    return os.path.join(config.DATA_DIR, "scheduled_jobs.json")


def _scheduled_job_already_fired(job: str, today: dt.date) -> bool:
    data = read_json(_scheduled_jobs_path(), {})
    return isinstance(data, dict) and data.get(job) == today.isoformat()


def _mark_scheduled_job_fired(job: str, today: dt.date) -> None:
    data = read_json(_scheduled_jobs_path(), {})
    if not isinstance(data, dict):
        data = {}
    data[job] = today.isoformat()
    atomic_write_json(_scheduled_jobs_path(), data)

@tasks.loop(minutes=1)
async def daily_recap():
    """
    Posts the end-of-session retrospective once per weekday, at SESSION_END_HOUR
    (Europe/Berlin) + 15 minutes, so it runs right after the trading session closes.
    Guards against duplicate posts within the same calendar day.
    """
    global _recap_fired_date
    try:
        from zoneinfo import ZoneInfo as _ZI
        now = dt.datetime.now(_ZI("Europe/Berlin"))
    except Exception:
        now = dt.datetime.utcnow()

    # Mon-Fri (0-4): normal end-of-session retrospective. Sunday (6): the
    # retrospective still fires -- its Parts 1-7 (trade tables, lessons)
    # will mostly be empty on a non-trading day, which is expected, and its
    # Sunday-gated Parts 8-10 (weekly risk report E53, RS rotation E81,
    # scan health E82) exist SPECIFICALLY to post here. Excluding weekday()
    # > 4 entirely (the original guard) meant those three already-shipped
    # features could never actually fire from this scheduled loop -- caught
    # while wiring E87's separate Saturday deep-scan job alongside this one.
    # Saturday (5) is deliberately still excluded from THIS loop: it has its
    # own separate job (weekend_deep_scan, Task E87), not a retrospective.
    if now.weekday() == 5:
        return

    today = now.date()
    if _recap_fired_date == today or _scheduled_job_already_fired('daily_recap', today):
        return  # already posted today, including before a process restart

    # Fire at SESSION_END_HOUR:15 Berlin time (15-min grace after session closes)
    trigger_hour   = config.SESSION_END_HOUR
    trigger_minute = 15
    if now.hour != trigger_hour or now.minute < trigger_minute:
        return

    log.info("daily_recap: posting end-of-session retrospective for %s", today)
    _recap_fired_date = today
    _mark_scheduled_job_fired('daily_recap', today)
    try:
        await recap._post_retrospective()
    except Exception as exc:
        log.exception("daily_recap: failed to post retrospective: %s", exc)



@tasks.loop(minutes=1)
async def weekend_deep_scan_task():
    """Task E87: Saturday-only sibling of daily_recap, same minute-resolution
    poll + SESSION_END_HOUR:15 trigger + duplicate-post guard shape, kept as
    its own loop rather than a branch inside daily_recap so a slow/failing
    deep scan can never affect the weekday/Sunday retrospective's own timing."""
    global _weekend_scan_fired_date
    try:
        from zoneinfo import ZoneInfo as _ZI
        now = dt.datetime.now(_ZI("Europe/Berlin"))
    except Exception:
        now = dt.datetime.utcnow()

    if now.weekday() != 5:   # Saturday only
        return

    today = now.date()
    if _weekend_scan_fired_date == today or _scheduled_job_already_fired('weekend_deep_scan', today):
        return

    trigger_hour   = config.SESSION_END_HOUR
    trigger_minute = 15
    if now.hour != trigger_hour or now.minute < trigger_minute:
        return

    log.info("weekend_deep_scan_task: running relaxed-threshold deep scan for %s", today)
    _weekend_scan_fired_date = today
    _mark_scheduled_job_fired('weekend_deep_scan', today)
    try:
        await recap.weekend_deep_scan()
    except Exception:
        log.exception("weekend_deep_scan_task: deep scan failed")

@tasks.loop(minutes=config.MARKET_DATA_REFRESH_MINUTES)
async def market_data_refresh():
    """
    Keeps market_data/{timeframe}/{TICKER}.csv current for the training
    timeframes while the bot runs.

    Cheap by construction: each timeframe carries its own staleness window
    (hourly 4h, daily 12h, weekly/monthly 24h), so most wake-ups fetch
    nothing and return immediately. The actual fetching runs off the event
    loop via asyncio.to_thread -- yfinance is blocking, and a full sweep can
    take minutes under Yahoo throttling, which would otherwise stall every
    Discord command for the duration.

    Time-budgeted (MARKET_DATA_REFRESH_BUDGET_SECONDS) on top of that: a
    large stale backlog (after extended downtime) or a slow/rate-limited
    provider can make even the to_thread-offloaded sweep run long enough to
    starve the Discord gateway heartbeat on a small box and drop the bot's
    connection -- production incident, 2026-08-24. Whatever the budget
    doesn't reach this tick carries its staleness into the next one; nothing
    is lost, the sweep just degrades to "less done per wake" instead of
    "unbounded."

    Failures are logged and counted, never raised: a rate-limited window or
    a single delisted symbol must not kill the loop.
    """
    if not config.MARKET_DATA_AUTO_REFRESH:
        return

    timeframes = [t.strip() for t in
                  str(config.MARKET_DATA_TIMEFRAMES).split(",") if t.strip()]
    symbols = load_watchlist()
    if not timeframes or not symbols:
        return

    try:
        from swingbot.core.marketdata.data_refresh import (
            FAILED_RETRY_HOURS, pending_gaps, refresh_all, summary_line,
        )
        result = await asyncio.to_thread(
            refresh_all, symbols, timeframes, sleep_seconds=0.3,
            deadline_seconds=config.MARKET_DATA_REFRESH_BUDGET_SECONDS,
        )
    except Exception as exc:
        log.exception("market_data_refresh: refresh failed: %s", exc)
        return

    line = summary_line(result)
    if result["failures"]:
        sample = ", ".join(f"{s}/{tf}" for s, tf, _ in result["failures"][:5])
        log.warning("market_data_refresh: %s | %d failure(s): %s%s",
                    line, len(result["failures"]), sample,
                    " ..." if len(result["failures"]) > 5 else "")
    elif line != "all timeframes already fresh":
        log.info("market_data_refresh: %s", line)

    if result.get("deadline_hit"):
        log.warning(
            "market_data_refresh: hit its %ds time budget and stopped early -- "
            "remaining pairs carry over to the next wake.",
            config.MARKET_DATA_REFRESH_BUDGET_SECONDS,
        )

    # Anything still unresolved stays on the books and is re-attempted on the
    # next tick (failed pairs go stale after FAILED_RETRY_HOURS instead of
    # their normal window), so gaps keep being chipped at for as long as the
    # bot runs. Note this covers RECOVERABLE gaps only -- a provider depth cap
    # is a refusal, not a gap, and is never queued for retry.
    gaps = pending_gaps(result.get("state"))
    if gaps:
        worst = sorted(gaps, key=lambda g: -g[2])[:3]
        log.info("market_data_refresh: %d gap(s) queued for retry (~%.1fh): %s",
                 len(gaps), FAILED_RETRY_HOURS,
                 ", ".join(f"{s}/{tf} x{n}" for s, tf, n, _ in worst))


@market_data_refresh.before_loop
async def _before_market_data_refresh():
    # Don't compete with startup: let the bot connect and the first scan
    # settle before a potentially minutes-long network sweep begins.
    await bot.wait_until_ready()
    await asyncio.sleep(60)


def _apply_market_data_refresh_config(changed: dict) -> None:
    if "MARKET_DATA_REFRESH_MINUTES" in changed and market_data_refresh.is_running():
        market_data_refresh.change_interval(minutes=config.MARKET_DATA_REFRESH_MINUTES)
        log.info("Market-data refresh interval hot-reloaded to every %d minute(s).",
                 config.MARKET_DATA_REFRESH_MINUTES)
    if "MARKET_DATA_AUTO_REFRESH" in changed:
        if config.MARKET_DATA_AUTO_REFRESH and not market_data_refresh.is_running():
            market_data_refresh.start()
            log.info("Market-data auto-refresh enabled and started.")
        elif not config.MARKET_DATA_AUTO_REFRESH and market_data_refresh.is_running():
            market_data_refresh.cancel()
            log.info("Market-data auto-refresh disabled and stopped.")


@on_config_reload
def _apply_scan_interval_change(changed: dict):
    """SCAN_INTERVAL_MINUTES is baked into @tasks.loop() at decoration time
    (discord.ext.tasks doesn't re-read it live), so a hot reload needs to
    explicitly push the new interval onto the running loop."""
    if "SCAN_INTERVAL_MINUTES" in changed and session_scan.is_running():
        new_minutes = config.SCAN_INTERVAL_MINUTES
        session_scan.change_interval(minutes=new_minutes)
        log.info("Scan interval hot-reloaded to every %d minute(s) (takes effect next tick).", new_minutes)
    _apply_market_data_refresh_config(changed)


@bot.event
async def on_ready():
    global _ready_announcement_sent
    log.info("Logged in as %s (id=%s)", bot.user, bot.user.id if bot.user else "n/a")
    log.info("Watching %d guild(s): %s", len(bot.guilds), ", ".join(g.name for g in bot.guilds) or "none")
    wl_size = len(load_watchlist())
    log.info(
        "Session window: %02d:00-%02d:00 Europe/Berlin (7 days), scanning every %d min, "
        "%d-scan confirmation, min confidence Lv%d, min %d strategies confirmed (within %.1f%% deviation), "
        "watchlist size %d",
        config.SESSION_START_HOUR, config.SESSION_END_HOUR, config.SCAN_INTERVAL_MINUTES,
        config.SIGNAL_CONFIRMATION_SCANS, config.MIN_ALERT_CONFIDENCE_LEVEL, config.MIN_TARGET_CONFLUENCE_COUNT,
        config.CONFLUENCE_DEVIATION_PCT, wl_size,
    )
    install_reload_signal_handler()
    if not session_scan.is_running():
        session_scan.start()
    if not heartbeat.is_running():
        heartbeat.start()
    if not config_watcher.is_running():
        config_watcher.start()
    if not trade_monitor.is_running():
        trade_monitor.start()
    if not daily_recap.is_running():
        daily_recap.start()
    if not weekend_deep_scan_task.is_running():
        weekend_deep_scan_task.start()
    if config.MARKET_DATA_AUTO_REFRESH and not market_data_refresh.is_running():
        market_data_refresh.start()
    await presence._refresh_presence()

    if _ready_announcement_sent:
        return
    _ready_announcement_sent = True

    # Sync slash commands and announce only once per process startup.
    try:
        synced = await bot.tree.sync()
        log.info("Synced %d slash command(s) to Discord.", len(synced))
    except Exception as e:
        log.warning("Failed to sync slash commands: %s", e)

    # Post a startup notice to the alerts channel so there's a visible
    # timestamp in Discord for when the bot came (back) online.
    if config.DISCORD_CHANNEL_TRADES_ID:
        channel = silence(bot.get_channel(int(config.DISCORD_CHANNEL_TRADES_ID)))
        if channel:
            open_count = trade_log.get_stats()["open"]
            await channel.send(
                f"🤖 **Bot online** — {dt.datetime.now(SESSION_TZ).strftime('%Y-%m-%d %H:%M %Z')}\n"
                f"Session: {config.SESSION_START_HOUR:02d}:00–{config.SESSION_END_HOUR:02d}:00 Berlin · "
                f"scan every {config.SCAN_INTERVAL_MINUTES} min · watchlist: {wl_size} ticker(s) · "
                f"open trades: {open_count} · min confidence: Lv{config.MIN_ALERT_CONFIDENCE_LEVEL}"
            )
