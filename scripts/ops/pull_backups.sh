#!/usr/bin/env bash
# Pull a verified rebuild-from-zero set off the VM into backups/ (v120 section 2).
# Dev machine only (Git Bash). Reaches the VM solely through ssh-hetzner.sh, with
# the remote script piped over stdin.
#   bash scripts/ops/pull_backups.sh                  # normal pull
#   bash scripts/ops/pull_backups.sh --stable <name>  # fetch one pinned stable point
# Nothing here ever deletes under backups/market_data/ or backups/stable/.
# backups/ is the MAIN worktree's, so a pull made from a worktree session
# survives that worktree being removed (SWINGBOT_BACKUPS_DIR overrides it).
set -euo pipefail
cd "$(dirname "$0")/../.."
SSH_HETZNER="${SSH_HETZNER:-E:/Documents/Private/Projects/Discord-Bot/scripts/ops/ssh-hetzner.sh}"

# The main worktree's root: the parent of git's common dir. Falls back to this
# checkout when git is unavailable or the result is not a directory.
resolve_main_root() {
  local m
  MAIN_ROOT="$(dirname "$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null)")" || MAIN_ROOT=""
  if [ -n "$MAIN_ROOT" ] && [ "$MAIN_ROOT" != "." ] && [ -d "$MAIN_ROOT" ]; then
    m="$MAIN_ROOT"
  else
    m="$PWD"
  fi
  MAIN_ROOT="$m"
}
resolve_main_root
B="${SWINGBOT_BACKUPS_DIR:-$MAIN_ROOT/backups}"
# PULL_STAMP is a test seam; a real run takes the UTC minute.
STAMP="${PULL_STAMP:-$(date -u +%Y-%m-%dT%H-%MZ)}"

# The VM-side script. Quoted heredoc: nothing expands locally. Arguments (mode,
# stamp or name, since) are plain words after `bash -s --`.
read -r -d '' REMOTE <<'REMOTE_EOF' || true
set -euo pipefail
cd /opt/swing-bot
MODE="$1"
ARG="${2:-}"
SINCE="${3:-0}"
case "$MODE" in
  stage)
    OUT="backups/outbox/$ARG"
    WORK="$(mktemp -d)"
    trap 'rm -rf "$WORK"' EXIT
    # An aborted earlier pull may have left an outbox folder (it holds a copy of .env).
    if [ -d backups/outbox ]; then
      find backups/outbox -mindepth 1 -maxdepth 1 -mmin +120 -exec rm -rf {} +
    fi
    # git runs as the checkout's owner: root gets "dubious ownership" and an empty sha.
    GIT_SHA="$(runuser -u deploy -- git rev-parse HEAD)"
    [ -n "$GIT_SHA" ] || { echo "pull_backups: could not read the git sha as deploy" >&2; exit 1; }
    mkdir -p backups/outbox
    chmod 700 backups/outbox
    mkdir "$OUT"
    # </dev/null: this script itself arrives on stdin, so no child may read it.
    BACKUP_OUT="$(./scripts/ops/backup_db.sh </dev/null)"
    DUMP="$(printf '%s\n' "$BACKUP_OUT" | sed -n 's/^backup_db: wrote \(.*\) (.*)$/\1/p' | tail -n 1)"
    if [ -z "$DUMP" ] || [ ! -f "$DUMP" ]; then
      echo "pull_backups: could not find the dump backup_db.sh wrote ('$DUMP')" >&2
      exit 1
    fi
    cp "$DUMP" "$OUT/db.sql.gz"
    install -m 600 .env "$OUT/env"
    cp backups/deploys.jsonl "$OUT/deploys.jsonl"
    tail -n 1 backups/deploys.jsonl > "$WORK/deploy.json"
    # market_data is live: GNU tar exits 1 when a file changed while it was read.
    # Tolerate 1 only (verify hashes the finished tar); anything else fails.
    tar_rc=0
    find market_data -type f -newerct "@$SINCE" -printf '%P\0' | tar --null -C market_data -T - -cf "$OUT/market_data.tar" || tar_rc=$?
    if [ "$tar_rc" -le 1 ]; then
      [ "$tar_rc" -eq 0 ] || echo "pull_backups: tar exit 1 tolerated (a market_data file changed while read)" >&2
    else
      echo "pull_backups: tar failed with status $tar_rc" >&2
      exit "$tar_rc"
    fi
    find market_data -type f -printf '%s\t%P\n' > "$WORK/market_files.tsv"
    python3 scripts/ops/backup_manifest.py count-dump "$OUT/db.sql.gz" > "$WORK/rows.json"
    PGV="$(docker compose exec -T db psql -U swingbot -d swingbot -At -c 'SHOW server_version' </dev/null | tr -d '\r')"
    python3 scripts/ops/backup_manifest.py build "$OUT" --git-sha "$GIT_SHA" \
      --deploy-json "$WORK/deploy.json" --row-counts "$WORK/rows.json" --pg-version "$PGV" \
      --market-files "$WORK/market_files.tsv" --vm-epoch "$(date +%s)" >&2
    ;;
  stream)
    [ -n "$ARG" ] || exit 2
    tar czf - -C backups/outbox "$ARG" | base64 -w0
    ;;
  clean)
    [ -n "$ARG" ] || exit 2
    rm -rf "backups/outbox/$ARG"
    ;;
  stream-stable)
    [ -n "$ARG" ] || exit 2
    tar czf - -C "backups/stable/$ARG" . | base64 -w0
    ;;
  *)
    echo "pull_backups: unknown remote mode '$MODE'" >&2
    exit 2
    ;;
esac
REMOTE_EOF

# remote <mode> [arg] [since]: run one mode on the VM. The script goes over
# stdin (an inline command through the wrapper would expand $(...) in WSL first).
remote() {
  printf '%s\n' "$REMOTE" | bash "$SSH_HETZNER" "bash -s -- $*"
}

iso_now() { date -u +%Y-%m-%dT%H:%M:%SZ; }

OUTBOX_DIRTY=0
PULL_STARTED=0
PULL_OK=0

# Record the local pull folder as failed: LAST_PULL first, then the rename
# (copy fallback for a Windows indexer lock). LAST_GOOD_PULL is never touched.
# $1 is the reason; the FAIL line goes to stderr so every abort path ends on one.
mark_pull_failed() {
  local d="$B/pulls/$STAMP"
  echo "$(iso_now) FAIL pulls/$STAMP.FAILED" > "$B/LAST_PULL"
  echo "pull_backups: FAIL ${1:-unknown} pulls/$STAMP.FAILED" >&2
  if mv "$d" "$d.FAILED" 2>/dev/null; then
    return 0
  fi
  if [ -e "$d.FAILED" ]; then
    echo "pull_backups: $d.FAILED already exists, not copying over it; inspect $d by hand" >&2
    return 1
  fi
  mkdir -p "$d.FAILED" && cp -r "$d/." "$d.FAILED/" && rm -rf "$d"
}

# Runs on every exit: a failed stream must never leave a copy of .env in the
# VM's outbox, and an unfinished local pull must never look like a good one.
# Only a normal pull that actually started may mark its own folder failed: a
# --stable run or a refused rerun never touches an earlier pull of the same minute.
# Re-raises the original status.
cleanup_outbox() {
  rc=$?
  if [ "$OUTBOX_DIRTY" = 1 ]; then
    remote clean "$STAMP" >/dev/null 2>&1 || echo "pull_backups: WARNING outbox/$STAMP may remain on the VM" >&2
    OUTBOX_DIRTY=0
  fi
  if [ "$PULL_STARTED" = 1 ] && [ "$PULL_OK" != 1 ] && [ -d "$B/pulls/$STAMP" ]; then
    mark_pull_failed "status $rc" || echo "pull_backups: WARNING could not mark $B/pulls/$STAMP failed" >&2
  fi
  exit "$rc"
}
trap cleanup_outbox EXIT

since_epoch() {
  local last=0
  if [ -f "$B/LAST_GOOD_PULL" ]; then
    last="$(awk '{print $3}' "$B/LAST_GOOD_PULL")"
  fi
  case "$last" in ''|*[!0-9]*) last=0 ;; esac
  if [ "$last" -gt 3600 ]; then echo $((last - 3600)); else echo 0; fi
}

# Report (never delete or fetch): local files the VM no longer has, VM files
# absent locally and VM files whose size differs from the local copy.
report_market() {
  python scripts/ops/backup_manifest.py report-market "$1/manifest.json" "$B/market_data"
}

pull_stable() {
  local name="$1"
  if ! [[ "$name" =~ ^stable-[0-9]{4}-[0-9]{2}-[0-9]{2}(-[0-9]+)?$ ]]; then
    echo "pull_backups: bad stable name '$name'" >&2
    exit 2
  fi
  local dest="$B/stable/$name"
  if [ -e "$dest" ] || [ -e "$dest.partial" ]; then
    echo "pull_backups: $dest (or its .partial) already exists, refusing to overwrite; inspect it, then delete the .partial by hand" >&2
    exit 2
  fi
  mkdir -p "$dest.partial"
  if ! remote stream-stable "$name" | base64 -d | tar xzf - -C "$dest.partial"; then
    echo "pull_backups: stream failed, left $dest.partial; inspect it, then delete the .partial by hand" >&2
    exit 1
  fi
  if ! python scripts/ops/backup_manifest.py verify "$dest.partial"; then
    echo "pull_backups: verify failed, left $dest.partial for inspection" >&2
    exit 1
  fi
  if ! mv "$dest.partial" "$dest" 2>/dev/null; then
    # A Windows indexer/AV lock can block the rename: copy, then verify the copy.
    # The .partial is left in place (nothing is ever removed under backups/stable).
    if ! { mkdir -p "$dest" && cp -r "$dest.partial/." "$dest/"; }; then
      echo "pull_backups: could not move or copy $dest.partial; inspect $dest and the .partial, delete the .partial by hand" >&2
      exit 1
    fi
    if ! python scripts/ops/backup_manifest.py verify "$dest"; then
      echo "pull_backups: the copy at $dest failed verify; inspect it, delete the .partial by hand" >&2
      exit 1
    fi
    echo "pull_backups: rename blocked, copied instead; $dest.partial left in place, delete the .partial by hand"
  fi
  echo "pull_backups: stable point stored at $dest"
}

pull_normal() {
  local since pull_dir vm_epoch added missing_out missing_count bytes
  since="$(since_epoch)"
  pull_dir="$B/pulls/$STAMP"
  if [ -e "$pull_dir" ] || [ -e "$pull_dir.FAILED" ]; then
    echo "pull_backups: $pull_dir (or its .FAILED) already exists for this minute, refusing; wait a minute and rerun" >&2
    exit 2
  fi
  mkdir -p "$B/pulls" "$B/market_data"
  PULL_STARTED=1
  OUTBOX_DIRTY=1
  remote stage "$STAMP" "$since"
  remote stream "$STAMP" | base64 -d | tar xzf - -C "$B/pulls/"
  remote clean "$STAMP" >/dev/null && OUTBOX_DIRTY=0

  if ! python scripts/ops/backup_manifest.py verify "$pull_dir"; then
    mark_pull_failed "verify failed"
    exit 1
  fi

  added="$(tar tf "$pull_dir/market_data.tar" | wc -l | tr -d ' ')"
  tar xf "$pull_dir/market_data.tar" -C "$B/market_data"
  vm_epoch="$(python -c 'import json,sys; print(json.load(open(sys.argv[1]))["vm_epoch"])' "$pull_dir/manifest.json")"
  missing_out="$(report_market "$pull_dir")"
  missing_count="$(printf '%s\n' "$missing_out" | sed -n 's/^MISSING_COUNT=//p')"
  printf '%s\n' "$missing_out" | grep -v '^MISSING_COUNT=' || true
  echo "$(iso_now) PASS pulls/$STAMP" > "$B/LAST_PULL"
  echo "$(iso_now) pulls/$STAMP $vm_epoch" > "$B/LAST_GOOD_PULL"
  PULL_OK=1
  python scripts/ops/backup_manifest.py prune "$B" --keep 10
  bytes="$(du -sb "$pull_dir" | cut -f1)"
  echo "pull_backups: PASS $pull_dir bytes=$bytes files_added=$added missing_on_vm=$missing_count"
}

if [ "${1:-}" = "--stable" ]; then
  [ -n "${2:-}" ] || { echo "usage: pull_backups.sh [--stable <name>]" >&2; exit 2; }
  pull_stable "$2"
else
  pull_normal
fi
