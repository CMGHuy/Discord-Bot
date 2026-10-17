#!/usr/bin/env bash
# One minute's sample of VM CPU load for the v106 (a) slowdown diagnosis
# (plan docs/superpowers/plans/implemented/2026-09-26-v106-alpaca-data-provider.md, T13c).
# Read-only. Appends one block to logs/v106_load_sampler.log: vmstat's 1 s
# us/sy/id/wa/st (st = hypervisor steal), loadavg, per-container CPU/mem and
# the top host processes. Runs only on the trading days START..END (UTC dates)
# and removes its own crontab line once END has passed.
# Usage: v106_load_sampler.sh START END
set -uo pipefail
START=${1:-$(date -u +%Y-%m-%d)}
END=${2:-$START}
TODAY=$(date -u +%Y-%m-%d)
LOG=/opt/swing-bot/logs/v106_load_sampler.log

if [ "$TODAY" \> "$END" ]; then
    crontab -l 2>/dev/null | grep -vF "v106_load_sampler.sh" | crontab -
    echo "one-shot done: crontab line removed" >> "$LOG"
    exit 0
fi
[ "$TODAY" \< "$START" ] && exit 0

{
    echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) loadavg=$(cut -d' ' -f1-3 /proc/loadavg)"
    echo "vmstat(1s): $(vmstat 1 2 | tail -1)   [r b swpd free buff cache si so bi bo in cs us sy id wa st]"
    /usr/bin/docker stats --no-stream --format '  {{.Name}} cpu={{.CPUPerc}} mem={{.MemUsage}}' 2>&1
    ps -eo pcpu,pmem,etimes,args --sort=-pcpu | head -7 | cut -c1-150 | sed 's/^/  /'
} >> "$LOG" 2>&1
