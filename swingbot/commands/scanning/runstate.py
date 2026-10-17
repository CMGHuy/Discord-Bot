import datetime as dt
import logging

from swingbot.bot_core import in_session
from swingbot.core.infra import swallowed as swallowed_mod
from swingbot.core.infra.swallowed import swallowed

log = logging.getLogger(__name__)


def _read_heartbeat() -> dict:
    """Current heartbeat state, or {} when absent or unreadable.

    Absent is "unknown", never "failing"."""
    try:
        from swingbot.core.db.repositories.heartbeat import heartbeat_repo
        return heartbeat_repo().last() or {}
    except Exception as exc:
        swallowed(log, "runstate.read_heartbeat", exc, level=logging.DEBUG)
        return {}


def _update_heartbeat(fields: dict) -> None:
    """Merge `fields` into the heartbeat row key by key (`doc || fields` in
    SQL, v148): no read first, so the bot and the admin never write a stale
    whole-doc view over each other's keys. A failed write is counted and
    logged, never raised -- the heartbeat must not take down a tick."""
    try:
        from swingbot.core.db.repositories.heartbeat import heartbeat_repo
        heartbeat_repo().merge(fields)
    except Exception as exc:
        swallowed(log, "runstate.update_heartbeat", exc, "heartbeat write failed")


def _write_heartbeat() -> None:
    """
    Stamps the bot_heartbeat row that the admin UI reads to show a blinking
    bot-liveness dot on the Dashboard, and flushes this process's
    swallowed-error counts (v148 O5) for the System → Scan panel. Written
    on every session_scan tick (including off-hours / paused ticks) so the
    dot goes dark only when the bot process itself stops responding, not
    just because it's outside the trading session window.

    This is LIVENESS ONLY, and it is written before the tick does any work --
    so on its own it cannot distinguish "working" from "crashing every tick",
    which is exactly how a five-day alert blackout went unnoticed. Tick
    OUTCOME is record_tick_success() / record_tick_failure() below.
    """
    _update_heartbeat({
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "session_active": in_session(),
        "scan_paused": is_scan_paused(),
        "swallowed": {"since": swallowed_mod.STARTED_AT,
                      "counts": swallowed_mod.snapshot()},
    })


def record_tick_success() -> bool:
    """Mark the tick as completed. Returns True iff this clears an active
    alert -- i.e. the caller should post a recovery notice."""
    was_alerting = bool(_read_heartbeat().get("alert_active"))
    _update_heartbeat({
        "last_success": dt.datetime.now(dt.timezone.utc).isoformat(),
        "consecutive_failures": 0,
        "alert_active": False,
    })
    return was_alerting


def record_tick_failure() -> int:
    """Mark the tick as failed. Returns the new consecutive-failure count.

    Persisted rather than held in memory so a crash-looping container that
    restarts does not reset its own outage counter.
    """
    failures = int(_read_heartbeat().get("consecutive_failures") or 0) + 1
    _update_heartbeat({"consecutive_failures": failures})
    return failures


def get_alert_active() -> bool:
    return bool(_read_heartbeat().get("alert_active"))


def set_alert_active(active: bool) -> None:
    _update_heartbeat({"alert_active": bool(active)})


def get_stale_alert_active() -> bool:
    """v148 O3: a stale-scan alert is open (ops_watch.scan_watchdog). Kept in
    the heartbeat row so a restart neither re-posts nor forgets it."""
    return bool(_read_heartbeat().get("stale_alert_active"))


def set_stale_alert_active(active: bool) -> None:
    _update_heartbeat({"stale_alert_active": bool(active)})


def get_provider_alert_active() -> bool:
    """v148 O4: a provider-degradation alert is open (ops_watch.check_provider_health)."""
    return bool(_read_heartbeat().get("provider_alert_active"))


def set_provider_alert_active(active: bool) -> None:
    _update_heartbeat({"provider_alert_active": bool(active)})


def last_success_iso() -> str | None:
    return _read_heartbeat().get("last_success")


def record_store_write_failure(exc: Exception) -> None:
    """v116: mark the heartbeat so the admin shows the halt until unpaused."""
    _update_heartbeat({"store_write_failure": {
        "at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "error": f"{type(exc).__name__}: {str(exc)[:300]}",
    }})


def is_scan_paused() -> bool:
    """Whether the automatic background scan loop is currently paused
    (via the admin UI toggle or the !pause command). Manual scans
    (!check, and the admin UI's "Run !check now" trigger) are NOT
    affected by this -- pausing only stops the unattended, scheduled
    scanning so the user can still check on demand."""
    from swingbot.core.db.repositories.flags import flags_repo
    return flags_repo().is_set("scan_paused")


def set_scan_paused(paused: bool) -> None:
    from swingbot.core.db.repositories.flags import flags_repo
    repo = flags_repo()
    repo.set("scan_paused") if paused else repo.clear("scan_paused")
    if not paused:
        # Unpausing is the partner's acknowledgement of a store-write halt.
        _update_heartbeat({"store_write_failure": None})


def scan_paused_at() -> str | None:
    """When the scan pause was raised (the row's set_at), or None."""
    from swingbot.core.db.repositories.flags import flags_repo
    return flags_repo().set_at("scan_paused")


def trigger_requested_at() -> str | None:
    from swingbot.core.db.repositories.flags import flags_repo
    return flags_repo().set_at("trigger_check")


def is_trigger_requested() -> bool:
    from swingbot.core.db.repositories.flags import flags_repo
    return flags_repo().is_set("trigger_check")


def request_trigger() -> None:
    """Queue a manual scan. The row stores only the flag and its set_at."""
    from swingbot.core.db.repositories.flags import flags_repo
    flags_repo().set("trigger_check")


def clear_trigger() -> None:
    from swingbot.core.db.repositories.flags import flags_repo
    flags_repo().clear("trigger_check")
