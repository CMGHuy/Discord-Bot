#!/usr/bin/env bash
# Installs (idempotently) the v171 D9 weekday crontab entries on the Hetzner VM
# (plan v171 V171-37..V171-39). A re-run replaces its own line, never duplicates.
#   report LABEL SINCE UNTIL [BASE_SINCE BASE_UNTIL]  21:15 UTC, after the US close
#   sampler START END                                 13:20 UTC, before the earliest open
# Run ON the VM, e.g. from a dev machine:
#   bash scripts/ops/ssh-hetzner.sh "bash -s -- report baseline 2026-10-19 2026-10-23" < scripts/ops/install_v171_cron.sh
set -euo pipefail
MODE=${1:?report|sampler}
shift
case "$MODE" in
    report)
        LABEL=${1:?label}
        MARKER="# v171 report $LABEL (install_v171_cron.sh)"
        CRON_LINE="15 21 * * 1-5 /bin/bash /opt/swing-bot/scripts/ops/v171_report_cron.sh $*"
        DROP="v171_report_cron.sh $LABEL "
        ;;
    sampler)
        START=${1:?start}; END=${2:?end}
        MARKER='# v171 tape sampler (install_v171_cron.sh)'
        CRON_LINE="20 13 * * 1-5 /bin/bash /opt/swing-bot/scripts/ops/v171_tape_sampler_cron.sh $START $END"
        DROP="v171_tape_sampler_cron.sh"
        ;;
    *) echo "usage: $0 report LABEL SINCE UNTIL [BASE_SINCE BASE_UNTIL] | sampler START END" >&2; exit 2 ;;
esac

{
    crontab -l 2>/dev/null | grep -vF "$MARKER" | grep -vF "$DROP" || true
    echo "$MARKER"
    echo "$CRON_LINE"
} | crontab -

echo "Installed crontab:"
crontab -l
