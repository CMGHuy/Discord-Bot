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
# --wait blocks until all containers with a healthcheck report healthy
# (or exits non-zero if any container fails to become healthy within its
# start_period + retries window). This means the SSH step in the CI
# pipeline fails loudly instead of silently returning while a container
# is still crashing in a restart loop.
docker compose up -d --build --wait

echo "==> Pruning old, now-unused images (keeps disk usage in check on small instances)"
docker image prune -f

echo "==> Health status after deploy"
docker compose ps

# --wait above proves the containers are UP. It does not prove the admin UI
# serves a working page: the compose healthcheck accepts 200/401/302 on `/`,
# and an unauthenticated request gives 302 whether the SPA is fine or is a
# black screen with every asset 404ing. That exact failure is what NG54's
# acceptance walk found, and neither test suite could see it -- static/app/
# is gitignored and built only inside the image, so the artifact that deploys
# has never been exercised until this moment.
#
# So: fetch the real index.html and follow every asset URL it declares.
# Inside the admin container, against its own localhost, using the
# credentials already in .env -- no new secrets, and it works identically
# for a manual deploy.
#
# 127.0.0.1, NOT localhost: inside the container `localhost` can resolve to
# ::1 first while Flask binds IPv4. Observed failing on one container and
# succeeding on another from the SAME image, which is the worst version of
# this bug -- an intermittently failing deploy check is one that gets ignored.
echo "==> Verifying the admin UI actually serves a working SPA"
# shellcheck disable=SC1091
set -a; . ./.env; set +a
if docker compose exec -T admin python scripts/smoke_spa.py \
      --url "http://127.0.0.1:${ADMIN_PORT:-1234}" \
      --user "${ADMIN_USERNAME:-admin}" \
      --password "${ADMIN_PASSWORD:-admin}" \
      --expect "${ADMIN_UI:-spa}"; then
  echo "==> Admin UI verified."
else
  echo "" >&2
  echo "DEPLOY VERIFICATION FAILED -- the containers are up but the admin UI" >&2
  echo "is not serving a usable page. Roll back with ADMIN_UI=jinja and a" >&2
  echo "restart (that is what the flag is for), then investigate:" >&2
  echo "  docker compose logs --tail=100 admin" >&2
  exit 1
fi

echo "==> Done. Tail logs with: docker compose logs -f bot"
