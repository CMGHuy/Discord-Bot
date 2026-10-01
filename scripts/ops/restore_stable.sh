#!/usr/bin/env bash
# Restore a pinned stable point on the VM (v120 section 1, Restore).
#
#   scripts/ops/restore_stable.sh stable-2026-10-01 --dry-run    # print the plan
#   scripts/ops/restore_stable.sh stable-2026-10-01 --i-mean-it  # do it
#
# Without a flag it prints the plan and a usage line and exits 2; nothing is
# changed. The manifest verify and the GHCR image check run before anything is
# stopped or overwritten. Restores the dump, market_data/, .env, both images
# and the code of the point, then starts with scanning PAUSED -- unpause from
# the admin UI. Runs ON the VM as root; modelled on rollback_to.sh.
set -euo pipefail
cd /opt/swing-bot

NAME="${1:-}"
MODE="${2:-}"
if [ -z "$NAME" ]; then
  echo "usage: restore_stable.sh <stable-name> [--dry-run | --i-mean-it]" >&2
  exit 2
fi
DRY_RUN=0
CONFIRMED=0
[ "$MODE" = "--dry-run" ] && DRY_RUN=1
[ "$MODE" = "--i-mean-it" ] && CONFIRMED=1
DIR="backups/stable/$NAME"
LOG=logs/rollback.log
mkdir -p backups logs
WORK="$(mktemp -d /opt/swing-bot/backups/restore_stable.XXXXXX)"   # same filesystem: mv is atomic
trap 'rm -rf "$WORK"' EXIT

# 1. A damaged or incomplete point is refused.
python3 scripts/ops/backup_manifest.py verify "$DIR" || { echo "REFUSE: $DIR failed verification"; exit 2; }

# 2. Read the manifest (python3 json module only).
read_field() {
  python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])' "$DIR/manifest.json" "$1"
}
git_sha="$(read_field git_sha)"
bot_image="$(read_field bot_image)"
db_image="$(read_field db_image)"
restic_id="$(read_field restic_id)"

echo "Stable point $NAME resolves to:"
echo "  dump       $DIR/db.sql.gz"
echo "  code       git $git_sha"
echo "  bot image  $bot_image"
echo "  db image   $db_image"
echo "  market     restic $restic_id"
if ! docker manifest inspect "$bot_image" >/dev/null || ! docker manifest inspect "$db_image" >/dev/null; then
  echo "REFUSE: an image recorded for $NAME is no longer on GHCR"
  exit 2
fi
if [ "$DRY_RUN" = 1 ]; then
  echo "Dry run: nothing changed."
  exit 0
fi
if [ "$CONFIRMED" != 1 ]; then
  echo "usage: restore_stable.sh <stable-name> [--dry-run | --i-mean-it]" >&2
  echo "  nothing changed; pass --i-mean-it to restore over the live system" >&2
  exit 2
fi

RESTIC_PASSWORD="$(python3 scripts/ops/env_set.py --get RESTIC_PASSWORD)"
export RESTIC_PASSWORD
export RESTIC_REPOSITORY=/opt/swing-bot/backups/restic

echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) restore_stable $NAME started (git $git_sha)" >> "$LOG"

# 3. Checkpoint of now, so this restore can itself be undone.
docker compose exec -T -u postgres db pgbackrest --stanza=swingbot --type=diff backup </dev/null
scripts/ops/restic_hourly.sh
python3 -m swingbot.core.infra.env_snapshot snapshot .env

# 4. Stop the writers.
docker compose stop bot admin

# 5. market_data, swapped in atomically.
restic restore "$restic_id" --target "$WORK/md" --include /opt/swing-bot/market_data
mv market_data "backups/market_data.pre-restore-$(date -u +%Y%m%dT%H%M%SZ)"
mv "$WORK/md/opt/swing-bot/market_data" market_data

# 6. Config: the .env of the point, in place (keeps the owner); its images.
cat "$DIR/env" > .env
chown deploy:deploy .env
python3 scripts/ops/env_set.py SWING_BOT_IMAGE "$bot_image"
python3 scripts/ops/env_set.py SWING_BOT_DB_IMAGE "$db_image"
docker pull "$bot_image"
docker pull "$db_image"

# 7. Postgres from the dump, then the code of the point.
./scripts/ops/restore_db.sh "$DIR/db.sql.gz" swingbot --i-mean-it
git checkout --detach "$git_sha"

# 8. Pause scanning BEFORE the bot starts, so it does not re-post old alerts.
touch data/scan_paused.flag
docker compose exec -T db psql -U swingbot -d swingbot -v ON_ERROR_STOP=1 -c \
  "INSERT INTO runtime_flags (name, set_at) VALUES ('scan_paused', now())
   ON CONFLICT (name) DO UPDATE SET set_at = EXCLUDED.set_at" </dev/null

# 9. Start and verify.
docker compose up -d --no-build --wait bot admin
echo "--- alembic (current must equal heads) ---"
docker compose exec -T bot alembic current </dev/null
docker compose exec -T bot alembic heads </dev/null
docker compose ps
echo "Restored $NAME: dump, market_data (restic $restic_id), .env, images of git $git_sha."
echo "Scanning is PAUSED. Unpause from the admin UI once the book looks right."
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) restore_stable $NAME finished" >> "$LOG"
