#!/usr/bin/env bash
# One run of the v171 D9 report for one window (plan v171 V171-37..V171-39).
# Pipes scripts/reports/market_fetch_report.py into the bot container over
# stdin. Appends to logs/v171_<LABEL>_cron.log and rewrites
# logs/v171_<LABEL>.json; after the window's last day it writes FINAL and
# removes its own crontab line. Usage: LABEL SINCE UNTIL [BASE_SINCE BASE_UNTIL]
set -uo pipefail
LABEL=${1:?label}; SINCE=${2:?since}; UNTIL=${3:?until}; BASE_SINCE=${4:-}; BASE_UNTIL=${5:-}
cd /opt/swing-bot
LOG=/opt/swing-bot/logs/v171_${LABEL}_cron.log
ARGS=(--since "$SINCE" --until "$UNTIL" --json "logs/v171_${LABEL}.json" --tape-samples logs/v171_tape_samples.jsonl)
[ -n "$BASE_SINCE" ] && ARGS+=(--baseline-since "$BASE_SINCE" --baseline-until "$BASE_UNTIL")
{
    echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
    /usr/bin/docker compose exec -T bot python - "${ARGS[@]}" < scripts/reports/market_fetch_report.py
} >> "$LOG" 2>&1
if [ ! "$(date -u +%Y-%m-%d)" \< "$UNTIL" ]; then
    crontab -l 2>/dev/null | grep -vF "v171_report_cron.sh $LABEL " | crontab -
    echo "FINAL: window $SINCE..$UNTIL closed; crontab line removed" >> "$LOG"
fi
