#!/usr/bin/env bash
# Pull the v162 Alpaca history store off the VM into data/market_data/ (spec
# section 4). Dev machine only (Git Bash). Reaches the VM solely through
# ssh-hetzner.sh, with the remote script piped over stdin.
#   bash scripts/ops/pull_history_store.sh           # pull, verify every hash, swap in
#   bash scripts/ops/pull_history_store.sh --probe   # prove the binary path on one small file
# Writes the MAIN tree's data/market_data/ (never the root market_data/ live
# cache, never a worktree), so a pull made from a worktree session survives
# the worktree. HISTORY_PULL_DEST overrides the destination.
# Do not pull Sunday 06:30-07:30 UTC: the weekly update cron writes
# data/market_data/ on the VM then (hash verification would catch a torn copy,
# but the pull would fail).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
SSH_HETZNER="${SSH_HETZNER:-E:/Documents/Private/Projects/Discord-Bot/scripts/ops/ssh-hetzner.sh}"

# The main worktree's root: the parent of git's common dir, else this checkout.
resolve_main_root() {
  MAIN_ROOT="$(dirname "$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null)")" || MAIN_ROOT=""
  if [ -z "$MAIN_ROOT" ] || [ "$MAIN_ROOT" = "." ] || [ ! -d "$MAIN_ROOT" ]; then
    MAIN_ROOT="$PWD"
  fi
}
resolve_main_root
DEST="${HISTORY_PULL_DEST:-$MAIN_ROOT/data/market_data}"
PARTIAL="$DEST.partial"
TIMEFRAMES="15min hourly daily"

# The VM-side script. Quoted heredoc: nothing expands locally. It only reads.
read -r -d '' REMOTE <<'REMOTE_EOF' || true
set -euo pipefail
cd /opt/swing-bot/data/market_data
MODE="$1"
ARG="${2:-}"
case "$MODE" in
  stream)
    case "$ARG" in
      15min|hourly|daily) ;;
      *) echo "pull_history_store: bad timeframe '$ARG'" >&2; exit 2 ;;
    esac
    tar czf - "$ARG" | base64 -w0
    ;;
  probe-hash)
    sha256sum daily/_manifest.json | cut -d' ' -f1
    ;;
  probe-stream)
    tar czf - daily/_manifest.json | base64 -w0
    ;;
  *)
    echo "pull_history_store: unknown remote mode '$MODE'" >&2
    exit 2
    ;;
esac
REMOTE_EOF

# remote <mode> [arg]: run one mode on the VM (plain words after `bash -s --`).
remote() {
  printf '%s\n' "$REMOTE" | bash "$SSH_HETZNER" "bash -s -- $*"
}

probe() {
  local tmp want got
  tmp="$(mktemp -d)"
  want="$(remote probe-hash | tr -d '\r\n')"
  remote probe-stream | base64 -d | tar xzf - -C "$tmp"
  got="$(sha256sum "$tmp/daily/_manifest.json" | cut -d' ' -f1)"
  rm -rf "$tmp"
  if [ "$want" != "$got" ]; then
    echo "pull_history_store: probe FAIL local $got != VM $want" >&2
    exit 1
  fi
  echo "pull_history_store: probe PASS $got"
}

# verify <root>: 0 when every file matches its manifest SHA-256. Row-count
# gaps are printed in the saved log but never fail the transport.
verify() {
  local out problems
  out="$(python scripts/data/check_history_store.py --root "$1" --verify-hashes || true)"
  printf '%s\n' "$out" > "$1.check.txt"
  printf '%s\n' "$out" | grep -E '^(HASH |check: )' || true
  problems="$(printf '%s\n' "$out" | sed -n 's/^check: .*, \([0-9][0-9]*\) hash problem(s)$/\1/p')"
  [ "$problems" = "0" ]
}

# swap_in: move the verified $PARTIAL into place, keeping the old store as
# $DEST.prev. If the second move fails after $DEST went to $DEST.prev, put the
# old store back; if even that fails, say how to restore by hand.
swap_in() {
  if [ -e "$DEST" ]; then
    rm -rf "$DEST.prev"
    mv "$DEST" "$DEST.prev"
  fi
  if mv "$PARTIAL" "$DEST"; then
    return 0
  fi
  echo "pull_history_store: ERROR could not move $PARTIAL to $DEST" >&2
  if [ -e "$DEST.prev" ]; then
    if mv "$DEST.prev" "$DEST"; then
      echo "pull_history_store: old store restored to $DEST; new pull left in $PARTIAL" >&2
    else
      echo "pull_history_store: restore FAILED; run by hand: mv \"$DEST.prev\" \"$DEST\"" >&2
    fi
  fi
  return 1
}

pull() {
  if [ -e "$PARTIAL" ]; then
    echo "pull_history_store: $PARTIAL exists from an earlier pull; inspect it, then delete it by hand" >&2
    exit 2
  fi
  mkdir -p "$PARTIAL"
  for tf in $TIMEFRAMES; do
    echo "pull_history_store: streaming $tf"
    remote stream "$tf" | base64 -d | tar xzf - -C "$PARTIAL"
  done
  if ! verify "$PARTIAL"; then
    echo "pull_history_store: FAIL hash verify, left $PARTIAL (see $PARTIAL.check.txt)" >&2
    exit 1
  fi
  swap_in
  mv "$PARTIAL.check.txt" "$DEST.check.txt"
  echo "pull_history_store: PASS $DEST bytes=$(du -sb "$DEST" | cut -f1)"
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  if [ "${1:-}" = "--probe" ]; then
    probe
  else
    pull
  fi
fi
