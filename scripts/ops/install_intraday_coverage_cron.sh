#!/usr/bin/env bash
# Installs (idempotently) a daily crontab entry on the Hetzner VM that runs
# scripts/ops/intraday_archive_coverage.py inside the bot container and
# appends timestamped output to logs/intraday_coverage_cron.log.
#
# Added for plan v87 (docs/superpowers/plans/2026-09-15-v87-intraday-bar-archive.md)
# Task IA7 Step 4, the one-week done-condition check: this gives a coverage
# reading every day regardless of whether a Claude session is open to run
# the check manually on the exact day.
#
# Run this ON the VM as root, e.g. from a dev machine via:
#   ./scripts/ops/ssh-hetzner.sh "bash -s" < scripts/ops/install_intraday_coverage_cron.sh
#
# Safe to re-run: it replaces any prior line this script installed rather
# than appending a duplicate.
set -euo pipefail

MARKER='# v87 intraday archive coverage (installed by install_intraday_coverage_cron.sh)'
CRON_LINE='7 6 * * * cd /opt/swing-bot && { echo "=== $(date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ) ==="; /usr/bin/docker compose exec -T bot python scripts/ops/intraday_archive_coverage.py; } >> /opt/swing-bot/logs/intraday_coverage_cron.log 2>&1'

{
    crontab -l 2>/dev/null | grep -vF "$MARKER" | grep -vF "intraday_archive_coverage.py" || true
    echo "$MARKER"
    echo "$CRON_LINE"
} | crontab -

echo "Installed crontab:"
crontab -l
