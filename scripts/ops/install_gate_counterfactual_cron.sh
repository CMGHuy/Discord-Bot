#!/usr/bin/env bash
# Installs (idempotently) a weekly crontab entry on the Hetzner VM that runs
# scripts/ops/gate_counterfactual_progress.py inside the bot container and
# appends timestamped output to logs/gate-counterfactual.log.
#
# Added for plan v147 (docs/superpowers/plans/2026-10-09-v147-gate-counterfactual_0-index.md)
# Task V147-16: the live gate-counterfactual verdicts need weeks of rows; this
# gives a progress reading every Saturday whether or not a Claude session is
# open. It reads and prints only -- it decides, resolves and removes nothing.
#
# Install AFTER the v147 deploy (close-out), ON the VM as root, e.g. from a dev machine via:
#   bash scripts/ops/ssh-hetzner.sh "bash -s" < scripts/ops/install_gate_counterfactual_cron.sh
#
# Safe to re-run: it replaces any prior line this script installed rather
# than appending a duplicate.
set -euo pipefail

MARKER='# v147 gate counterfactual progress (installed by install_gate_counterfactual_cron.sh)'
CRON_LINE='30 7 * * 6 cd /opt/swing-bot && { echo "=== $(date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ) ==="; /usr/bin/docker compose exec -T bot python scripts/ops/gate_counterfactual_progress.py; } >> /opt/swing-bot/logs/gate-counterfactual.log 2>&1'

{
    crontab -l 2>/dev/null | grep -vF "$MARKER" | grep -vF "gate_counterfactual_progress.py" || true
    echo "$MARKER"
    echo "$CRON_LINE"
} | crontab -

echo "Installed crontab:"
crontab -l
