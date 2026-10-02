#!/usr/bin/env bash
# Roll the whole bot back to one UTC second in the last 30 days (v116 Phase 0).
#
#   scripts/ops/rollback_to.sh "2026-10-14 13:05:00" [--dry-run]
#
# Restores Postgres to the second (pgBackRest PITR), market_data/ (restic),
# .env (backups/env) and the bot + db images (backups/deploys.jsonl), then
# starts with scanning PAUSED -- unpause from the admin UI. Not rolled back, by
# design: Discord messages already posted, logs, telemetry, caches.
# Runs ON the VM as root. Spec: 2026-09-30-v116 section rollback_to.sh.
set -euo pipefail
cd /opt/swing-bot

TARGET="${1:?usage: rollback_to.sh '<UTC timestamp>' [--dry-run]}"
DRY_RUN=0
[ "${2:-}" = "--dry-run" ] && DRY_RUN=1
LOG=logs/rollback.log
mkdir -p backups
WORK="$(mktemp -d /opt/swing-bot/backups/rollback.XXXXXX)"   # same filesystem: mv is atomic
trap 'rm -rf "$WORK"' EXIT

RESTIC_PASSWORD="$(python3 scripts/ops/env_set.py --get RESTIC_PASSWORD)"
export RESTIC_PASSWORD
export RESTIC_REPOSITORY=/opt/swing-bot/backups/restic

# 1 + 3. Refuse an unrestorable target; resolve the artifacts current at it.
docker compose exec -T -u postgres db pgbackrest --stanza=swingbot --output=json info \
  </dev/null > "$WORK/pgbackrest.json"
restic snapshots --host swing-bot --tag market_data --json > "$WORK/restic.json"
PLAN="$(python3 scripts/ops/pitr_resolve.py --target "$TARGET" \
  --deploys backups/deploys.jsonl --env-dir backups/env \
  --restic-json "$WORK/restic.json" --pgbackrest-json "$WORK/pgbackrest.json")" \
  || { echo "$PLAN"; exit 2; }
eval "$PLAN"
echo "Target $TARGET resolves to:"
echo "  code       git $git_sha"
echo "  bot image  $bot_image"
echo "  db image   $db_image"
echo "  .env       $env_file"
echo "  market     restic $restic_id ($restic_time)"
if ! docker manifest inspect "$bot_image" >/dev/null || ! docker manifest inspect "$db_image" >/dev/null; then
  echo "REFUSE: an image recorded for the target is no longer on GHCR"
  exit 2
fi
if [ "$DRY_RUN" = 1 ]; then
  echo "Dry run: nothing changed."
  exit 0
fi

echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) rollback to $TARGET started (git $git_sha)" >> "$LOG"

# 2. Checkpoint of now, so the rollback itself can be undone. PITR opens a new
# timeline; a later restore can still target any second on the old one.
docker compose exec -T -u postgres db pgbackrest --stanza=swingbot --type=diff backup </dev/null
scripts/ops/restic_hourly.sh
python3 -m swingbot.core.infra.env_snapshot snapshot .env

# 4. Stop the writers.
docker compose stop bot admin

# 5. market_data, swapped in atomically.
restic restore "$restic_id" --target "$WORK/md" --include /opt/swing-bot/market_data
mv market_data "backups/market_data.pre-rollback-$(date -u +%Y%m%dT%H%M%SZ)"
mv "$WORK/md/opt/swing-bot/market_data" market_data

# 6. Config and code: the .env of the target, in place; the images of the target.
cat "$env_file" > .env
python3 scripts/ops/env_set.py SWING_BOT_IMAGE "$bot_image"
python3 scripts/ops/env_set.py SWING_BOT_DB_IMAGE "$db_image"
docker pull "$bot_image"
docker pull "$db_image"

# 7. Postgres to the second.
docker compose stop db
docker compose run --rm --no-deps -u postgres --entrypoint pgbackrest db \
  --stanza=swingbot --delta --type=time "--target=$target_pg" --target-action=promote restore
docker compose up -d --no-build --wait db

# 8. Pause scanning BEFORE the bot starts: otherwise it re-posts alerts for
# setups it had already alerted on after the target second.
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
echo "Restored: Postgres to $TARGET, market_data to $restic_time, .env $env_file, images of git $git_sha."
echo "Scanning is PAUSED. Unpause from the admin UI once the book looks right."
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) rollback to $TARGET finished" >> "$LOG"
