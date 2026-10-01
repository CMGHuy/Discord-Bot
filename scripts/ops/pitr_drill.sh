#!/usr/bin/env bash
# PITR drill (v116 Phase 0): prove a restore lands on an exact second.
#
# Writes one mark before and one after a target second into a throwaway
# `pitr_drill` schema in production (outside schema.py; nothing reads it),
# restores that second into the scratch project deploy/db/docker-compose.drill.yml,
# and checks: the "before" mark is there, the "after" mark is not, and a known
# trade record and the whole signal_state table hash to what production held at
# the target. Appends to logs/pitr_drill.log; last line is the VERDICT.
# Runs ON the VM as root; re-runnable (V116-33 repeats it within 7 days of Phase 4).
set -euo pipefail
cd /opt/swing-bot
LOG=logs/pitr_drill.log
DRILL="docker compose -p swingbot-drill -f deploy/db/docker-compose.drill.yml"
SWING_BOT_DB_IMAGE="$(python3 scripts/ops/env_set.py --get SWING_BOT_DB_IMAGE)"
export SWING_BOT_DB_IMAGE
psql_prod() { docker compose exec -T db psql -U swingbot -d swingbot -tA -v ON_ERROR_STOP=1 -c "$1" </dev/null; }
psql_drill() { $DRILL exec -T db psql -U swingbot -d swingbot -tA -v ON_ERROR_STOP=1 -c "$1" </dev/null; }
TRADE_SQL="SELECT coalesce(md5(doc::text || status), 'none') FROM trades ORDER BY trade_id LIMIT 1"
STATE_SQL="SELECT md5(coalesce(string_agg(key || doc::text, ',' ORDER BY key), '')) FROM signal_state"

{
echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) PITR drill (db image $SWING_BOT_DB_IMAGE) ==="
psql_prod "CREATE SCHEMA IF NOT EXISTS pitr_drill"
psql_prod "CREATE TABLE IF NOT EXISTS pitr_drill.marks (id bigserial PRIMARY KEY, note text NOT NULL, at timestamptz NOT NULL DEFAULT clock_timestamp())"
RUN="drill-$(date -u +%Y%m%dT%H%M%SZ)"
psql_prod "INSERT INTO pitr_drill.marks (note) VALUES ('${RUN}-before')"
sleep 2
TARGET="$(psql_prod "SELECT to_char(clock_timestamp() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS') || '+00'")"
TRADE_AT="$(psql_prod "$TRADE_SQL")"
STATE_AT="$(psql_prod "$STATE_SQL")"
sleep 2
psql_prod "INSERT INTO pitr_drill.marks (note) VALUES ('${RUN}-after')"
psql_prod "SELECT pg_switch_wal()" >/dev/null
for _ in $(seq 1 60); do
  [ "$(psql_prod "SELECT last_archived_time > now() - interval '2 minutes' FROM pg_stat_archiver")" = "t" ] && break
  sleep 5
done
echo "target=$TARGET trade_md5=$TRADE_AT state_md5=$STATE_AT"

$DRILL --profile restore down -v --remove-orphans >/dev/null 2>&1 || true
$DRILL --profile restore run --rm --entrypoint sh restore \
  -c 'mkdir -p /var/lib/postgresql/18/docker && chmod 700 /var/lib/postgresql/18/docker'
DRILL_TARGET="$TARGET" $DRILL --profile restore run --rm restore
$DRILL up -d --wait db
for _ in $(seq 1 60); do
  [ "$(psql_drill "SELECT NOT pg_is_in_recovery()")" = "t" ] && break
  sleep 5
done
BEFORE="$(psql_drill "SELECT count(*) FROM pitr_drill.marks WHERE note = '${RUN}-before'")"
AFTER="$(psql_drill "SELECT count(*) FROM pitr_drill.marks WHERE note = '${RUN}-after'")"
TRADE_R="$(psql_drill "$TRADE_SQL")"
STATE_R="$(psql_drill "$STATE_SQL")"
echo "restored: before_mark=$BEFORE after_mark=$AFTER trade_md5=$TRADE_R state_md5=$STATE_R"
ok=1
[ "$BEFORE" = "1" ] || ok=0
[ "$AFTER" = "0" ] || ok=0
[ "$TRADE_R" = "$TRADE_AT" ] || ok=0
[ "$STATE_R" = "$STATE_AT" ] || ok=0
$DRILL --profile restore down -v --remove-orphans
psql_prod "DELETE FROM pitr_drill.marks WHERE at < now() - interval '30 days'" >/dev/null
if [ "$ok" = 1 ]; then
  echo "VERDICT $(date -u +%F) target=$TARGET PASS"
else
  echo "VERDICT $(date -u +%F) target=$TARGET FAIL"
fi
} 2>&1 | tee -a "$LOG"
