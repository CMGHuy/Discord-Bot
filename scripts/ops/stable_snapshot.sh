#!/usr/bin/env bash
# Pin a known-good point on the VM (v120 section 1): a fresh DB dump, .env,
# the deploy record, exact row counts and a tagged restic snapshot of
# market_data/, sealed by a manifest under backups/stable/<name>/.
# Usage (root, on the VM): scripts/ops/stable_snapshot.sh stable-YYYY-MM-DD[-N]
# Built in <name>.partial and renamed last, so a half snapshot never carries
# the final name. Prints the manifest JSON as its last output.
set -euo pipefail
cd "$(dirname "$0")/../.."

NAME="${1:-}"
if ! [[ "$NAME" =~ ^stable-[0-9]{4}-[0-9]{2}-[0-9]{2}(-[0-9]+)?$ ]]; then
  echo "stable_snapshot: name must match stable-YYYY-MM-DD[-N], got '$NAME'" >&2
  exit 2
fi
DIR="backups/stable/$NAME"
if [ -e "backups/stable/$NAME" ]; then
  echo "stable_snapshot: $DIR already exists, refusing to overwrite" >&2
  exit 2
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$DIR.partial" "$WORK"' EXIT
mkdir -p "$DIR.partial" logs

./scripts/ops/backup_db.sh
NEWEST_DUMP="$(ls -t data/backups/db/swingbot_*.sql.gz | head -1)"
cp "$NEWEST_DUMP" "$DIR.partial/db.sql.gz"

install -m 600 .env "$DIR.partial/env"
tail -n 1 backups/deploys.jsonl > "$DIR.partial/deploy.json"

# Exact count(*) per public base table, as one JSON object; rows.json lives
# outside the folder (the manifest embeds it).
ROW_SQL="select coalesce(json_object_agg(table_name, (xpath('/row/c/text()', query_to_xml(format('select count(*) as c from %I.%I', table_schema, table_name), false, true, '')))[1]::text::bigint), '{}'::json) from information_schema.tables where table_schema = 'public' and table_type = 'BASE TABLE';"
docker compose exec -T db psql -U swingbot -d swingbot -At -c "$ROW_SQL" > "$WORK/rows.json"
PGV="$(docker compose exec -T db psql -U swingbot -d swingbot -At -c 'SHOW server_version' | tr -d '\r')"

RESTIC_PASSWORD="$(python3 scripts/ops/env_set.py --get RESTIC_PASSWORD)"
if [ -z "$RESTIC_PASSWORD" ]; then
  echo "stable_snapshot: RESTIC_PASSWORD is not set in .env" >&2
  exit 1
fi
export RESTIC_PASSWORD
export RESTIC_REPOSITORY="$PWD/backups/restic"
restic backup --host swing-bot --tag market_data --tag stable --tag "$NAME" --json "$PWD/market_data" > "$WORK/restic.jsonl"
RESTIC_ID="$(tail -n 1 "$WORK/restic.jsonl" | python3 -c 'import json,sys; print(json.load(sys.stdin)["snapshot_id"])')"

python3 scripts/ops/backup_manifest.py build "$DIR.partial" --git-sha "$(git rev-parse HEAD)" --deploy-json "$DIR.partial/deploy.json" --restic-id "$RESTIC_ID" --row-counts "$WORK/rows.json" --pg-version "$PGV" --vm-epoch "$(date +%s)" > "$WORK/manifest.json"
python3 scripts/ops/backup_manifest.py verify "$DIR.partial"
mv "$DIR.partial" "$DIR"

echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) stable_snapshot $NAME restic=$RESTIC_ID" >> logs/stable_snapshot.log
cat "$WORK/manifest.json"
