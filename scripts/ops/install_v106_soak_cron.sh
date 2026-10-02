#!/usr/bin/env bash
# Installs (idempotently) a weekday crontab entry on the Hetzner VM that runs
# scripts/ops/v106_soak_cron.sh at 21:15 UTC, after the US close, for v106
# soak (plan docs/superpowers/plans/2026-09-26-v106-alpaca-data-provider.md,
# T13 Step 6, window given as START END). Read-only checks;
# the next Claude session reads logs/v106_soak_cron.log and acts on the FINAL
# verdict. The job removes its own line after the END-day run.
#
# Run ON the VM, e.g. from a dev machine:
#   ./scripts/ops/ssh-hetzner.sh "bash -s -- START END" < scripts/ops/install_v106_soak_cron.sh
# START/END = the soak window's first and last trading day (UTC dates).
set -euo pipefail
START=${1:-2026-10-01}
END=${2:-2026-10-07}

MARKER='# v106 soak check (installed by install_v106_soak_cron.sh)'
CRON_LINE="15 21 * * 1-5 /bin/bash /opt/swing-bot/scripts/ops/v106_soak_cron.sh $START $END"

{
    crontab -l 2>/dev/null | grep -vF "$MARKER" | grep -vF "v106_soak_cron.sh" || true
    echo "$MARKER"
    echo "$CRON_LINE"
} | crontab -

echo "Installed crontab:"
crontab -l
