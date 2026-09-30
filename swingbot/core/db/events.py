"""Which table raises which SSE concern.

One event type per *concern*, not per table -- several tables raise the same
event and the client never learns the storage layout. This is the same taxonomy
swingbot/admin/events/watcher.py's _DATA_PATHS encodes today, restated against
tables so the SPA contract survives the storage change untouched.
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
    # `analytics` and Part 5's tables are added by that part.
}
