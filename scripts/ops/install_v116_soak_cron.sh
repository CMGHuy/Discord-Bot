#!/usr/bin/env bash
# Installs (idempotently) the v116 soak cron on the Hetzner VM. Run ON the VM:
#   bash scripts/ops/ssh-hetzner.sh "bash -s" < scripts/ops/install_v116_soak_cron.sh
# Removed by V116-42 once Phase 4 ships.
set -euo pipefail
MARKER='# v116 soak check (installed by install_v116_soak_cron.sh)'
chmod +x /opt/swing-bot/scripts/ops/v116_parity_check.sh
{
  crontab -l 2>/dev/null | grep -vF "$MARKER" | grep -vF "v116_parity_check" || true
  echo "$MARKER"
  echo "15 22 * * 1-5 /opt/swing-bot/scripts/ops/v116_parity_check.sh"
} | crontab -
crontab -l
