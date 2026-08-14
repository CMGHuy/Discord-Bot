#!/usr/bin/env bash
# Pulls the published image and (re)starts both services. Idempotent --
# safe to run repeatedly.
#
# THIS SERVER DOES NOT BUILD. CI builds the image, tests it, pushes it to
# GHCR, and this script pulls the exact tag that passed. The git checkout
# here is still updated, but only for the things that live outside the
# image: docker-compose.yml, this script, and .env. The application code
# and the SPA bundle come from the image and nothing on the host may
# shadow them -- see the volumes: comment in docker-compose.yml.
#
# Pulling a private GHCR package needs a one-off login on the server:
#   echo <read-only-PAT> | docker login ghcr.io -u <github-user> --password-stdin
# The credential persists in ~/.docker/config.json, so this runs unattended
# afterwards. SWING_BOT_IMAGE in .env supplies the default image to pull.
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

# The image is built by CI and pulled here -- this server does not build.
#
# A CI deploy exports SWING_BOT_IMAGE with an immutable sha- tag. A human
# running this by hand gets the fallback from .env, which normally ends in
# :latest.
#
# Read out of .env WITHOUT sourcing it. `.` or `source` would run the file
# through the shell, so a password containing `$`, a backtick or `!` gets
# expanded on the way through -- the exact bug that made a correct password
# 401 on a real deploy, which is why the verification below uses
# --from-config rather than shell-parsing .env. One key, no evaluation, and
# tolerant of the trailing CR a .env written on Windows leaves behind.
env_value() {
  sed -n "s/^[[:space:]]*$1[[:space:]]*=//p" .env | tail -1 | tr -d '\r' \
    | sed -e 's/^["'\'']//' -e 's/["'\'']$//' -e 's/[[:space:]]*$//'
}

IMAGE="${SWING_BOT_IMAGE:-$(env_value SWING_BOT_IMAGE)}"
if [ -z "$IMAGE" ]; then
  echo "No image to deploy." >&2
  echo "Add the published image to $(pwd)/.env, e.g." >&2
  echo "  SWING_BOT_IMAGE=ghcr.io/<owner>/<repo>:latest" >&2
  echo "(the exact path is in the 'Publishing as ...' line of any CI run)," >&2
  echo "or export SWING_BOT_IMAGE to deploy one specific tag." >&2
  exit 1
fi
export SWING_BOT_IMAGE="$IMAGE"

# Docker creates a DIRECTORY at any bind-mount source that does not exist,
# which for a file mount produces a container that fails in a confusing way
# (.env becomes an unreadable directory). Both files are mounted; make sure
# both exist first. .env.bak is written by the admin UI's settings page and
# is empty until the first save.
[ -f .env.bak ] || touch .env.bak

# The state directories are bind-mounted, so they must exist on the host.
# The container creates data/ and logs/ itself (config.py:69) but only
# INSIDE the container -- which, under a bind mount, is the host path, so a
# missing one would be created root-owned by Docker anyway. Creating them
# here keeps ownership with the deploy user.
mkdir -p data logs exports market_data

echo "==> Pulling $IMAGE"
docker pull "$IMAGE"

echo "==> Starting services"
# --no-build is the assertion, not an optimisation: if anything ever makes
# this server build its own image again, the artifact that was tested in CI
# is not the artifact running, and the whole registry round-trip was
# pointless. Fail instead.
#
# --wait blocks until every container with a healthcheck reports healthy (or
# exits non-zero if one fails to become healthy within its start_period +
# retries window), so the SSH step in CI fails loudly instead of returning
# while a container is still crash-looping.
docker compose up -d --no-build --wait

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

# The smoke test proves the admin serves a WORKING page. It cannot prove the
# page came from the image we just pulled -- a months-old SPA loads perfectly
# and passes every assertion in it. That is precisely how the stale-bundle
# bug survived deploy after deploy with every check green.
#
# So assert the containers are running the image this deploy pulled, by
# digest. Comparing digests rather than tags is the point: `:latest` can be
# repointed under a running container, and a container keeps whatever it
# started from.
echo "==> Verifying the containers run the image this deploy pulled"
WANT=$(docker image inspect --format '{{.Id}}' "$IMAGE")
MISMATCH=""
for svc in bot admin; do
  GOT=$(docker inspect --format '{{.Image}}' "$(docker compose ps -q "$svc")")
  if [ "$GOT" != "$WANT" ]; then
    echo "  FAIL $svc is running $GOT" >&2
    MISMATCH="$MISMATCH $svc"
  else
    echo "  OK   $svc -> ${GOT:0:19}"
  fi
done

if [ -z "$MISMATCH" ]; then
  echo "==> Both services run the pulled image."
else
  echo "" >&2
  echo "DEPLOY VERIFICATION FAILED --$MISMATCH did not adopt the pulled image." >&2
  echo "  wanted: $WANT ($IMAGE)" >&2
  echo "" >&2
  echo "Usually a container Compose decided not to recreate. Force it:" >&2
  echo "  docker compose up -d --no-build --force-recreate --wait" >&2
  exit 1
fi

echo "==> Done. Tail logs with: docker compose logs -f bot"
