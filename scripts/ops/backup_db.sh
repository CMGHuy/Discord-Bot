#!/usr/bin/env bash
# Nightly Postgres backup: one timestamped dump into data/backups/db/,
# pruning anything older than 90 days.
#
# 90 days, by age and not by count (v116): day-level restores beyond the 30-day
# point-in-time window, and a day with three manual dumps must not evict older
# nightly ones.
#
# The dump streams over stdout from the db container to the host, so no
# container mount is needed. Restore: scripts/ops/restore_db.sh.
set -euo pipefail

cd "$(dirname "$0")/../.."

BACKUP_DIR="data/backups/db"
STAMP="$(date -u +%Y-%m-%d_%H-%M-%S)"
OUT="${BACKUP_DIR}/swingbot_${STAMP}.sql.gz"
TMP="${OUT}.partial"

mkdir -p "$BACKUP_DIR"
trap 'rm -f "$TMP"' EXIT

# --clean --if-exists so the dump can be replayed into a database that still
# has objects; -Fp (plain) so it is greppable and restorable with psql alone.
docker compose exec -T db \
  pg_dump -U swingbot -d swingbot --clean --if-exists -Fp \
  | gzip -9 > "$TMP"

# An empty file is the failure mode that would otherwise pass silently, and
# pruning after an empty dump is how the last good backup gets deleted.
if [ ! -s "$TMP" ]; then
  echo "backup_db: dump is empty, refusing to prune: $OUT" >&2
  exit 1
fi

mv "$TMP" "$OUT"
echo "backup_db: wrote $OUT ($(du -h "$OUT" | cut -f1))"

find "$BACKUP_DIR" -name 'swingbot_*.sql.gz' -type f -mtime +90 -print -delete
