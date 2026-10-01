#!/usr/bin/env bash
# Pull a read-only copy of production's store files into data/v116_snapshot/
# for tests/db/test_prod_snapshot_round_trip.py (v116 Phase 3). Gitignored;
# never commit it. Read-only on the VM: it only tars and streams.
#   bash scripts/ops/pull_prod_snapshot.sh
set -euo pipefail
cd "$(dirname "$0")/../.."
SSH_HETZNER="${SSH_HETZNER:-E:/Documents/Private/Projects/Discord-Bot/scripts/ops/ssh-hetzner.sh}"
OUT=data/v116_snapshot
FILES="trades.json plans.json starred_plans.json account.json state.json journal.json \
watchlist.json admin_jobs.json scheduled_jobs.json ui_preferences.json settings_audit.jsonl \
killswitch.json ticker_directory.json tuning_results tuning_proposals scan_paused.flag \
trigger_check.flag scan_running.flag stop_scan.flag bot_heartbeat.json manual_close_notify.json \
market_data_state.json scan_progress.json"

rm -rf "$OUT.tmp"
mkdir -p "$OUT.tmp"
# The remote script goes over stdin: `wsl ssh "<cmd>"` expands $(...) in WSL
# first, so an inline command substitution would list nothing.
printf 'cd /opt/swing-bot/data && ls -d %s 2>/dev/null | xargs tar czf - | base64 -w0\n' "$FILES" \
  | bash "$SSH_HETZNER" "bash -s" 2>/dev/null | base64 -d | tar xzf - -C "$OUT.tmp"
rm -rf "$OUT"
# Windows can refuse a directory rename (indexer/AV holds it); copy then.
mv "$OUT.tmp" "$OUT" 2>/dev/null || { mkdir -p "$OUT" && cp -r "$OUT.tmp/." "$OUT/" && rm -rf "$OUT.tmp"; }
date -u +%Y-%m-%dT%H:%M:%SZ > "$OUT/PULLED_AT"
ls -la "$OUT"
