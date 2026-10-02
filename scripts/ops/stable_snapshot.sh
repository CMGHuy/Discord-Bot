#!/usr/bin/env bash
# Pin a known-good point on the VM (v120 section 1): a fresh DB dump, .env,
# the deploy record, row counts read from that dump and a tagged restic
# snapshot of market_data/, sealed by a manifest under backups/stable/<name>/.
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
DONE=0
SNAP_ID=""
# On any exit: drop the partial folder and temp dir; if the run did not finish,
# forget the restic snapshot it made (its stable tag would pin it forever).
# The original exit status is captured first and re-raised.
cleanup() {
  rc=$?
  rm -rf "$DIR.partial" "$WORK"
  if [ "$DONE" = 0 ] && [ -n "$SNAP_ID" ]; then
    echo "stable_snapshot: failed, forgetting restic snapshot $SNAP_ID" >&2
    restic forget "$SNAP_ID" >&2 || true
  fi
  exit "$rc"
}
trap cleanup EXIT

# git runs as the checkout's owner (deploy): root gets "dubious ownership", and a
# failing command substitution inside an argument would not trip set -e, so the
# manifest would silently record an empty sha. Read it first and fail loudly.
GIT_SHA="$(runuser -u deploy -- git rev-parse HEAD)"
[ -n "$GIT_SHA" ] || { echo "stable_snapshot: could not read the git sha as deploy" >&2; exit 1; }

rm -rf "$DIR.partial"
mkdir -p "$DIR.partial" logs
chmod 700 "$DIR.partial"

BACKUP_OUT="$(./scripts/ops/backup_db.sh)"
echo "$BACKUP_OUT"
NEWEST_DUMP="$(printf '%s\n' "$BACKUP_OUT" | sed -n 's/^backup_db: wrote \(.*\) (.*)$/\1/p' | tail -n 1)"
if [ -z "$NEWEST_DUMP" ] || [ ! -f "$NEWEST_DUMP" ]; then
  echo "stable_snapshot: could not find the dump backup_db.sh wrote ('$NEWEST_DUMP')" >&2
  exit 1
fi
cp "$NEWEST_DUMP" "$DIR.partial/db.sql.gz"
chmod 600 "$DIR.partial/db.sql.gz"

install -m 600 .env "$DIR.partial/env"
tail -n 1 backups/deploys.jsonl > "$DIR.partial/deploy.json"

# Row counts come from the dump itself so they cannot drift from it while the
# bot keeps writing; rows.json lives outside the folder (the manifest embeds it).
python3 scripts/ops/backup_manifest.py count-dump "$DIR.partial/db.sql.gz" > "$WORK/rows.json"
PGV="$(docker compose exec -T db psql -U swingbot -d swingbot -At -c 'SHOW server_version' | tr -d '\r')"

RESTIC_PASSWORD="$(python3 scripts/ops/env_set.py --get RESTIC_PASSWORD)"
if [ -z "$RESTIC_PASSWORD" ]; then
  echo "stable_snapshot: RESTIC_PASSWORD is not set in .env" >&2
  exit 1
fi
export RESTIC_PASSWORD
export RESTIC_REPOSITORY="$PWD/backups/restic"
# Same lock as the hourly cron, so this cannot collide with its forget --prune.
RESTIC_RC=0
flock logs/restic.lock restic backup --host swing-bot --tag market_data --tag stable --tag "$NAME" --json "$PWD/market_data" > "$WORK/restic.jsonl" || RESTIC_RC=$?
# Parse the snapshot id BEFORE acting on the status, so cleanup can forget it.
SNAP_ID="$(python3 -c 'import json,sys
for line in open(sys.argv[1]):
    try:
        m = json.loads(line)
    except ValueError:
        continue
    if m.get("message_type") == "summary" and m.get("snapshot_id"):
        print(m["snapshot_id"])' "$WORK/restic.jsonl")" || SNAP_ID=""
case "$RESTIC_RC" in
  0) ;;
  3) echo "stable_snapshot: WARNING restic exit 3 (a file vanished while read); the snapshot $SNAP_ID exists, continuing" >&2 ;;
  *) echo "stable_snapshot: restic backup failed with status $RESTIC_RC" >&2; exit 1 ;;
esac
if [ -z "$SNAP_ID" ]; then
  echo "stable_snapshot: restic printed no snapshot id" >&2
  exit 1
fi

python3 scripts/ops/backup_manifest.py build "$DIR.partial" --git-sha "$GIT_SHA" --deploy-json "$DIR.partial/deploy.json" --restic-id "$SNAP_ID" --row-counts "$WORK/rows.json" --pg-version "$PGV" --vm-epoch "$(date +%s)" > "$WORK/manifest.json"
python3 scripts/ops/backup_manifest.py verify "$DIR.partial"
mv -T "$DIR.partial" "$DIR"
DONE=1

echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) stable_snapshot $NAME restic=$SNAP_ID" >> logs/stable_snapshot.log
cat "$WORK/manifest.json"
