#!/usr/bin/env bash
# One-shot v91 P91-06 Step 3 check, run BY CRON ON THE VM after the first full
# trading day at DB_STORES=watchlist:dual,state:dual: greps the bot log for
# JSON-vs-database divergence, re-runs parity for both stores, appends the
# result to logs/v91_dual_check.log, then removes its own cron line.
#
# Installed by install_v91_dual_check_cron.sh. Read-only against the stores.
# Resume the plan (P91-07) from the log's VERDICT line.
set -uo pipefail
cd /opt/swing-bot || exit 1
LOG=/opt/swing-bot/logs/v91_dual_check.log

{
    echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) v91 dual check ==="
    echo "--- divergence lines, last 24h (expected: none) ---"
    docker compose logs --since 24h bot </dev/null 2>&1 | grep -iE "divergen" | head -40
    echo "--- stages ---"
    docker compose exec -T bot python -c "from swingbot.core.db import stages; print(stages.stage_for('watchlist'), stages.stage_for('state'), stages.stage_for('trades'))" </dev/null 2>&1
    rc=0
    for store in watchlist state; do
        echo "--- parity: ${store} ---"
        docker compose exec -T bot python scripts/db/parity_report.py --store "$store" </dev/null 2>&1 | tail -6
        [ "${PIPESTATUS[0]}" != "0" ] && rc=1
    done
    echo "--- VERDICT: $([ "$rc" = 0 ] && echo 'parity OK (check the divergence section is empty)' || echo 'PARITY FAILED') ---"
} >> "$LOG" 2>&1

crontab -l 2>/dev/null | grep -vF "v91_dual_check" | crontab -
