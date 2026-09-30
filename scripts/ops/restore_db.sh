#!/usr/bin/env bash
# Restore a pg_dump into a named database.
#
#   ./scripts/ops/restore_db.sh data/backups/db/swingbot_2026-08-30_03-00-00.sql.gz swingbot_restore_test
#
# The target database is a REQUIRED argument with no default. A restore script
# whose default target is production is a script that eventually restores over
# production; one word removes that.
set -euo pipefail

cd "$(dirname "$0")/../.."

DUMP="${1:-}"
TARGET="${2:-}"
FORCE="${3:-}"

if [ -z "$DUMP" ] || [ -z "$TARGET" ]; then
  echo "usage: $0 <dump.sql.gz> <target-database> [--i-mean-it]" >&2
  echo "  the target database is required and has no default" >&2
  exit 2
fi

if [ ! -s "$DUMP" ]; then
  echo "restore_db: no such dump, or it is empty: $DUMP" >&2
  exit 1
fi

if [ "$TARGET" = "swingbot" ] && [ "$FORCE" != "--i-mean-it" ]; then
  echo "restore_db: '$TARGET' is the live database." >&2
  echo "  Restore into a throwaway database first and compare row counts." >&2
  echo "  If you really mean it, pass --i-mean-it as the third argument." >&2
  exit 1
fi

echo "restore_db: creating $TARGET"
docker compose exec -T db psql -U swingbot -d postgres \
  -c "DROP DATABASE IF EXISTS \"$TARGET\";" \
  -c "CREATE DATABASE \"$TARGET\";"

echo "restore_db: replaying $DUMP into $TARGET"
gunzip -c "$DUMP" | docker compose exec -T db psql -U swingbot -d "$TARGET" -v ON_ERROR_STOP=1

echo "restore_db: row counts in $TARGET"
docker compose exec -T db psql -U swingbot -d "$TARGET" -c "
  SELECT relname, n_live_tup FROM pg_stat_user_tables ORDER BY relname;"
