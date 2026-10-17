#!/usr/bin/env bash
# Installs (idempotently) the v148 heartbeat watch on the Hetzner VM: every
# 5 minutes, 24/7, scripts/ops/heartbeat_watch.sh checks the bot's heartbeat
# row and posts to OPS_ALERT_WEBHOOK_URL once per incident and on recovery.
# The script writes its own verdict line to logs/heartbeat_watch.log; cron
# discards stdout and appends stderr to the same log.
#
# Permanent (not one-shot). Owner: the partner (ops). Run this ON the VM as
# root, from a dev machine:
#   bash scripts/ops/ssh-hetzner.sh "bash -s" < scripts/ops/install_heartbeat_watch_cron.sh
#
# Safe to re-run: it replaces any prior line this script installed rather
# than appending a duplicate. BASE overrides /opt/swing-bot (tests only).
set -euo pipefail

BASE="${BASE:-/opt/swing-bot}"
MARKER='# v148 heartbeat watch (installed by install_heartbeat_watch_cron.sh)'
CRON_LINE="*/5 * * * * /usr/bin/env bash $BASE/scripts/ops/heartbeat_watch.sh >/dev/null 2>> $BASE/logs/heartbeat_watch.log"

mkdir -p "$BASE/logs"
{
    crontab -l 2>/dev/null | grep -vF "$MARKER" | grep -vF "heartbeat_watch.sh" || true
    echo "$MARKER"
    echo "$CRON_LINE"
} | crontab -

echo "Installed crontab:"
crontab -l
