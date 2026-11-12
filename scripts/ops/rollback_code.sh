#!/usr/bin/env bash
# Code-only rollback (v220): put the VM's checkout and bot image back to an
# earlier main commit while keeping every row of trading data.
#
#   rollback_code.sh --resolve <target>      # one target -> {"sha","image","form","label"}
#   rollback_code.sh --candidates            # picker rows (JSON)
#   rollback_code.sh <sha> <image> --dry-run # every check; nothing changes
#   rollback_code.sh <sha> <image> --i-mean-it [--reason TEXT] [--keep-refresher] [--allow-writer-drift]
#
# Never touched: Postgres contents, the db container, .env beyond the
# SWING_BOT_IMAGE pin, the market data cache. No schema migration runs;
# SWING_BOT_DB_IMAGE stays. While rolled back, backups/deploy_hold.json holds
# every deploy (CI hold job, deploy.sh) until --release.
# Exit: 0 pass, 1 failed (previous code and image restored), 2 refused
# (nothing changed), 3 no-op (target already running).
# Runs ON the VM as root. Its first act copies itself into $WORK and re-execs,
# and the planner modules are written into $WORK from $ROLLBACK_TOOLS_REF, so
# checking out an older tree (which may lack all of them) rewrites nothing
# that is running. Spec: docs/superpowers/specs/2026-11-08-v220-code-only-rollback-design.md
set -Eeuo pipefail

APP_DIR="${ROLLBACK_APP_DIR:-/opt/swing-bot}"
TOOLS_REF="${ROLLBACK_TOOLS_REF:-origin/main}"
DRILL="${ROLLBACK_DRILL:-0}"
TOOLS="rollback_plan.py rollback_migrations.py rollback_checks.py rollback_window.py"
HOLD=backups/deploy_hold.json
LOG=logs/rollback.log

usage() {
  echo "usage: rollback_code.sh --resolve <target> | --candidates" >&2
  echo "       rollback_code.sh <sha40> <image> --dry-run|--i-mean-it [--reason TEXT] [--keep-refresher] [--allow-writer-drift]" >&2
}
stamp() { date -u +%Y-%m-%dT%H:%M:%SZ; }
log() { echo "$(stamp) rollback_code $*" | tee -a "$LOG"; }
refuse() {
  echo "REFUSE: $*" >&2; echo "$(stamp) rollback_code refused: $*" >> "$LOG"
  exit 2
}
git_d() { runuser -u deploy -- git -C "$APP_DIR" "$@"; }
planner() { runuser -u deploy -- python3 "$WORK/rollback_plan.py" "$@"; }
env_get() { python3 scripts/ops/env_set.py --get "$1"; }
json_field() {
  python3 -c 'import json,sys; v=json.load(open(sys.argv[1])).get(sys.argv[2]); print("" if v is None else v)' "$1" "$2"
}

parse_args() {
  ACTION=""; TARGET=""; SHA=""; IMAGE=""; MODE=""
  REASON="manual rollback"; KEEP_REFRESHER=0; ALLOW_DRIFT=0
  case "${1:-}" in
    --resolve) [ $# -eq 2 ] || return 1; ACTION=resolve; TARGET="$2"; return 0 ;;
    --candidates) [ $# -eq 1 ] || return 1; ACTION=candidates; return 0 ;;
    ''|-*) return 1 ;;
    *) [ $# -ge 3 ] || return 1; ACTION=rollback; SHA="$1"; IMAGE="$2"; MODE="$3"; shift 3 ;;
  esac
  while [ $# -gt 0 ]; do
    case "$1" in
      --reason) [ $# -ge 2 ] || return 1; REASON="$2"; shift 2 ;;
      --keep-refresher) KEEP_REFRESHER=1; shift ;;
      --allow-writer-drift) ALLOW_DRIFT=1; shift ;;
      *) return 1 ;;
    esac
  done
  case "$MODE" in --dry-run|--i-mean-it) ;; *) return 1 ;; esac
  [[ "$SHA" =~ ^[0-9a-f]{40}$ ]] && [ -n "$IMAGE" ]
}

fetch_tools() {
  local f
  git_d fetch -q origin main
  for f in $TOOLS; do
    git_d show "$TOOLS_REF:scripts/ops/$f" > "$WORK/$f"
  done
}

run_check() {
  local rc=0 extra=()
  FROM_SHA="$(git_d rev-parse HEAD)"
  FROM_REF="$(git_d symbolic-ref -q --short HEAD || true)"
  FROM_IMAGE="$(env_get SWING_BOT_IMAGE)"
  DB_IMAGE="$(env_get SWING_BOT_DB_IMAGE)"
  FROM_REFRESHER=keep-stopped
  if [ -n "$(docker compose ps -q --status running refresher 2>/dev/null)" ]; then FROM_REFRESHER=start; fi
  if [ "$ALLOW_DRIFT" = 1 ]; then extra+=(--allow-writer-drift); fi
  planner check "$SHA" --image "$IMAGE" --repo "$APP_DIR" --ref "$TOOLS_REF" --env "$APP_DIR/.env" \
    --running-sha "$FROM_SHA" --hold "$APP_DIR/$HOLD" "${extra[@]}" > "$WORK/report.json" || rc=$?
  cat "$WORK/report.json"
  case "$rc" in
    0) ;;
    3) log "no-op: $SHA is already running"; exit 3 ;;
    2) refuse "safety checks failed (report above)" ;;
    *) echo "rollback_code: planner failed (exit $rc)" >&2; exit 1 ;;
  esac
  START_REFRESHER="$(json_field "$WORK/report.json" refresher)"
  if [ "$KEEP_REFRESHER" = 1 ]; then START_REFRESHER=keep-stopped; fi
}

host_checks() {
  local dirty
  docker manifest inspect "$IMAGE" >/dev/null || refuse "image $IMAGE is not on GHCR"
  dirty="$(git_d status --porcelain --untracked-files=no)"
  if [ -n "$dirty" ]; then refuse "tracked files have local changes (mirror them first): $dirty"; fi
}

print_plan() {
  echo "Code-only rollback plan:"
  echo "  from     git $FROM_SHA  image $FROM_IMAGE"
  echo "  to       git $SHA  image $IMAGE"
  echo "  db image $DB_IMAGE (unchanged); refresher: $START_REFRESHER; reason: $REASON"
  if [ -f "$HOLD" ]; then echo "  replaces the hold: $(cat "$HOLD")"; fi
}

run_rollback() {
  run_check
  host_checks
  print_plan
  if [ "$MODE" = --dry-run ]; then echo "Dry run: nothing changed."; exit 0; fi
  refuse "--i-mean-it is not wired yet (V220-9b)"
}

main() {
  if ! parse_args "$@"; then usage; exit 2; fi
  SELF="$(readlink -f "$0")"
  cd "$APP_DIR"
  mkdir -p backups logs
  if [ -z "${ROLLBACK_WORK:-}" ]; then
    WORK="$(mktemp -d "$APP_DIR/backups/rollback.XXXXXX")"
    chmod 755 "$WORK"
    cp "$SELF" "$WORK/rollback_code.sh"
    ROLLBACK_WORK="$WORK" exec bash "$WORK/rollback_code.sh" "$@"
  fi
  WORK="$ROLLBACK_WORK"
  trap 'rm -rf "$WORK"' EXIT
  fetch_tools
  case "$ACTION" in
    resolve) planner resolve "$TARGET" --repo "$APP_DIR" --ref "$TOOLS_REF" \
               --deploys "$APP_DIR/backups/deploys.jsonl" --current-image "$(env_get SWING_BOT_IMAGE)" || exit $? ;;
    candidates) planner candidates --repo "$APP_DIR" --ref "$TOOLS_REF" \
               --deploys "$APP_DIR/backups/deploys.jsonl" --stable-dir "$APP_DIR/backups/stable" || exit $? ;;
    rollback) run_rollback ;;
  esac
}

main "$@"; exit $?
