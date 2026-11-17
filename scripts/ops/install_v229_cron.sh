#!/usr/bin/env bash
# Installs (idempotently) the v229 weekly pair-append crontab entry on the
# Hetzner VM (plan v229, Tasks V229-11 and V229-14). A re-run replaces its own
# line, never duplicates. T0 is baked into the line: the CLI needs it in every
# mode and cannot read its own freeze commit on the VM (plan Handoff 13).
# Run ON the VM as root, after the deploy that ships scripts/ops/v229_pairs_cron.sh:
#   bash scripts/ops/ssh-hetzner.sh "bash -s -- <T0>" < scripts/ops/install_v229_cron.sh
# Removal (Task V229-15, after the verdict):
#   crontab -l | grep -vF '# v229 deferred-entry pairs' | grep -vF v229_pairs_cron.sh | crontab -
# SWING_BOT_DIR is a test seam; a real run takes the default.
set -euo pipefail

T0=${1:?usage: install_v229_cron.sh <T0>}
if ! [[ "$T0" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(Z|[+-][0-9]{2}:[0-9]{2})$ ]]; then
    echo "install_v229_cron: T0 must be ISO 8601 with seconds and an offset, got '$T0'" >&2
    exit 2
fi

BASE=${SWING_BOT_DIR:-/opt/swing-bot}
MARKER='# v229 deferred-entry pairs'
CRON_LINE="15 8 * * 6 /bin/bash $BASE/scripts/ops/v229_pairs_cron.sh $T0"

mkdir -p "$BASE/logs" "$BASE/data/v229"
{
    crontab -l 2>/dev/null | grep -vF "$MARKER" | grep -vF "v229_pairs_cron.sh" || true
    echo "$MARKER"
    echo "$CRON_LINE"
} | crontab -

echo "Installed crontab:"
crontab -l
