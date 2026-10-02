"""Which table raises which SSE concern.

One event type per *concern*, not per table -- several tables raise the same
event and the client never learns the storage layout. This is the taxonomy the
former file watcher encoded, restated against tables so the SPA contract survives the storage change untouched.
"""

TABLE_CHANNELS: dict[str, str] = {
    # Live trading state (Part 2)
    "trades": "trades",
    "plans": "trades",
    "starred_plans": "trades",
    "manual_close_notify": "trades",
    "account": "account",
    "account_balance_history": "account",
    "signal_state": "account",
    "journal_entries": "journal",
    "watchlist": "watchlist",
    # Operational state (Part 3)
    "runtime_flags": "scan",
    "bot_heartbeat": "bot",
    "killswitch": "risk",
    "admin_jobs": "jobs",
    "scheduled_jobs": "jobs",
    "ui_preferences": "jobs",
    "tuning_results": "jobs",
    "tuning_proposals": "jobs",
    "ticker_directory": "watchlist",
    "settings_audit": "settings",
    # v116 Phase 1. market_data_state drove no event as a file; its trigger
    # raises `watchlist`, the concern whose rows show data freshness.
    "scan_progress": "scan",
    "market_data_state": "watchlist",
}

from swingbot.core.db.notify import CHANNELS  # noqa: E402

#: The SPA's event contract: every name the stream can send besides `resync`
#: and `ping`. Formerly the file watcher's WATCHED_EVENTS.
SSE_EVENTS = frozenset(CHANNELS)

#: Sources that stay files (spec § Out) and raise their concern themselves
#: through notify.publish -- the watcher that stat()ed them is gone (v116).
FILE_PUBLISHERS: dict[str, str] = {
    "data/analytics_snapshot.json (analytics.snapshots.save_snapshot)": "analytics",
    "data/scan_snapshots.json (scanning.snapshots._save_scan_snapshots)": "scan",
    "data/scan_telemetry.jsonl (scanning.telemetry.log_scan_telemetry)": "scan",
    ".env (admin.helpers._write_env_text, scripts/ops/env_set.py)": "settings",
}
