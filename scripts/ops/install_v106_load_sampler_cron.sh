#!/usr/bin/env bash
# Installs (idempotently) a crontab entry on the Hetzner VM that runs
# scripts/ops/v106_load_sampler.sh every minute 13:00-20:59 UTC on weekdays,
# for the v106 (a) slowdown diagnosis. The sampler itself only acts on the
# START..END dates and removes its own line after END. Read-only.
#
# Run ON the VM, e.g. from a dev machine:
#   ./scripts/ops/ssh-hetzner.sh "bash -s -- START END" < scripts/ops/install_v106_load_sampler_cron.sh
set -euo pipefail
START=${1:-$(date -u +%Y-%m-%d)}
END=${2:-$START}

MARKER='# v106 load sampler (installed by install_v106_load_sampler_cron.sh)'
CRON_LINE="* 13-20 * * 1-5 /bin/bash /opt/swing-bot/scripts/ops/v106_load_sampler.sh $START $END"

{
    crontab -l 2>/dev/null | grep -vF "$MARKER" | grep -vF "v106_load_sampler.sh" || true
    echo "$MARKER"
    echo "$CRON_LINE"
} | crontab -

echo "Installed crontab:"
crontab -l
