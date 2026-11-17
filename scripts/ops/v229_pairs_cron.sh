#!/usr/bin/env bash
# v229 weekly pair append (plan docs/superpowers/plans/implemented/2026-11-15-v229-deferred-entry-counterfactual_0-index.md,
# Task V229-11). Runs ON THE VM from the crontab line install_v229_cron.sh writes.
#   1. The read-only book export, on the HOST (the bot container has no psql
#      path), into data/v229/rows.csv (= /app/data/v229/rows.csv in the bot
#      container), written through rows.csv.tmp so a failed export never
#      leaves a half file behind.
#   2. The deferred-entry CLI in append mode inside the bot container: it
#      appends the new eligible pairs to data/v229/pairs.jsonl (append-once
#      per trade id) and prints one count line.
# It decides, resolves and removes nothing: the verdict is Task V229-15's, by
# hand, after verdict_open_date(T0). An empty week prints a count of 0 and exits 0.
# Usage: v229_pairs_cron.sh <T0>   (ISO 8601 UTC, the pre-registration commit time)
# SWING_BOT_DIR / DOCKER are test seams; a real run takes the defaults.
set -uo pipefail

T0=${1:?usage: v229_pairs_cron.sh <T0>}
BASE=${SWING_BOT_DIR:-/opt/swing-bot}
DOCKER=${DOCKER:-/usr/bin/docker}

cd "$BASE" || exit 1
mkdir -p data/v229 logs

run() {
    echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
    if ! bash scripts/ops/export_book_rows.sh rows > data/v229/rows.csv.tmp; then
        rm -f data/v229/rows.csv.tmp
        echo "v229 pairs: export failed; rows.csv left as it was, nothing appended"
        return 1
    fi
    mv -f data/v229/rows.csv.tmp data/v229/rows.csv
    "$DOCKER" compose exec -T bot python scripts/reports/deferred_entry_counterfactual.py \
        --mode append --rows data/v229/rows.csv --t0 "$T0"
}

run >> logs/v229-pairs.log 2>&1
exit $?
