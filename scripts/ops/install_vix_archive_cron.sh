#!/usr/bin/env bash
# Installs (idempotently) a weekday crontab entry on the Hetzner VM that runs
# scripts/ops/archive_vix.py inside the bot container at 22:30 UTC (after the
# US close in both DST regimes) and appends output to logs/vix_archive_cron.log.
#
# Run ON the VM as root, e.g.:
#   bash scripts/ops/ssh-hetzner.sh "bash -s" < scripts/ops/install_vix_archive_cron.sh
set -euo pipefail

MARKER='# v222 VIX archive (installed by install_vix_archive_cron.sh)'
CRON_LINE='30 22 * * 1-5 cd /opt/swing-bot && { echo "=== $(date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ) ==="; /usr/bin/docker compose exec -T bot python scripts/ops/archive_vix.py; } >> /opt/swing-bot/logs/vix_archive_cron.log 2>&1'

{
    crontab -l 2>/dev/null | grep -vF "$MARKER" | grep -vF "archive_vix.py" || true
    echo "$MARKER"
    echo "$CRON_LINE"
} | crontab -

echo "Installed crontab:"
crontab -l
