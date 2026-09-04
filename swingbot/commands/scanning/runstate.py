import datetime as dt
import json
import os

from swingbot import config
from swingbot.bot_core import in_session


_TRIGGER_FILE         = os.path.join(config.DATA_DIR, "trigger_check.flag")
# Queue file written by the admin UI when a trade is manually closed.
# Each line is a JSON-encoded trade record; the bot drains it and posts
# to DISCORD_CHANNEL_TRADES_HISTORY_ID, then deletes the file.
_MANUAL_CLOSE_QUEUE   = os.path.join(config.DATA_DIR, "manual_close_notify.json")
_PAUSE_FILE = os.path.join(config.DATA_DIR, "scan_paused.flag")
_HEARTBEAT_FILE = os.path.join(config.DATA_DIR, "bot_heartbeat.json")


def _read_heartbeat() -> dict:
    """Current heartbeat state, or {} when absent or unreadable.

    Absent is "unknown", never "failing" -- an upgraded admin container reads
    files written by a bot that has not restarted yet.
    """
    try:
        with open(_HEARTBEAT_FILE) as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _update_heartbeat(fields: dict) -> None:
    """Merge `fields` into the heartbeat file, preserving everything else."""
    state = _read_heartbeat()
    state.update(fields)
    try:
        os.makedirs(config.DATA_DIR, exist_ok=True)
        with open(_HEARTBEAT_FILE, "w") as fh:
            json.dump(state, fh)
    except Exception:
        pass


def _write_heartbeat() -> None:
    """
    Stamps a small JSON file that the admin UI reads to show a blinking
    bot-liveness dot on the Dashboard. Written on every session_scan tick
    (including off-hours / paused ticks) so the dot goes dark only when the
    bot process itself stops responding, not just because it's outside the
    trading session window.

    This is LIVENESS ONLY, and it is written before the tick does any work --
    so on its own it cannot distinguish "working" from "crashing every tick",
    which is exactly how a five-day alert blackout went unnoticed. Tick
    OUTCOME is record_tick_success() / record_tick_failure() below.
    """
    _update_heartbeat({
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "session_active": in_session(),
        "scan_paused": is_scan_paused(),
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


def last_success_iso() -> str | None:
    return _read_heartbeat().get("last_success")


def is_scan_paused() -> bool:
    """Whether the automatic background scan loop is currently paused
    (via the admin UI toggle or the !pause command). Manual scans
    (!check, and the admin UI's "Run !check now" trigger) are NOT
    affected by this -- pausing only stops the unattended, scheduled
    scanning so the user can still check on demand."""
    return os.path.exists(_PAUSE_FILE)


def set_scan_paused(paused: bool) -> None:
    os.makedirs(config.DATA_DIR, exist_ok=True)
    if paused:
        with open(_PAUSE_FILE, "w") as f:
            f.write(dt.datetime.now(dt.timezone.utc).isoformat())
    else:
        try:
            os.remove(_PAUSE_FILE)
        except OSError:
            pass  # already resumed by a parallel caller
