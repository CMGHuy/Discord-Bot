#!/usr/bin/env bash
# Installs (idempotently) the v162 weekly crontab entry on the Hetzner VM:
# Sunday 06:30 UTC, `fetch_alpaca_history.py --mode update` in its own
# container (`compose run --rm`, never `exec` into the CPU-capped live bot),
# then `check_history_store.py --verify-hashes`. Both exit codes are logged
# to logs/history_store_cron.log; a non-zero check is something to read, not
# a failure of the cron.
#
# Plan v162 (docs/superpowers/plans/2026-10-15-v162-alpaca-history-store_0-index.md),
# task AH20; installed by AH25 after the merge, because `compose run` uses
# the deployed image (SWING_BOT_IMAGE from /opt/swing-bot/.env).
#
# Run this ON the VM as root, from a dev machine via:
#   bash scripts/ops/ssh-hetzner.sh "bash -s" < scripts/ops/install_v162_history_cron.sh
#
# Safe to re-run: it replaces any earlier line this script installed.
set -euo pipefail

MARKER='# v162 alpaca history store weekly update (installed by install_v162_history_cron.sh)'
BASE="${BASE:-/opt/swing-bot}"
CRON_LINE='30 6 * * 0 cd /opt/swing-bot && { echo "=== $(date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ) ==="; /usr/bin/docker compose run --rm -T bot python scripts/data/fetch_alpaca_history.py --mode update; echo "update exit $?"; /usr/bin/docker compose run --rm -T bot python scripts/data/check_history_store.py --verify-hashes; echo "check exit $?"; } >> /opt/swing-bot/logs/history_store_cron.log 2>&1'

mkdir -p "$BASE/logs"
{
    crontab -l 2>/dev/null | grep -vF "$MARKER" | grep -vF "fetch_alpaca_history.py --mode update" || true
    echo "$MARKER"
    echo "$CRON_LINE"
} | crontab -

echo "Installed crontab:"
crontab -l
