#!/usr/bin/env bash
# Nightly pgBackRest backup (v116 Phase 0): full on Sundays, differential on
# other days. pgBackRest applies repo1-retention-full=30 (time-based) itself,
# keeping 30 days of point-in-time history. Then .env versions older than 30
# days are pruned (the newest of them is kept: it was live when the window
# opened). Installed by install_pitr_crons.sh; logs to logs/pitr_backup.log.
set -euo pipefail
cd "$(dirname "$0")/../.."
trap 'echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) pitr_backup FAILED (line $LINENO) ===" >&2' ERR

TYPE=diff
if [ "$(date -u +%u)" = "7" ]; then
  TYPE=full
fi
echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) pgbackrest ${TYPE} ==="
docker compose exec -T -u postgres db pgbackrest --stanza=swingbot --type="$TYPE" backup </dev/null
python3 -m swingbot.core.infra.env_snapshot prune backups/env 30
echo "=== done ==="
