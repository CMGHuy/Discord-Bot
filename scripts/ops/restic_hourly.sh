#!/usr/bin/env bash
# Hourly restic snapshot of market_data/ (v116 Phase 0), then forget
# snapshots older than 30 days. The repo is local (backups/restic): this
# protects against a bad refresh or a bad rollback, not against losing the VM
# (spec § Honest limits). Installed by install_pitr_crons.sh.
set -euo pipefail
cd "$(dirname "$0")/../.."
trap 'echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) restic_hourly FAILED (line $LINENO) ===" >&2' ERR

RESTIC_PASSWORD="$(python3 scripts/ops/env_set.py --get RESTIC_PASSWORD)"
if [ -z "$RESTIC_PASSWORD" ]; then
  echo "restic_hourly: RESTIC_PASSWORD is not set in .env" >&2
  exit 1
fi
export RESTIC_PASSWORD
export RESTIC_REPOSITORY="$PWD/backups/restic"

echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) restic backup market_data ==="
restic backup --host swing-bot --tag market_data "$PWD/market_data"
# v120: restic keeps a snapshot if ANY keep policy matches, so snapshots tagged stable outlive the 30d window
restic forget --host swing-bot --tag market_data --keep-within 30d --keep-tag stable --prune
