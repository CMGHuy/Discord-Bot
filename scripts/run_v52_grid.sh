#!/bin/bash
# Plan v8 Task V52 Step 1 -- drive the selectivity search one strategy at a time.
#
# Same chunking rationale as run_v17_grid.sh (CLAUDE.md): a killed or restarted
# run loses one strategy's chunk, not the whole sweep, and each chunk's JSON
# lands as soon as it finishes. tune_selectivity.py prints one flushed line per
# cut-flag combo, so a redirected multi-hour run always shows progress.
#
# Usage: scripts/run_v52_grid.sh <python> <outdir> [strategy ...]
set -u
PY="${1:?usage: run_v52_grid.sh <python> <outdir> [strategy ...]}"
OUT="${2:?usage: run_v52_grid.sh <python> <outdir> [strategy ...]}"
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
  "$PY" scripts/tune_selectivity.py --strategy "$s" --json "$json"
  echo "### DONE  $s  rc=$?  $(date -u +%FT%TZ)"
done
echo "### ALL DONE $(date -u +%FT%TZ)"
