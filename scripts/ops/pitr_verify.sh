#!/usr/bin/env bash
# Monthly proof that both PITR repos are readable (v116 Phase 0):
# `pgbackrest verify` and `restic check`. Ends with one VERDICT line.
# Installed by install_pitr_crons.sh; logs to logs/pitr_verify.log.
set -uo pipefail
cd "$(dirname "$0")/../.."

rc=0
echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) pitr verify ==="
docker compose exec -T -u postgres db pgbackrest --stanza=swingbot verify </dev/null || rc=1
RESTIC_PASSWORD="$(python3 scripts/ops/env_set.py --get RESTIC_PASSWORD)" || RESTIC_PASSWORD=""
if [ -z "$RESTIC_PASSWORD" ]; then
  echo "pitr_verify: RESTIC_PASSWORD is not set in .env" >&2
  rc=1
else
  export RESTIC_PASSWORD
  export RESTIC_REPOSITORY="$PWD/backups/restic"
  restic check || rc=1
fi
if [ "$rc" = 0 ]; then
  echo "VERDICT $(date -u +%F) PASS"
else
  echo "VERDICT $(date -u +%F) FAIL"
fi
exit "$rc"
