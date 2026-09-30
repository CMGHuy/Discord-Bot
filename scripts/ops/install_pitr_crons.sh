#!/usr/bin/env bash
# Installs (idempotently) the v116 PITR crons on the Hetzner VM. Run ON the
# VM as root, from a dev machine via:
#   bash scripts/ops/ssh-hetzner.sh "bash -s" < scripts/ops/install_pitr_crons.sh
# backup_db.sh's own 03:00 line (installed 2026-09-30) is left alone.
set -euo pipefail

MARKER='# v116 PITR (installed by install_pitr_crons.sh)'
BASE=/opt/swing-bot
chmod +x "$BASE/scripts/ops/pitr_backup.sh" "$BASE/scripts/ops/restic_hourly.sh" \
         "$BASE/scripts/ops/pitr_verify.sh"
{
  crontab -l 2>/dev/null | grep -vF "$MARKER" \
    | grep -vE 'pitr_backup\.sh|restic_hourly\.sh|pitr_verify\.sh' || true
  echo "$MARKER"
  echo "30 2 * * * $BASE/scripts/ops/pitr_backup.sh >> $BASE/logs/pitr_backup.log 2>&1"
  echo "7 * * * * $BASE/scripts/ops/restic_hourly.sh >> $BASE/logs/restic.log 2>&1"
  echo "0 4 1 * * $BASE/scripts/ops/pitr_verify.sh >> $BASE/logs/pitr_verify.log 2>&1"
} | crontab -

echo "Installed crontab:"
crontab -l
