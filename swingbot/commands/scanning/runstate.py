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


def _write_heartbeat() -> None:
    """
    Stamps a small JSON file that the admin UI reads to show a blinking
    green/red bot-liveness dot on the Dashboard. Written on every
    session_scan tick (including off-hours / paused ticks) so the dot
    goes red only when the bot process itself stops responding, not just
    because it's outside the trading session window.
    """
    try:
        os.makedirs(config.DATA_DIR, exist_ok=True)
        with open(_HEARTBEAT_FILE, "w") as fh:
            json.dump({
                "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
                "session_active": in_session(),
                "scan_paused": is_scan_paused(),
            }, fh)
    except Exception:
        pass


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
