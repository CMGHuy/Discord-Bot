#!/usr/bin/env bash
# Pulls the latest code from `main` and (re)builds/(re)starts both services.
#
# Used two ways:
#   - Automatically, by .github/workflows/deploy.yml, over SSH, on every
#     push to main.
#   - Manually, for an on-demand deploy or to re-apply after editing
#     .env by hand instead of through the admin UI:
#       ssh deploy@<server> '/opt/swing-bot/deploy/deploy.sh'
#
# ---------------------------------------------------------------------------
# RECONCILE BEFORE THE BOT COMES BACK UP. This is the whole reason this
# script is more than three lines.
#
# Trades close only on a spot-price poll, so a TP/SL touched while the bot is
# down is invisible to it forever. Worse, on restart it books those plans at
# the CURRENT spot price rather than the one that actually triggered them. On
# 2026-08-04 that turned a real 10W/12L into a flattering 15W/9L across 28
# plans, and nothing errored -- the win rate was simply wrong.
# `scripts/reconcile_open_plans.py` replays the missed bars through
# PlanManager's own state machine and books them correctly, but it is a
# standalone script that nothing calls for you.
#
# This script previously ran `docker compose up -d --build --wait` directly,
# which recreates the bot container on EVERY push to main -- so every deploy
# was one of those unreconciled restarts, silently, including during market
# hours. The order below (stop -> back up -> reconcile -> up) is the one
# documented in CLAUDE.md, and getting it wrong corrupts the trade record
# rather than raising an error.
# ---------------------------------------------------------------------------
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  echo "No .env found in $(pwd) -- copy .env.example to .env and fill it in before deploying." >&2
  exit 1
fi

echo "==> Fetching latest code (main)"
git fetch origin main
git reset --hard origin/main

# The reset above may have just replaced THIS script. Bash reads a script
# incrementally, so the running process would otherwise finish with a mix of
# old and new logic -- and any fix to the deploy procedure would not take
# effect until the deploy AFTER the one that shipped it. Re-exec once so a
# deploy always runs the deploy logic that ships with the code it deploys.
if [ "${SWINGBOT_DEPLOY_REEXEC:-}" != "1" ]; then
  export SWINGBOT_DEPLOY_REEXEC=1
  echo "==> Re-exec'ing the freshly pulled deploy script"
  exec bash "$0" "$@"
fi

echo "==> Building images (nothing is restarted yet)"
docker compose build

# ── Reconcile, with the bot DOWN ───────────────────────────────────────────
# Stopped explicitly rather than letting `up` recreate it: the plan state must
# not move under a running PlanManager while this replays the same bars.
echo "==> Stopping the bot before touching its trade state"
docker compose stop bot

if [ -f data/plans.json ]; then
  ts=$(date +%Y%m%d-%H%M%S)
  echo "==> Backing up trade state (data/*.json.predeploy-$ts)"
  for f in plans trades account journal; do
    if [ -f "data/$f.json" ]; then
      cp -a "data/$f.json" "data/$f.json.predeploy-$ts"
    fi
  done

  echo "==> Reconciling open plans -- DRY RUN (no writes)"
  docker compose run --rm --no-deps -T bot \
      python scripts/reconcile_open_plans.py

  echo "==> Reconciling open plans -- APPLY"
  # On failure this aborts with the bot still DOWN, deliberately. Starting it
  # on an unreconciled book is what corrupts the record, and that corruption
  # cannot be repaired from the logs afterwards; a stopped bot can always be
  # started once a human has looked at it.
  if ! docker compose run --rm --no-deps -T bot \
          python scripts/reconcile_open_plans.py --apply; then
    echo "" >&2
    echo "!! RECONCILE FAILED -- the bot has deliberately been left STOPPED." >&2
    echo "!! Starting it now would book any touched plan at current spot and" >&2
    echo "!! silently corrupt the win rate (see 2026-08-04)." >&2
    echo "!! State backups: data/*.json.predeploy-$ts" >&2
    echo "!! Investigate, then bring it up with: docker compose up -d --wait" >&2
    exit 1
  fi
else
  echo "==> No data/plans.json yet -- first deploy, nothing to reconcile"
fi

echo "==> Starting services"
# --wait blocks until all containers with a healthcheck report healthy (or
# exits non-zero if any fails to become healthy within its start_period +
# retries window), so the CI SSH step fails loudly instead of returning while
# a container is still crashing in a restart loop. No --build here: the images
# were built above, before the bot was stopped.
docker compose up -d --wait

echo "==> Pruning old, now-unused images (keeps disk usage in check on small instances)"
docker image prune -f

echo "==> Health status after deploy"
docker compose ps

echo "==> Done. Tail logs with: docker compose logs -f bot"
