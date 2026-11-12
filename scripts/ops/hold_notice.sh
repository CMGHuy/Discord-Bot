#!/usr/bin/env bash
# Deploy hold notice (v220): prints the held message and posts it once to
# OPS_ALERT_WEBHOOK_URL, the VM-side ops alert path heartbeat_watch.sh uses.
#
#   bash scripts/ops/hold_notice.sh [APP_DIR]     # default /opt/swing-bot
#
# Run by the CI `hold` job on the VM (fetched from origin/main, because the
# checkout may be an older rollback target) when backups/deploy_hold.json
# exists. The last stdout line is the message; "no deploy hold" when there is
# none. Always exits 0: a failed post must not turn the hold check red.
# The webhook URL is read from .env without sourcing it and never printed.
set -uo pipefail
APP_DIR="${1:-/opt/swing-bot}"
HOLD_FILE="$APP_DIR/backups/deploy_hold.json"
UNREADABLE="deploy held by rollback (backups/deploy_hold.json unreadable)"

env_value() {
  sed -n "s/^[[:space:]]*$1[[:space:]]*=//p" "$APP_DIR/.env" 2>/dev/null | tail -1 | tr -d '\r' \
    | sed -e 's/^["'\'']//' -e 's/["'\'']$//' -e 's/[[:space:]]*$//'
}

held_message() {
  python3 - "$HOLD_FILE" <<'PY'
import json, sys
try:
    with open(sys.argv[1], encoding="utf-8") as fh:
        h = json.load(fh)
    print(f"deploy held by rollback to {h['sha']} ({h['reason']}, since {h['at']})")
except (OSError, ValueError, KeyError, TypeError):
    sys.exit(1)
PY
}

main() {
  local msg payload url
  if [ ! -f "$HOLD_FILE" ]; then echo "no deploy hold"; return 0; fi
  msg="$(held_message)" || msg="$UNREADABLE"
  url="$(env_value OPS_ALERT_WEBHOOK_URL)"
  if [ -n "$url" ]; then
    payload="$(python3 -c 'import json,sys; print(json.dumps({"content": sys.argv[1] + " -- release with /rollback --release"}))' "$msg")"
    curl -fsS -m 15 -o /dev/null -H 'Content-Type: application/json' -d "$payload" "$url" >/dev/null 2>&1 \
      || echo "hold_notice: ops notice not delivered" >&2
  fi
  echo "$msg"
}

main; exit 0
