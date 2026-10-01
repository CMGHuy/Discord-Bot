#!/usr/bin/env bash
# v116 staged flip, one stage (used on 2026-10-01 for every group; see the spec Status section). Runs ON the VM as root.
# Copy and run: ssh-hetzner.sh "cat > /tmp/v116_flip.sh" < scripts/ops/v116_flip_stage.sh ; ssh-hetzner.sh "NEW=... bash /tmp/v116_flip.sh"
#   NEW='<DB_STORES value>'  [TRUNC='<TRUNCATE table list>']  [IMPORTS='plans starred ...']  [CHECKPOINT=1]
# Aborts (touching nothing) when the last 10 minutes of logs or the dual parity are not clean.
# After the flip it re-checks parity and reverts DB_STORES to the previous value on any difference.
set -uo pipefail
cd /opt/swing-bot
: "${NEW:?set NEW to the new DB_STORES value}"
TRUNC="${TRUNC:-}"; IMPORTS="${IMPORTS:-}"; CHECKPOINT="${CHECKPOINT:-0}"
PREV="$(python3 scripts/ops/env_set.py --get DB_STORES)"
echo "prev=$PREV"; echo "new =$NEW"

ERR_RE='sqlalchemy\.exc|DatabaseUnavailable|StoreWriteHalt|dual\[|Traceback'
count_errors() { docker compose logs --since "$1" bot admin 2>&1 | grep -iE "$ERR_RE" | grep -v 'engine created' | wc -l; }
parity_dirty() { docker compose exec -T bot python scripts/db/parity_report.py --dual </dev/null 2>&1 | grep 'VERDICT' | grep -vc 'VERDICT: OK'; }
healthy_wait() { for _ in $(seq 1 40); do n=$(docker compose ps --format '{{.Name}} {{.Status}}' | grep -c healthy); [ "$n" -ge 3 ] && return 0; sleep 3; done; return 1; }
show_stages() { for s in bot admin; do docker compose exec -T "$s" python -c 'from swingbot import config; from swingbot.core.db import stages; print(sorted(stages.parse(config.DB_STORES).items()))' </dev/null; done; }

echo "== preflight"
e=$(count_errors 10m); echo "database error lines, last 10m: $e"
d=$(parity_dirty); echo "parity blocks not OK: $d"
if [ "$e" != 0 ] || [ "$d" != 0 ]; then echo "ABORT: not clean, nothing changed"; exit 3; fi

echo "== wait for a gap between scans (no scan running; >=25s after one completed, >=60s before the next)"
scan_running() { [ "$(docker compose exec -T db psql -U swingbot -d swingbot -tAc "select count(*) from runtime_flags where name='scan_running'" </dev/null 2>/dev/null | tr -d '[:space:]')" = 1 ] || [ -f data/scan_running.flag -a "$(( $(date +%s) - $(stat -c %Y data/scan_running.flag) ))" -lt 600 ]; }
for _ in $(seq 1 200); do
  last=$(docker compose logs --since 7m bot 2>&1 | grep 'Session scan complete' | tail -1 | awk '{print $4}' | cut -d, -f1)
  if [ -n "$last" ] && ! scan_running; then
    age=$(( $(date +%s) - $(date -u -d "$(date -u +%F) $last" +%s) )) || age=0
    if [ "$age" -ge 25 ] && [ "$age" -le 200 ]; then break; fi
  fi
  sleep 3
done
date -u

if [ "$CHECKPOINT" = 1 ]; then
  echo "== checkpoint: pgBackRest differential backup + pg_dump"
  docker compose exec -T -u postgres db pgbackrest --stanza=swingbot --type=diff backup </dev/null 2>&1 | tail -2
  ./scripts/ops/backup_db.sh 2>&1 | tail -2
  echo "CHECKPOINT_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
fi

if [ -n "$TRUNC" ]; then
  echo "== truncate: $TRUNC"
  docker compose exec -T db psql -U swingbot -d swingbot -v ON_ERROR_STOP=1 -c "TRUNCATE $TRUNC RESTART IDENTITY CASCADE" </dev/null || { echo "ABORT: truncate failed"; exit 4; }
fi

echo "== flip + restart"
python3 scripts/ops/env_set.py DB_STORES "$NEW" >/dev/null
docker compose restart bot admin </dev/null
healthy_wait || echo "WARN: not all healthy after restart"
show_stages

if [ -n "$IMPORTS" ]; then
  echo "== imports (foreign-key order)"
  for s in $IMPORTS; do docker compose exec -T bot python "scripts/db/import_${s}.py" </dev/null | tail -4; done
fi

echo "== parity after"
docker compose exec -T bot python scripts/db/parity_report.py --dual </dev/null 2>&1 | grep -E '^\[|VERDICT|records|rows'
d=$(parity_dirty)
if [ "$d" != 0 ]; then
  echo "REVERT: parity not clean ($d), restoring $PREV"
  python3 scripts/ops/env_set.py DB_STORES "$PREV" >/dev/null
  docker compose restart bot admin </dev/null; healthy_wait || true; show_stages
  echo "STAGE_RESULT=REVERTED"; exit 5
fi
echo "STAGE_RESULT=OK $(date -u +%FT%TZ)"
