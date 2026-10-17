#!/usr/bin/env bash
# v148 O3: out-of-process liveness check for the bot. Runs from cron on the
# Hetzner VM every 5 minutes, 24/7 (installed by install_heartbeat_watch_cron.sh).
#
# Reads doc->>'timestamp' from the singleton bot_heartbeat row. Only the bot's
# runstate._write_heartbeat writes it, at the start of every tick, in session
# or not; admin-side writes (an unpause) bump the `ts` column, never this
# field. Stale when older than max(15 min, 3 x SCAN_INTERVAL_MINUTES); a failed
# query is an incident of its own ("unreadable"). Posts to
# OPS_ALERT_WEBHOOK_URL once per incident and once on recovery; the last
# delivered verdict lives in logs/heartbeat_watch.state; every run appends one
# verdict line to logs/heartbeat_watch.log, which keeps its last 2000 lines.
#
# Owner: the partner (ops). Permanent: removed only when a monitor outside the
# VM replaces it, by its own spec. It dies with the VM.
#
#   heartbeat_watch.sh                       # the cron run
#   heartbeat_watch.sh --dry-run --age 42    # verdict for a given age (s): no psql,
#                                            # no curl, no state write
#   heartbeat_watch.sh --dry-run --age ''    # verdict for an unreadable heartbeat
#   heartbeat_watch.sh --test                # force one test post (exit 1 if not delivered)
#
# .env is read with grep | cut, never sourced: a `$` in any value would be
# expanded (docs/deploy/DEPLOY_HETZNER.md).
set -euo pipefail

ROOT="${HEARTBEAT_WATCH_ROOT:-/opt/swing-bot}"
LOG="$ROOT/logs/heartbeat_watch.log"
STATE_FILE="$ROOT/logs/heartbeat_watch.state"
MAX_LOG_LINES=2000
MIN_STALE_S=900
SQL="SELECT floor(extract(epoch FROM now() - (doc->>'timestamp')::timestamptz))::bigint FROM bot_heartbeat WHERE key = 'bot'"

DRY_RUN=0
TEST_POST=0
AGE_GIVEN=0
AGE_ARG=""

usage() {
  echo "usage: heartbeat_watch.sh [--dry-run --age <seconds>] [--test]" >&2
  exit 2
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --age) [ "$#" -ge 2 ] || usage; AGE_ARG="$2"; AGE_GIVEN=1; shift ;;
    --test) TEST_POST=1 ;;
    *) usage ;;
  esac
  shift
done
[ "$DRY_RUN" = "$AGE_GIVEN" ] || usage

env_value() {   # KEY -> its value in .env, or nothing
  { grep "^$1=" "$ROOT/.env" 2>/dev/null || true; } | tail -n 1 | cut -d= -f2- | tr -d '\r'
}

now_iso() { date -u +%Y-%m-%dT%H:%M:%SZ; }

record() {      # print one line, append it to the log, keep the last 2000 lines
  echo "$1"
  echo "$1" >> "$LOG"
  tail -n "$MAX_LOG_LINES" "$LOG" > "$LOG.tmp"
  mv "$LOG.tmp" "$LOG"
}

stale_after() { # seconds: max(900, 3 x SCAN_INTERVAL_MINUTES x 60)
  local minutes seconds
  minutes="$(env_value SCAN_INTERVAL_MINUTES)"
  case "$minutes" in ''|*[!0-9]*) minutes=5 ;; esac
  seconds=$((minutes * 180))
  [ "$seconds" -ge "$MIN_STALE_S" ] || seconds="$MIN_STALE_S"
  echo "$seconds"
}

read_age() {    # seconds since the bot's last heartbeat, or nothing
  { (cd "$ROOT" && docker compose exec -T db psql -U swingbot -d swingbot -tA \
      -v ON_ERROR_STOP=1 -c "$SQL" </dev/null 2>/dev/null) || true; } | tr -d '[:space:]'
}

verdict_for() { # age threshold -> ok | stale | unreadable
  if ! [[ "$1" =~ ^-?[0-9]+$ ]]; then echo unreadable; return; fi
  if [ "$1" -gt "$2" ]; then echo stale; else echo ok; fi
}

action_for() {  # verdict previous -> alert | recover | none
  if [ "$1" != ok ] && [ "$1" != "$2" ]; then echo alert
  elif [ "$1" = ok ] && [ -n "$2" ] && [ "$2" != ok ]; then echo recover
  else echo none; fi
}

message_for() { # action verdict age threshold previous
  local host="${HOSTNAME:-the VM}"
  case "$1:$2" in
    alert:stale) echo "[swingbot ops] Heartbeat STALE on $host: the bot last wrote its heartbeat $3s ago (threshold $4s). The bot process may be dead or its event loop blocked. Check docker compose ps and docker compose logs --tail 200 bot." ;;
    alert:unreadable) echo "[swingbot ops] Heartbeat UNREADABLE on $host: cannot read the bot_heartbeat row from Postgres. Check docker compose ps (is db up?)." ;;
    *) echo "[swingbot ops] Heartbeat RECOVERED on $host: the bot wrote its heartbeat $3s ago (was $5)." ;;
  esac
}

post() {        # message -> 0 when delivered; never echoes the URL
  local url
  url="$(env_value OPS_ALERT_WEBHOOK_URL)"
  [ -n "$url" ] || return 1
  curl -fsS -m 15 -o /dev/null -H 'Content-Type: application/json' \
    -d "{\"content\":\"$1\"}" "$url"
}

mkdir -p "$ROOT/logs"
touch "$LOG"

if [ "$TEST_POST" = 1 ]; then
  if post "[swingbot ops] heartbeat_watch TEST post from ${HOSTNAME:-the VM} at $(now_iso). No action needed."; then
    record "$(now_iso) test delivered=yes"
    exit 0
  fi
  record "$(now_iso) test delivered=no (OPS_ALERT_WEBHOOK_URL unset or the post failed)"
  exit 1
fi

threshold="$(stale_after)"
if [ "$DRY_RUN" = 1 ]; then age="$AGE_ARG"; else age="$(read_age)"; fi
verdict="$(verdict_for "$age" "$threshold")"
previous="$(cat "$STATE_FILE" 2>/dev/null || true)"
action="$(action_for "$verdict" "$previous")"
line="$(now_iso) verdict=$verdict age_s=${age:-none} threshold_s=$threshold previous=${previous:-none} action=$action"

if [ "$DRY_RUN" = 1 ]; then
  record "$line dry_run=1"
  exit 0
fi
if [ "$action" = none ]; then
  echo "$verdict" > "$STATE_FILE"
  record "$line"
  exit 0
fi
if [ -z "$(env_value OPS_ALERT_WEBHOOK_URL)" ]; then
  # State untouched: the incident posts on the first run after a URL is set.
  record "$line delivered=no-webhook"
  exit 0
fi
if post "$(message_for "$action" "$verdict" "$age" "$threshold" "$previous")"; then
  echo "$verdict" > "$STATE_FILE"
  record "$line delivered=yes"
else
  # State untouched: retried on the next run.
  record "$line delivered=failed"
fi
exit 0
