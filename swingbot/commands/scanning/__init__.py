"""Discord command layer for scanning.

Split from the 1824-line commands/scanning.py on 2026-08-25 (v61). This
facade re-exports the external surface and imports every submodule so command
and loop decorator registration fires when the package is imported.
"""
from . import alerts, commands, loops, presence, recap, runstate  # noqa: F401

from .alerts import _ordered_alerts, _send_alerts, cap_alerts, deep_scan_report, digest_payload, route_channel_id
from .commands import check_cmd
from .loops import (
    config_watcher,
    daily_recap,
    heartbeat,
    market_data_refresh,
    on_ready,
    session_scan,
    trade_monitor,
    weekend_deep_scan_task,
)
from .recap import weekend_deep_scan
from .runstate import _HEARTBEAT_FILE, _MANUAL_CLOSE_QUEUE, _PAUSE_FILE, _TRIGGER_FILE, is_scan_paused, set_scan_paused

__all__ = [
    "is_scan_paused", "set_scan_paused",
    "_ordered_alerts", "digest_payload", "cap_alerts", "route_channel_id",
    "deep_scan_report", "_send_alerts", "check_cmd", "weekend_deep_scan",
    "session_scan", "heartbeat", "config_watcher", "trade_monitor",
    "daily_recap", "weekend_deep_scan_task", "market_data_refresh", "on_ready",
]
