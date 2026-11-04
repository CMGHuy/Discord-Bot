#!/usr/bin/env bash
# Replicate the PRODUCTION Postgres database into the LOCAL dev database.
# Dev machine only (Git Bash). Reaches the VM solely through ssh-hetzner.sh.
#
#   bash scripts/ops/replicate_prod_db.sh                       # -> swingbot_prod_replica
#   bash scripts/ops/replicate_prod_db.sh my_copy               # -> my_copy
#   bash scripts/ops/replicate_prod_db.sh swingbot --i-mean-it  # -> the live LOCAL db
#   bash scripts/ops/replicate_prod_db.sh --full                # drop and rebuild instead of topping up
#   bash scripts/ops/replicate_prod_db.sh --dry-run             # print the plan, touch nothing
#
# DEFAULT IS INCREMENTAL: when the target already exists on the same alembic
# revision as production, only the rows it LACKS are inserted (a data-only dump
# replayed with ON CONFLICT DO NOTHING); nothing local is dropped, so a sibling
# task mid-test keeps its database. It rebuilds from scratch (the old behaviour)
# when the target is absent, on another revision, or --full is given. Rows
# production deleted or changed since the last sync are NOT touched by a top-up:
# use --full when that matters.
#
# Production is only ever READ: one pg_dump (a single consistent snapshot) and
# one read-only count query. Nothing is written, restarted or deleted there.
# A FULL rebuild drops and recreates the target via restore_db.sh, so the default
# is a separate replica database that never collides with the working local one.
#
# The dump travels base64-encoded: ssh-hetzner.sh goes through `wsl ssh`, and a
# raw binary stream through wsl.exe is not something to bet a backup on.
set -euo pipefail
cd "$(dirname "$0")/../.."

TARGET="swingbot_prod_replica"
FORCE=""
DRY=""
MODE_FLAG=""
for arg in "$@"; do
  case "$arg" in
    --i-mean-it) FORCE="--i-mean-it" ;;
    --dry-run) DRY=1 ;;
    --full) MODE_FLAG="full" ;;
    -*) echo "replicate_prod_db: unknown flag '$arg' (--dry-run, --full, --i-mean-it)" >&2; exit 2 ;;
    *) TARGET="$arg" ;;
  esac
done
SSH_HETZNER="${SSH_HETZNER:-scripts/ops/ssh-hetzner.sh}"
KEEP=3
STAMP="${REPLICATE_STAMP:-$(date -u +%Y-%m-%dT%H-%MZ)}"
OUT_DIR="backups/prod-replica"
OUT="$OUT_DIR/prod_${STAMP}.sql.gz"

# The same one-line count query on both sides: exact counts, every public table.
COUNTS_SQL="select table_name, (xpath('/row/c/text()', query_to_xml(format('select count(*) as c from %I.%I', table_schema, table_name), false, true, '')))[1]::text from information_schema.tables where table_schema='public' and table_type='BASE TABLE' order by 1"

if [ "$TARGET" = "swingbot" ] && [ "$FORCE" != "--i-mean-it" ]; then
  echo "replicate_prod_db: 'swingbot' is the live LOCAL database and would be dropped." >&2
  echo "  Use the default replica database, or add --i-mean-it." >&2
  exit 2
fi
case "$TARGET" in
  *[!A-Za-z0-9_]*|"") echo "replicate_prod_db: target must be [A-Za-z0-9_]+: '$TARGET'" >&2; exit 2 ;;
esac

if [ -n "$DRY" ]; then
  echo "replicate_prod_db: DRY RUN"
  echo "  source : production swingbot (Hetzner VM, read-only pg_dump)"
  echo "  target : local swing-db / $TARGET"
  echo "  dump   : $OUT"
  exit 0
fi

# Preflight: both ends must answer before a byte is moved.
docker compose exec -T db pg_isready -U swingbot -d postgres >/dev/null \
  || { echo "replicate_prod_db: FAIL local db container is not ready (make up)" >&2; exit 1; }
bash "$SSH_HETZNER" "true" >/dev/null 2>&1 \
  || { echo "replicate_prod_db: FAIL cannot reach the VM through $SSH_HETZNER" >&2; exit 1; }

# Incremental only when the target exists on production's revision; otherwise rebuild.
LOCAL_PSQL=(docker compose exec -T db psql -U swingbot -At)
PROD_REV="$(bash "$SSH_HETZNER" "cd /opt/swing-bot && docker compose exec -T db psql -U swingbot -d swingbot -At -c 'select version_num from alembic_version'" 2>/dev/null | tr -d '\r')"
HAVE_TARGET="$("${LOCAL_PSQL[@]}" -d postgres -c "select 1 from pg_database where datname='$TARGET'" | tr -d '\r')"
LOCAL_REV=""
[ "$HAVE_TARGET" = "1" ] && LOCAL_REV="$("${LOCAL_PSQL[@]}" -d "$TARGET" -c 'select version_num from alembic_version' 2>/dev/null | tr -d '\r' || true)"
MODE="full"
if [ "$MODE_FLAG" != "full" ] && [ -n "$PROD_REV" ] && [ "$PROD_REV" = "$LOCAL_REV" ]; then MODE="incremental"; fi
echo "replicate_prod_db: mode=$MODE (prod alembic=${PROD_REV:-?} local=${LOCAL_REV:-none})"
if [ "$MODE" = "incremental" ]; then
  # Top up: data only, one INSERT per row that does nothing on a key conflict.
  DUMP_FLAGS="--data-only --column-inserts --on-conflict-do-nothing --disable-triggers"
else
  DUMP_FLAGS="--clean --if-exists"
fi

mkdir -p "$OUT_DIR"
TMP="$OUT.partial"
trap 'rm -f "$TMP"' EXIT

echo "replicate_prod_db: dumping production (read-only)"
bash "$SSH_HETZNER" "cd /opt/swing-bot && docker compose exec -T db pg_dump -U swingbot -d swingbot --no-owner --no-privileges $DUMP_FLAGS -Fp | gzip -9 | base64 -w0" 2>/dev/null \
  | base64 -d > "$TMP"

if [ ! -s "$TMP" ] || ! gzip -t "$TMP" 2>/dev/null; then
  echo "replicate_prod_db: FAIL the dump is empty or not valid gzip; local db untouched" >&2
  exit 1
fi
# Header read into a variable: `grep -q` closing the pipe early would SIGPIPE
# gunzip and, under pipefail, turn a good dump into a false failure.
HEADER="$(gunzip -c "$TMP" 2>/dev/null | head -n 20 || true)"
if ! printf '%s' "$HEADER" | grep -q "PostgreSQL database dump"; then
  echo "replicate_prod_db: FAIL the dump has no pg_dump header; local db untouched" >&2
  exit 1
fi
mv "$TMP" "$OUT"
echo "replicate_prod_db: dump ok: $OUT ($(du -h "$OUT" | cut -f1))"

PROD_COUNTS="$(bash "$SSH_HETZNER" "cd /opt/swing-bot && docker compose exec -T db psql -U swingbot -d swingbot -At -F '|' -c \"$COUNTS_SQL\"" 2>/dev/null | tr -d '\r')"

LOCAL_BEFORE=""
if [ "$MODE" = "incremental" ]; then
  LOCAL_BEFORE="$(docker compose exec -T db psql -U swingbot -d "$TARGET" -At -F '|' -c "$COUNTS_SQL" | tr -d '\r')"
  # One transaction: a failed replay leaves the replica exactly as it was.
  gunzip -c "$OUT" | docker compose exec -T db psql -U swingbot -d "$TARGET" -q -1 -v ON_ERROR_STOP=1 >/dev/null     || { echo "replicate_prod_db: FAIL top-up rolled back; replica unchanged (try --full)" >&2; exit 1; }
# restore_db.sh owns the drop/create/replay and its own live-db refusal.
elif [ "$FORCE" = "--i-mean-it" ]; then
  bash scripts/ops/restore_db.sh "$OUT" "$TARGET" --i-mean-it >/dev/null
else
  bash scripts/ops/restore_db.sh "$OUT" "$TARGET" >/dev/null
fi

LOCAL_COUNTS="$(docker compose exec -T db psql -U swingbot -d "$TARGET" -At -F '|' -c "$COUNTS_SQL" | tr -d '\r')"
REV="$(docker compose exec -T db psql -U swingbot -d "$TARGET" -At -c 'select version_num from alembic_version' | tr -d '\r')"

# Compare: the dump is a snapshot, production keeps moving, so a table where
# production is AHEAD is drift, not damage. Replica ahead, or a missing table,
# is a real mismatch.
VERDICT="MATCH"
DIFFS=""
while IFS='|' read -r tbl pcount; do
  [ -n "$tbl" ] || continue
  lcount="$(printf '%s\n' "$LOCAL_COUNTS" | awk -F'|' -v t="$tbl" '$1==t{print $2}')"
  if [ -z "$lcount" ]; then
    VERDICT="MISMATCH"; DIFFS="$DIFFS  $tbl: prod=$pcount replica=MISSING"$'\n'
  elif [ "$lcount" != "$pcount" ]; then
    if [ "$pcount" -gt "$lcount" ] && [ "$VERDICT" = "MATCH" ]; then VERDICT="DRIFT"; fi
    if [ "$lcount" -gt "$pcount" ]; then VERDICT="MISMATCH"; fi
    DIFFS="$DIFFS  $tbl: prod=$pcount replica=$lcount"$'\n'
  fi
done <<< "$PROD_COUNTS"

N_TABLES="$(printf '%s\n' "$LOCAL_COUNTS" | grep -c '|' || true)"
ADDED=""
if [ "$MODE" = "incremental" ]; then
  ADDED=" added=$(paste -d'|' <(printf '%s
' "$LOCAL_BEFORE") <(printf '%s
' "$LOCAL_COUNTS") | awk -F'|' '{a+=$4-$2} END{print a+0}')"
fi
echo "replicate_prod_db: $VERDICT mode=$MODE target=$TARGET tables=$N_TABLES alembic=$REV$ADDED dump=$OUT"
[ -z "$DIFFS" ] || printf '%s' "$DIFFS"

# Keep the newest few dumps; each is the whole trading history.
ls -1t "$OUT_DIR"/prod_*.sql.gz 2>/dev/null | tail -n +$((KEEP + 1)) | while read -r old; do rm -f "$old"; done

[ "$VERDICT" != "MISMATCH" ] || exit 1
