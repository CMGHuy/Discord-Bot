#!/usr/bin/env bash
# Installs (idempotently) the v116 PITR crons on the Hetzner VM. Run ON the
# VM as root, from a dev machine via:
#   bash scripts/ops/ssh-hetzner.sh "bash -s" < scripts/ops/install_pitr_crons.sh
# backup_db.sh's own 03:00 line (installed 2026-09-30) is left alone.
set -euo pipefail

MARKER='# v116 PITR (installed by install_pitr_crons.sh)'
BASE="${BASE:-/opt/swing-bot}"
mkdir -p "$BASE/logs"
# One lock per repo: restic_hourly and pitr_verify share the restic repo (its
# own lock would make an overlap fail); pgbackrest gets a separate one.
# flock -n -E 199 skips an overlapping run and exits 199, which is logged. 199 is
# a code the wrapped scripts never produce (they exit 0/1), so a real failure
# can never be mistaken for a lock skip.
skip() { echo "[ \$? -eq 199 ] && echo \"\$(date -u) skipped: previous run still holding lock\" >> $1"; }
cronline() {  # schedule script lock log
  echo "$1 flock -n -E 199 $BASE/logs/$3.lock $BASE/scripts/ops/$2 >> $BASE/logs/$4 2>&1; $(skip "$BASE/logs/$4")"
}
chmod +x "$BASE/scripts/ops/pitr_backup.sh" "$BASE/scripts/ops/restic_hourly.sh" \
         "$BASE/scripts/ops/pitr_verify.sh"
{
  crontab -l 2>/dev/null | grep -vF "$MARKER" \
    | grep -vE 'pitr_backup\.sh|restic_hourly\.sh|pitr_verify\.sh' || true
  echo "$MARKER"
  cronline "30 2 * * *" pitr_backup.sh pitr_backup pitr_backup.log
  cronline "7 * * * *" restic_hourly.sh restic restic.log
  cronline "0 4 1 * *" pitr_verify.sh restic pitr_verify.log
} | crontab -

echo "Installed crontab:"
crontab -l
