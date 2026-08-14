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

# This script updates ITSELF, and then has to hand over to the new version.
#
# `git reset --hard` below rewrites this very file while bash is executing it,
# and bash reads a script lazily, by byte offset. So after the reset it
# continues at whatever offset it had reached -- now pointing into different
# content. Best case it skips the steps that were added (observed: the
# 2026-08-13 Release A deploy silently did not run the verification step this
# file had just gained). Worst case the offset lands mid-line and it executes
# a fragment.
#
# So the update is a separate phase that re-execs. Phase 1 updates the code
# and hands off; phase 2 -- a fresh bash reading the NEW file from the top --
# does the actual work. The flag is what stops it looping.
if [ "${1:-}" != "--updated" ]; then
  echo "==> Fetching latest code (main)"
  git fetch origin main
  git reset --hard origin/main
  echo "==> Re-running the updated deploy script"
  exec bash "$0" --updated
fi

echo "==> Building and starting services"
# --wait blocks until all containers with a healthcheck report healthy
# (or exits non-zero if any container fails to become healthy within its
# start_period + retries window). This means the SSH step in the CI
# pipeline fails loudly instead of silently returning while a container
# is still crashing in a restart loop.
#
# --renew-anon-volumes is what makes `--build` mean anything for the SPA.
#
# Both services mount an ANONYMOUS volume at
# /app/swingbot/admin/static/app, to stop the `.:/app` bind mount from
# hiding the bundle the image built (see docker-compose.yml). An anonymous
# volume is initialised from the image only when it is first CREATED, and
# Compose deliberately carries existing anonymous volumes over to the new
# container on every recreate -- that is what the flag exists to opt out
# of. So without it: the image rebuilds with a fresh bundle, the container
# is recreated, and it re-mounts the volume created by the FIRST deploy,
# pinning the SPA to whatever it was that day. Forever.
#
# That is not theoretical -- it is what shipped. The Python side kept
# updating (it comes from the bind mount, which `git reset --hard` above
# refreshes), so the API was current while the UI was months stale: the
# admin still showed the pre-SR4 "Cockpit" navigation against an API that
# had long since renamed it to Dashboard.
#
# Safe by construction: this recreates ANONYMOUS volumes only. data/,
# logs/ and .env live on the host through the `.:/app` bind mount and are
# untouched, and there are no named volumes in this project.
docker compose up -d --build --renew-anon-volumes --wait

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
# So: fetch the real index.html and follow every asset URL it declares, from
# inside the admin container, against its own loopback. No new secrets, and it
# behaves identically for a manual deploy.
echo "==> Verifying the admin UI actually serves a working SPA"
# --from-config supplies the port, the credentials and the expected UI by
# reading the app's own config in the app's own container, so it cannot
# disagree with the server about any of them.
#
# The rejected alternative was sourcing .env here and passing the values in.
# `.` runs the file through the shell, so a password containing `$`, a
# backtick or `!` is expanded on the way through, and a .env written on
# Windows leaves a trailing CR on every value. Both give a 401 for a password
# that is perfectly correct in the file, and both did exactly that on a real
# deploy before this used --from-config.
if docker compose exec -T admin python scripts/smoke_spa.py --from-config; then
  echo "==> Admin UI verified."
else
  echo "" >&2
  echo "DEPLOY VERIFICATION FAILED -- the containers are up but the admin UI" >&2
  echo "is not serving a usable page. Investigate:" >&2
  echo "  docker compose logs --tail=100 admin" >&2
  exit 1
fi

# The smoke test proves the served bundle WORKS. It cannot prove it is the
# bundle just built -- a months-old SPA loads perfectly and passes every
# assertion in it. That is exactly how the stale-anonymous-volume bug above
# survived deploy after deploy: every check was green and the UI was frozen.
#
# So compare what the image contains against what the container serves. Same
# path, two sources: the freshly built image, and the running container with
# its volumes mounted over the top. A mismatch means something between the
# build and the mount is shadowing the bundle.
echo "==> Verifying the served bundle is the one just built"
IMAGE_SUM=$(docker run --rm --entrypoint sha256sum swing-bot:latest \
  /app/swingbot/admin/static/app/index.html | awk '{print $1}')
SERVED_SUM=$(docker compose exec -T admin sha256sum \
  /app/swingbot/admin/static/app/index.html | awk '{print $1}')

if [ "$IMAGE_SUM" = "$SERVED_SUM" ]; then
  echo "==> Bundle matches the image (${IMAGE_SUM:0:12})."
else
  echo "" >&2
  echo "DEPLOY VERIFICATION FAILED -- the admin container is serving a bundle" >&2
  echo "that is NOT the one this build produced." >&2
  echo "  image:  $IMAGE_SUM" >&2
  echo "  served: $SERVED_SUM" >&2
  echo "" >&2
  echo "Almost certainly a stale anonymous volume shadowing the image's copy." >&2
  echo "Clear it and redeploy:" >&2
  echo "  docker compose down && docker compose up -d --build --renew-anon-volumes --wait" >&2
  exit 1
fi

echo "==> Done. Tail logs with: docker compose logs -f bot"
