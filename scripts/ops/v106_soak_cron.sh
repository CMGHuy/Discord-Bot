#!/usr/bin/env bash
# One cron run of the v106 soak check (plan v106 T13 Step 6, soak attempt 2).
# Pipes scripts/ops/v106_soak_check.py into the bot container over stdin, so
# it needs only the host checkout, not a rebuilt image. Appends to
# logs/v106_soak_cron.log; once the window's last day (2026-10-07) has been
# checked it removes its own crontab line (one-shot job).
set -uo pipefail
cd /opt/swing-bot
LOG=/opt/swing-bot/logs/v106_soak_cron.log
{
    echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
    /usr/bin/docker compose exec -T bot python - < scripts/ops/v106_soak_check.py
} >> "$LOG" 2>&1
if [ "$(date -u +%Y-%m-%d)" \> "2026-10-06" ]; then
    crontab -l 2>/dev/null | grep -vF "v106_soak_cron.sh" | crontab -
    echo "one-shot done: crontab line removed" >> "$LOG"
fi
