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
# v184: a second check follows the heartbeat check, for the trade monitor's own
# `monitor` key in the same row (swingbot/commands/scanning/monitor_liveness.py,
# written at the end of every 60 s tick, at most every 120 s unless something
# material changed). Verdicts: monitor_stale (last tick ended > 300 s ago, any
# hour), stops_unchecked (NYSE regular session, positions open or unknown, not
# all checked for > STOPS_UNCHECKED_S, counted from the later of the last clean
# tick and today's 09:30 ET), not_deployed (no key: logged, silent), unreadable
# (not posted when the heartbeat is unreadable in the same run). Its own line
# ("<iso> monitor verdict=..."), after the heartbeat line in the same log, and
# its own state file, logs/monitor_watch.state. Nothing in it can change the
# heartbeat line, the heartbeat state or the exit code.
#
# Owner: the partner (ops), for both checks and both state files. Permanent:
# removed only when a monitor outside the VM replaces it, by its own spec,
# together with logs/monitor_watch.state. It dies with the VM.
#
#   heartbeat_watch.sh                       # the cron run: both checks
#   heartbeat_watch.sh --dry-run --age 42    # heartbeat verdict for a given age (s): no psql,
#                                            # no curl, no state write
#   heartbeat_watch.sh --dry-run --age ''    # verdict for an unreadable heartbeat
#   heartbeat_watch.sh --dry-run --monitor-age 42 [--priced-age 700] [--market-open true]
#                      [--positions 3|null]  # monitor verdict only (defaults 0, false, 0)
#   heartbeat_watch.sh --dry-run --monitor-age absent   # a pre-v184 row: not_deployed
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

MONITOR_STATE_FILE="$ROOT/logs/monitor_watch.state"
MONITOR_STALE_S=300
STOPS_UNCHECKED_S=600
# One row: tick_age|priced_age|market_open|positions|unquoted_count|unquoted|fetch_failed|check_errors,
# or the literal `absent` (no monitor key). priced_age counts from the later of
# priced_at (or started_at after a restart) and today's 09:30 ET.
MONITOR_SQL="SELECT CASE WHEN NOT (doc ? 'monitor') THEN 'absent' ELSE concat_ws('|', coalesce(floor(extract(epoch FROM now() - (doc->'monitor'->>'tick_at')::timestamptz))::bigint::text, ''), coalesce(floor(extract(epoch FROM now() - greatest(coalesce((doc->'monitor'->>'priced_at')::timestamptz, (doc->'monitor'->>'started_at')::timestamptz), ((now() AT TIME ZONE 'America/New_York')::date + time '09:30') AT TIME ZONE 'America/New_York')))::bigint::text, ''), coalesce(doc->'monitor'->>'market_open', ''), CASE WHEN jsonb_typeof(doc->'monitor'->'positions') = 'array' THEN jsonb_array_length(doc->'monitor'->'positions')::text ELSE 'null' END, coalesce(doc->'monitor'->>'unquoted_count', '0'), coalesce((SELECT string_agg(value, ',') FROM jsonb_array_elements_text(coalesce(doc->'monitor'->'unquoted', '[]'::jsonb))), ''), coalesce(doc->'monitor'->>'fetch_failed', 'false'), coalesce((SELECT string_agg(value, ',') FROM jsonb_array_elements_text(coalesce(doc->'monitor'->'check_errors', '[]'::jsonb))), '')) END FROM bot_heartbeat WHERE key = 'bot'"

DRY_RUN=0
TEST_POST=0
AGE_GIVEN=0
AGE_ARG=""
MON_GIVEN=0
MON_AGE_ARG=0
PRICED_AGE_ARG=0
MARKET_OPEN_ARG=false
POSITIONS_ARG=0

usage() {
  echo "usage: heartbeat_watch.sh [--dry-run [--age <seconds>] [--monitor-age <s|absent> --priced-age <s> --market-open <true|false> --positions <n|null>]] [--test]" >&2
  exit 2
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --age) [ "$#" -ge 2 ] || usage; AGE_ARG="$2"; AGE_GIVEN=1; shift ;;
    --monitor-age) [ "$#" -ge 2 ] || usage; MON_AGE_ARG="$2"; MON_GIVEN=1; shift ;;
    --priced-age) [ "$#" -ge 2 ] || usage; PRICED_AGE_ARG="$2"; MON_GIVEN=1; shift ;;
    --market-open) [ "$#" -ge 2 ] || usage; MARKET_OPEN_ARG="$2"; MON_GIVEN=1; shift ;;
    --positions) [ "$#" -ge 2 ] || usage; POSITIONS_ARG="$2"; MON_GIVEN=1; shift ;;
    --test) TEST_POST=1 ;;
    *) usage ;;
  esac
  shift
done
# A dry run needs --age, a monitor flag, or both; those flags need a dry run.
# Bare --dry-run still exits 2.
[ "$DRY_RUN" = 1 ] || [ "$AGE_GIVEN$MON_GIVEN" = 00 ] || usage
[ "$DRY_RUN" = 0 ] || [ "$AGE_GIVEN$MON_GIVEN" != 00 ] || usage

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

heartbeat_check() { # the v148 heartbeat verdict: one line, its own state file; sets HB_VERDICT
  local threshold age verdict previous action line
  threshold="$(stale_after)"
  if [ "$DRY_RUN" = 1 ]; then age="$AGE_ARG"; else age="$(read_age)"; fi
  verdict="$(verdict_for "$age" "$threshold")"
  HB_VERDICT="$verdict"
  previous="$(cat "$STATE_FILE" 2>/dev/null || true)"
  action="$(action_for "$verdict" "$previous")"
  line="$(now_iso) verdict=$verdict age_s=${age:-none} threshold_s=$threshold previous=${previous:-none} action=$action"

  if [ "$DRY_RUN" = 1 ]; then
    record "$line dry_run=1"
    return 0
  fi
  if [ "$action" = none ]; then
    echo "$verdict" > "$STATE_FILE"
    record "$line"
    return 0
  fi
  if [ -z "$(env_value OPS_ALERT_WEBHOOK_URL)" ]; then
    # State untouched: the incident posts on the first run after a URL is set.
    record "$line delivered=no-webhook"
    return 0
  fi
  if post "$(message_for "$action" "$verdict" "$age" "$threshold" "$previous")"; then
    echo "$verdict" > "$STATE_FILE"
    record "$line delivered=yes"
  else
    # State untouched: retried on the next run.
    record "$line delivered=failed"
  fi
}

read_monitor() {    # one '|' row from the monitor key, the literal absent, or nothing
  { (cd "$ROOT" && docker compose exec -T db psql -U swingbot -d swingbot -tA \
      -v ON_ERROR_STOP=1 -c "$MONITOR_SQL" </dev/null 2>/dev/null) || true; } | tr -d '\r\n'
}

monitor_row() {     # the dry-run flags as a row, or the live row
  if [ "$DRY_RUN" = 0 ]; then read_monitor; return 0; fi
  if [ "$MON_AGE_ARG" = absent ]; then echo absent; return 0; fi
  echo "$MON_AGE_ARG|$PRICED_AGE_ARG|$MARKET_OPEN_ARG|$POSITIONS_ARG|0||false|"
}

is_int() { [[ "$1" =~ ^-?[0-9]+$ ]]; }

monitor_verdict_for() { # tick_age priced_age market_open positions -> one verdict
  if [ "$1" = absent ]; then echo not_deployed; return 0; fi
  if ! is_int "$1"; then echo unreadable; return 0; fi
  if [ "$1" -gt "$MONITOR_STALE_S" ]; then echo monitor_stale; return 0; fi
  if [ "$3" != true ] || [ "$4" = 0 ]; then echo ok; return 0; fi
  if ! is_int "$2"; then echo unreadable; return 0; fi
  if [ "$2" -gt "$STOPS_UNCHECKED_S" ]; then echo stops_unchecked; else echo ok; fi
}

unchecked_count() { # positions unquoted_count check_errors -> n for the message, or unknown
  local errors=0
  if [ "$1" = null ] || ! is_int "$2"; then echo unknown; return 0; fi
  if [ -n "$3" ]; then errors=$(( $(printf '%s' "$3" | tr -cd ',' | wc -c) + 1 )); fi
  echo $(( $2 + errors ))
}

monitor_message_for() { # action verdict tick_age priced_age n tickers fetch_failed check_errors previous
  local host="${HOSTNAME:-the VM}"
  case "$1:$2" in
    alert:monitor_stale) echo "[swingbot ops] Stop monitor STALE on $host: last tick ended $3s ago (threshold ${MONITOR_STALE_S}s). Open stops are not being checked." ;;
    alert:stops_unchecked) echo "[swingbot ops] Stops UNCHECKED on $host: $5 position(s) not checked for $4s during the regular session (${6:-none}; fetch_failed=${7:-false}; check_errors=${8:-none})." ;;
    alert:unreadable) echo "[swingbot ops] Stop monitor UNREADABLE on $host: cannot read the monitor key from bot_heartbeat. Check docker compose ps (is db up?)." ;;
    *) echo "[swingbot ops] Stop monitor RECOVERED on $host: last tick ended $3s ago and stops are being checked (was $9)." ;;
  esac
}

monitor_deliver() { # verdict action line message -> logs the line with one suffix, keeps the state
  if [ "$DRY_RUN" = 1 ]; then record "$3 dry_run=1"; return 0; fi
  if [ "$1" = unreadable ] && [ "$HB_VERDICT" = unreadable ]; then
    # One database outage posts once (the heartbeat's post); state untouched.
    record "$3 suppressed=heartbeat-unreadable"
    return 0
  fi
  if [ "$1" = not_deployed ]; then record "$3"; return 0; fi   # pre-v184 row: silent, state untouched
  if [ "$2" = none ]; then
    echo "$1" > "$MONITOR_STATE_FILE"
    record "$3"
    return 0
  fi
  if [ -z "$(env_value OPS_ALERT_WEBHOOK_URL)" ]; then
    record "$3 delivered=no-webhook"   # state untouched: posts once a URL is set
    return 0
  fi
  if post "$4"; then
    echo "$1" > "$MONITOR_STATE_FILE"
    record "$3 delivered=yes"
  else
    record "$3 delivered=failed"       # state untouched: retried on the next run
  fi
}

monitor_check() {   # the v184 stop-monitor verdict: its own line after the heartbeat's, its own state
  local row tick_age priced_age market_open positions unquoted_count tickers fetch_failed check_errors
  local verdict previous action line n message
  row="$(monitor_row)"
  IFS='|' read -r tick_age priced_age market_open positions unquoted_count tickers fetch_failed \
    check_errors <<< "$row" || true
  verdict="$(monitor_verdict_for "$tick_age" "$priced_age" "$market_open" "$positions")"
  previous="$(cat "$MONITOR_STATE_FILE" 2>/dev/null || true)"
  action=none
  [ "$verdict" = not_deployed ] || action="$(action_for "$verdict" "$previous")"
  line="$(now_iso) monitor verdict=$verdict tick_age_s=${tick_age:-none} priced_age_s=${priced_age:-none} market_open=${market_open:-none} positions=${positions:-none} previous=${previous:-none} action=$action"
  n="$(unchecked_count "$positions" "$unquoted_count" "$check_errors")"
  message="$(monitor_message_for "$action" "$verdict" "$tick_age" "$priced_age" "$n" "$tickers" "$fetch_failed" "$check_errors" "$previous")"
  monitor_deliver "$verdict" "$action" "$line" "$message"
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

HB_VERDICT=""
if [ "$DRY_RUN" = 0 ] || [ "$AGE_GIVEN" = 1 ]; then heartbeat_check; fi
if [ "$DRY_RUN" = 0 ] || [ "$MON_GIVEN" = 1 ]; then
  monitor_check || record "$(now_iso) monitor verdict=error action=none"
fi
exit 0
