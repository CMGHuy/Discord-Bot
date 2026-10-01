#!/usr/bin/env bash
# Nightly v116 Phase 3 soak check, run BY CRON ON THE VM at 22:15 UTC Mon-Fri
# (after the US close). Counts database error lines in the last 24 h of the
# bot and admin logs, runs parity for every group not at json, and appends
# one block per run to logs/v116_parity.log. Read-only against the stores.
# The gate tasks read the log with `scripts/ops/v116_soak.py gate`.
set -uo pipefail
cd /opt/swing-bot || exit 1
LOG=/opt/swing-bot/logs/v116_parity.log
PATTERN='dual\[|sqlalchemy\.exc\.|psycopg\.|DatabaseUnavailable|StoreWriteHalt'

{
  echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) v116 soak check ==="
  ERRORS=$(docker compose logs --since 24h bot admin </dev/null 2>&1 | grep -cE "$PATTERN")
  echo "--- database error lines, last 24h: ${ERRORS} (first 20) ---"
  docker compose logs --since 24h bot admin </dev/null 2>&1 | grep -E "$PATTERN" | head -20
  docker compose exec -T bot python scripts/ops/v116_soak.py check --error-lines "$ERRORS" </dev/null 2>&1
} >> "$LOG" 2>&1
