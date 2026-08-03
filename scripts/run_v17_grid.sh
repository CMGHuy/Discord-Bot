#!/bin/bash
# Plan v8 Task V17 -- drive the sizing grid one strategy at a time.
#
# Chunked per strategy on purpose (CLAUDE.md): a killed or restarted run then
# loses one strategy's chunk, not the whole sweep, and each chunk's JSON lands
# as soon as it finishes. Both the driver and tune_sizing.py print one flushed
# line per config, so a redirected multi-hour run always shows progress.
#
# Usage: scripts/run_v17_grid.sh <python> <outdir> [strategy ...]
set -u
PY="${1:?usage: run_v17_grid.sh <python> <outdir> [strategy ...]}"
OUT="${2:?usage: run_v17_grid.sh <python> <outdir> [strategy ...]}"
shift 2
STRATEGIES=("$@")
if [ ${#STRATEGIES[@]} -eq 0 ]; then
  STRATEGIES=("EMA Crossover" "VWAP" "Fibonacci" "Support/Resistance" "RSI" \
              "MACD" "Elliott Wave" "MA Ribbon" "Break & Retest" \
              "RSI Divergence" "Volume Profile")
fi
mkdir -p "$OUT"
cd "$(dirname "$0")/.." || exit 1

for s in "${STRATEGIES[@]}"; do
  slug=$(echo "$s" | tr 'A-Z /&' 'a-z___' | tr -s '_')
  json="$OUT/$slug.json"
  if [ -f "$json" ]; then
    echo "### SKIP $s (already have $json)"
    continue
  fi
  echo "### START $s  $(date -u +%FT%TZ)"
  "$PY" scripts/tune_sizing.py --strategy "$s" --json "$json"
  echo "### DONE  $s  rc=$?  $(date -u +%FT%TZ)"
done
echo "### ALL DONE $(date -u +%FT%TZ)"
