#!/usr/bin/env bash
# Installs (idempotently) a ONE-SHOT crontab entry on the Hetzner VM that runs
# scripts/ops/v91_dual_check.sh at 21:00 UTC on 1 October (an hour after the
# US close), so the v91 P91-06 Step 3 divergence check happens with the laptop
# shut down. The check removes its own line when it finishes.
#
# Run this ON the VM as root, from a dev machine via:
#   ./scripts/ops/ssh-hetzner.sh "bash -s" < scripts/ops/install_v91_dual_check_cron.sh
set -euo pipefail

MARKER='# v91 dual-stage check, one-shot (installed by install_v91_dual_check_cron.sh)'
CRON_LINE='0 21 1 10 * /opt/swing-bot/scripts/ops/v91_dual_check.sh'

chmod +x /opt/swing-bot/scripts/ops/v91_dual_check.sh
{
    crontab -l 2>/dev/null | grep -vF "$MARKER" | grep -vF "v91_dual_check" || true
    echo "$MARKER"
    echo "$CRON_LINE"
} | crontab -

echo "Installed crontab:"
crontab -l
