#!/usr/bin/env bash
# Pull a verified rebuild-from-zero set off the VM into backups/ (v120 section 2).
# Dev machine only (Git Bash). Reaches the VM solely through ssh-hetzner.sh, with
# the remote script piped over stdin.
#   bash scripts/ops/pull_backups.sh                  # normal pull
#   bash scripts/ops/pull_backups.sh --stable <name>  # fetch one pinned stable point
# Nothing here ever deletes under backups/market_data/ or backups/stable/.
set -euo pipefail
cd "$(dirname "$0")/../.."
SSH_HETZNER="${SSH_HETZNER:-E:/Documents/Private/Projects/Discord-Bot/scripts/ops/ssh-hetzner.sh}"
B=backups
STAMP="$(date -u +%Y-%m-%dT%H-%MZ)"

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
    find market_data -type f -newermt "@$SINCE" -printf '%P\0' | tar --null -C market_data -T - -cf "$OUT/market_data.tar" || tar_rc=$?
    if [ "$tar_rc" -le 1 ]; then
      [ "$tar_rc" -eq 0 ] || echo "pull_backups: tar exit 1 tolerated (a market_data file changed while read)" >&2
    else
      echo "pull_backups: tar failed with status $tar_rc" >&2
      exit "$tar_rc"
    fi
    find market_data -type f -printf '%s\t%P\n' > "$WORK/market_files.tsv"
    python3 scripts/ops/backup_manifest.py count-dump "$OUT/db.sql.gz" > "$WORK/rows.json"
    PGV="$(docker compose exec -T db psql -U swingbot -d swingbot -At -c 'SHOW server_version' </dev/null | tr -d '\r')"
    python3 scripts/ops/backup_manifest.py build "$OUT" --git-sha "$(git rev-parse HEAD)" \
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
PULL_OK=0

# Record the local pull folder as failed: LAST_PULL first, then the rename
# (copy fallback for a Windows indexer lock). LAST_GOOD_PULL is never touched.
mark_pull_failed() {
  local d="$B/pulls/$STAMP"
  echo "$(iso_now) FAIL pulls/$STAMP.FAILED" > "$B/LAST_PULL"
  mv "$d" "$d.FAILED" 2>/dev/null || { mkdir -p "$d.FAILED" && cp -r "$d/." "$d.FAILED/" && rm -rf "$d"; }
}

# Runs on every exit: a failed stream must never leave a copy of .env in the
# VM's outbox, and an unfinished local pull must never look like a good one.
# Re-raises the original status.
cleanup_outbox() {
  rc=$?
  if [ "$OUTBOX_DIRTY" = 1 ]; then
    remote clean "$STAMP" >/dev/null 2>&1 || echo "pull_backups: WARNING outbox/$STAMP may remain on the VM" >&2
    OUTBOX_DIRTY=0
  fi
  if [ "$PULL_OK" != 1 ] && [ -d "$B/pulls/$STAMP" ]; then
    mark_pull_failed || echo "pull_backups: WARNING could not mark $B/pulls/$STAMP failed" >&2
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

# List local mirror files the VM no longer has (report only, never delete).
report_missing_on_vm() {
  python - "$1/manifest.json" "$B/market_data" <<'PY'
import json, pathlib, sys
manifest = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
vm = set(manifest.get("market_files") or {})
root = pathlib.Path(sys.argv[2])
missing = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()) if root.is_dir() else []
missing = [m for m in missing if m not in vm]
for m in missing:
    print("missing on VM: " + m)
print("MISSING_COUNT=" + str(len(missing)))
PY
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
  mv "$dest.partial" "$dest"
  echo "pull_backups: stable point stored at $dest"
}

pull_normal() {
  local since pull_dir vm_epoch added missing_out missing_count bytes
  since="$(since_epoch)"
  pull_dir="$B/pulls/$STAMP"
  mkdir -p "$B/pulls" "$B/market_data"
  OUTBOX_DIRTY=1
  remote stage "$STAMP" "$since"
  remote stream "$STAMP" | base64 -d | tar xzf - -C "$B/pulls/"
  remote clean "$STAMP" >/dev/null && OUTBOX_DIRTY=0

  if ! python scripts/ops/backup_manifest.py verify backups/pulls/$STAMP; then
    mark_pull_failed
    echo "pull_backups: verify FAILED, moved to $pull_dir.FAILED" >&2
    exit 1
  fi

  added="$(tar tf "$pull_dir/market_data.tar" | wc -l | tr -d ' ')"
  tar xf backups/pulls/$STAMP/market_data.tar -C "$B/market_data"
  vm_epoch="$(python -c 'import json,sys; print(json.load(open(sys.argv[1]))["vm_epoch"])' "$pull_dir/manifest.json")"
  missing_out="$(report_missing_on_vm "$pull_dir")"
  missing_count="$(printf '%s\n' "$missing_out" | sed -n 's/^MISSING_COUNT=//p')"
  printf '%s\n' "$missing_out" | grep '^missing on VM: ' || true
  echo "$(iso_now) PASS pulls/$STAMP" > "$B/LAST_PULL"
  echo "$(iso_now) pulls/$STAMP $vm_epoch" > backups/LAST_GOOD_PULL
  PULL_OK=1
  python scripts/ops/backup_manifest.py prune backups --keep 10
  bytes="$(du -sb "$pull_dir" | cut -f1)"
  echo "pull_backups: PASS $pull_dir bytes=$bytes files_added=$added missing_on_vm=$missing_count"
}

if [ "${1:-}" = "--stable" ]; then
  [ -n "${2:-}" ] || { echo "usage: pull_backups.sh [--stable <name>]" >&2; exit 2; }
  pull_stable "$2"
else
  pull_normal
fi
