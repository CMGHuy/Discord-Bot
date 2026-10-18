#!/usr/bin/env bash
# One day's v171 D9 tape sampler run (plan v171 V171-37..V171-39). Pipes
# scripts/ops/v171_tape_sampler.py into the bot container over stdin; it appends
# one line per minute to logs/v171_tape_samples.jsonl until 21:15 UTC. Skips
# days before START; after END's run it removes its own crontab line.
# Usage: START END (UTC dates)
set -uo pipefail
START=${1:?start}; END=${2:?end}
cd /opt/swing-bot
TODAY=$(date -u +%Y-%m-%d)
[ "$TODAY" \< "$START" ] && exit 0
/usr/bin/docker compose exec -T bot python - --out logs/v171_tape_samples.jsonl --until-utc 21:15 < scripts/ops/v171_tape_sampler.py >> logs/v171_tape_sampler.log 2>&1
if [ ! "$TODAY" \< "$END" ]; then
    crontab -l 2>/dev/null | grep -vF "v171_tape_sampler_cron.sh" | crontab -
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) one-shot done: window $START..$END closed; crontab line removed" >> logs/v171_tape_sampler.log
fi
