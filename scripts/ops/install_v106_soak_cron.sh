#!/usr/bin/env bash
# Installs (idempotently) a weekday crontab entry on the Hetzner VM that runs
# scripts/ops/v106_soak_cron.sh at 21:15 UTC, after the US close, for v106
# soak attempt 2 (plan docs/superpowers/plans/2026-09-26-v106-alpaca-data-provider.md,
# T13a Step 6 / T13 Step 6, window 2026-10-01 .. 2026-10-07). Read-only checks;
# the next Claude session reads logs/v106_soak_cron.log and acts on the FINAL
# verdict. The job removes its own line after the 2026-10-07 run.
#
# Run ON the VM, e.g. from a dev machine:
#   ./scripts/ops/ssh-hetzner.sh "bash -s" < scripts/ops/install_v106_soak_cron.sh
set -euo pipefail

MARKER='# v106 soak attempt 2 check (installed by install_v106_soak_cron.sh)'
CRON_LINE='15 21 * * 1-5 /bin/bash /opt/swing-bot/scripts/ops/v106_soak_cron.sh'

{
    crontab -l 2>/dev/null | grep -vF "$MARKER" | grep -vF "v106_soak_cron.sh" || true
    echo "$MARKER"
    echo "$CRON_LINE"
} | crontab -

echo "Installed crontab:"
crontab -l
