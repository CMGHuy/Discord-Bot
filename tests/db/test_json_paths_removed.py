"""No migrated store keeps a JSON read or write path (v116 Phase 4).
Each Phase 4 task adds its group's rows; V116-39 adds the global ones."""
import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]

#: (file, pattern that must not appear, why)
FORBIDDEN = [
    # ops group (V116-35)
    ("swingbot/commands/scanning/runstate.py", r"stages\.|\.flag\"|_HEARTBEAT_FILE|_MANUAL_CLOSE_QUEUE", "flags, heartbeat, notify_queue are tables"),
    ("swingbot/core/scanning/runstate.py", r"stages\.|\.flag\"", "flags are a table"),
    ("swingbot/commands/scanning/loops.py", r"stages\.\w+\(\"(scheduled_jobs|notify_queue)\"\)|scheduled_jobs\.json|_MANUAL_CLOSE_QUEUE", "scheduled_jobs, notify_queue are tables"),
    ("swingbot/admin/api_v1/trade_commands.py", r"stages\.|manual_close_notify\.json", "notify_queue is a table"),
    ("swingbot/core/edge/throttle.py", r"stages\.|KILLSWITCH_PATH|killswitch\.json", "killswitch is a table"),
    ("swingbot/admin/jobs.py", r"stages\.\w+\(\"jobs\"\)|admin_jobs\.json", "jobs is a table"),
    ("swingbot/admin/api_v1/jobs.py", r"stages\.\w+\(\"jobs\"\)", "jobs is a table"),
    ("swingbot/core/scanning/progress_store.py", r"stages\.|scan_progress\.json", "scan_progress is a table"),
    ("swingbot/core/marketdata/data_refresh.py", r"stages\.|market_data_state\.json|STATE_FILE", "market_data_state is a table"),
    ("swingbot/admin/app.py", r"stages\.\w+\(\"heartbeat\"\)|bot_heartbeat\.json", "heartbeat is a table"),
    # reference group (V116-36)
    ("swingbot/core/marketdata/watchlist.py", r"stages\.|watchlist\.json", "watchlist is a table"),
    ("swingbot/core/marketdata/ticker_directory.py", r"stages\.|ticker_directory\.json", "ticker_directory is a table"),
    ("swingbot/core/infra/state.py", r"stages\.|state\.json|_save\(", "signal_state is a table"),
    ("swingbot/admin/helpers.py", r"stages\.|settings_audit\.jsonl", "settings_audit is a table"),
    ("swingbot/admin/api_v1/system.py", r"stages\.|ui_preferences\.json", "preferences is a table"),
    ("swingbot/admin/jobs.py", r"stages\.|tuning_results", "tuning is a table"),
    ("swingbot/admin/api_v1/jobs.py", r"stages\.|tuning_results", "tuning is a table"),
    ("swingbot/admin/queries.py", r"stages\.|TUNING_PROPOSALS_DIR_NAME", "tuning_proposals is a table"),
    # trading group (V116-37)
    ("swingbot/core/tracking/performance.py", r"stages\.|trades\.json|def reload|def refresh|\.refresh\(\)|self\._trades", "trades is a table; no snapshot to refresh"),
    ("swingbot/core/planning/plan_store.py", r"stages\.|plans\.json|def reload|self\._plans", "plans is a table; no snapshot to reload"),
    ("swingbot/core/planning/plan_manager.py", r"stages\.|\.reload\(\)", "no snapshot to reload"),
    ("swingbot/core/planning/account.py", r"stages\.|account\.json|trades\.json|_read_trades_file", "account and trades are tables"),
    ("swingbot/core/analytics/journal.py", r"stages\.|journal\.json", "journal is a table"),
    ("swingbot/commands/views.py", r"stages\.|starred_plans\.json", "starred_plans is a table"),
    ("swingbot/admin/watchlist_rows.py", r"stages\.", "plans is a table"),
    ("swingbot/admin/events/broker.py", r"FileWatcher|residual_paths|_CompositeWatcher|stages\.", "the admin listens to Postgres only"),
]


@pytest.mark.parametrize("path,pattern,why", FORBIDDEN, ids=[f"{p}:{w}" for p, _r, w in FORBIDDEN])
def test_no_json_path_remains(path, pattern, why):
    text = (REPO / path).read_text(encoding="utf-8")
    hits = [f"{n}: {line.strip()}" for n, line in enumerate(text.splitlines(), 1)
            if re.search(pattern, line)]
    assert not hits, f"{path} still has a JSON path ({why}):\n" + "\n".join(hits)
