#!/usr/bin/env bash
# Pulls the latest code from `main` and (re)builds/(re)starts both
# services. Idempotent -- safe to run repeatedly; `docker compose up -d
# --build` only rebuilds/restarts what actually changed.
#
# Used two ways:
#   - Automatically, by .github/workflows/deploy.yml, over SSH, on every
#     push to main.
#   - Manually, for an on-demand deploy or to re-apply after editing
#     .env by hand instead of through the admin UI:
#       ssh deploy@<server> '/opt/swing-bot/deploy/deploy.sh'
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  echo "No .env found in $(pwd) -- copy .env.example to .env and fill it in before deploying." >&2
  exit 1
fi

echo "==> Fetching latest code (main)"
git fetch origin main
git reset --hard origin/main

echo "==> Building and starting services"
docker compose up -d --build

echo "==> Pruning old, now-unused images (keeps disk usage in check on small instances)"
docker image prune -f

echo "==> Status"
docker compose ps

echo "==> Done. Tail logs with: docker compose logs -f bot"
