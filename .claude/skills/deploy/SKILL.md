---
name: deploy
description: The Hetzner deploy sequence -- decide config vs. code, push or trigger the build, verify both containers on the VM, and mirror any hand edit back. Invoked explicitly as /deploy, never model-triggered.
disable-model-invocation: true
---

# Deploy

## Step 1 — Read the authority

`docs/deploy/DEPLOY_HETZNER.md`, then `docs/deploy/DOCKER.md` for the
two-containers-off-one-image shape. This skill is the checklist; the
reasoning behind every step below lives there, not here.

## Step 2 — Decide: config or code

A `.env` value hot-reloads into the running bot via `SIGHUP` — no restart,
no redeploy (DOCKER.md, "How hot reload actually works"). Two values don't:
the bot token needs `docker compose restart bot`, and the admin UI's own
username/password/port need `docker compose restart admin` — Flask can't
rebind its own port live. Everything else is a code change and needs Step
3's full build-and-deploy. Restarting for a config change, or redeploying
for one, is how this goes wrong in both directions.

## Step 3 — Build and deploy

Normal path — CI builds the image, Node stage included: `git push origin
main`, or **Actions → Deploy to Hetzner → Run workflow**. CI's `frontend`
job runs `ng test` plus a production build of the Angular SPA before the
image is ever built; `container-healthcheck` builds the image once,
smoke-tests it, publishes it to GHCR; `deploy` SSHes in and runs
`deploy/deploy.sh`.

Manual, on-demand redeploy of whatever is already published (same as CI):

```bash
ssh deploy@167.233.26.185
/opt/swing-bot/deploy/deploy.sh
```

Building locally on the server, with no registry involved (first bring-up,
or debugging) — this runs the Dockerfile's Node stage locally too, since
`--build` runs every stage:

```bash
sudo -u deploy docker compose up -d --build
```

## Step 4 — Verify on the VM, not locally

```bash
ssh deploy@167.233.26.185
cd /opt/swing-bot
docker compose ps
docker compose logs -f bot
```

Confirm both services are up, and the bot log shows it logged in and
scanning, not just started. Then confirm the admin API itself, not just its
container — a 302 on `/` is not proof (DOCKER.md, "Verifying a deploy
actually works"). `deploy.sh` already runs this after every deploy; re-run
it by hand the same way, with `--from-config` rather than shell-sourced
creds:

```bash
docker compose exec -T admin python scripts/dev/smoke_spa.py --from-config
```

## Step 5 — Mirror anything you changed by hand

Invoke `mirror-prod`. A deploy that included a live edit on the VM is not
finished at the deploy.

## The gate

`docker compose ps` shows both containers healthy on the VM, and nothing
was changed there that is not also in `git log`.
