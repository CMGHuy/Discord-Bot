# Deploying to Hetzner

**Server:** `167.233.26.185` (Docker already installed)

A push-to-deploy pipeline: push to `main` on GitHub, GitHub Actions SSHs
into your Hetzner server and runs `deploy/deploy.sh`, which pulls the
latest code and restarts both Docker services (`bot` and `admin`). No
manual server work after the one-time setup below.

## How it works, in short

```
git push origin main
        │
        ▼
GitHub Actions (.github/workflows/deploy.yml)
  1. test          -- the Python suite
  2. frontend      -- ng test + a real production build of the SPA
  2c. compose-lint -- docker-compose.yml still parses, default profile AND
                      the `tunnel` profile (catches a broken cloudflared
                      service before it ever reaches the server)
  3. container-healthcheck
        builds the image ONCE, starts it, runs the auth/route/SPA smoke
        tests against that exact image, and only then pushes it to GHCR as
        ghcr.io/<owner>/<repo>:sha-<12> and :latest
  4. cleanup   -- starts immediately alongside 1-3 (needs nothing they
                  build) and prunes old sha-* images already on the
                  Hetzner box, so disk is freed BEFORE deploy asks it
                  to pull a new one
  5. deploy    -- waits on container-healthcheck, cleanup AND compose-lint,
                  then SSHes in as `deploy` and runs deploy.sh with
                  SWING_BOT_IMAGE pinned to the sha- tag just published
        │
        ▼
deploy/deploy.sh (on the server)
  git fetch + reset --hard origin/main   # compose file, scripts, .env only
  docker pull $SWING_BOT_IMAGE
  docker compose pull cloudflared        # best-effort, keeps the tunnel patched
  docker compose up -d --no-build --wait
  verify: SPA loads, and both containers run the pulled image digest
```

**The server does not build.** The image is built once in CI, proven there,
and pulled here — so the artifact that was tested is the artifact that runs.
The git checkout on the server still exists, but only for the things that
live *outside* the image: `docker-compose.yml`, `deploy/`, and `.env`.

**Only state is mounted from the host** — `data/`, `logs/`, `exports/`,
`market_data/` and `.env`. The application code and the SPA bundle come from
the image and nothing on the host may shadow them. Both containers mount the
same `data/`, which is how the admin UI reads the very `trades.json` the bot
is writing.

The bot needs **no inbound networking at all** to run — Discord bots
connect *outbound* to Discord's Gateway, so the whole pipeline above
never needs to open a port for the bot itself. See "Networking" in
[DOCKER.md](DOCKER.md) for the full explanation, including how to reach
the admin UI safely without exposing it to the internet.

## 1. Server info

Your server is already provisioned at **`167.233.26.185`** with Docker installed.
Skip straight to step 2.

<details>
<summary>Creating a new Hetzner server (reference for next time)</summary>

1. [Hetzner Cloud Console](https://console.hetzner.cloud) → **New Project** → **Add Server**.
2. **Image**: Ubuntu 24.04 (or 22.04 — the bootstrap script supports both).
3. **Type**: CX22 (2 vCPU / 4 GB RAM) is fine; CX32 gives more headroom for chart rendering.
4. **SSH key**: add your public key at creation time.
5. Note the IP address, then run the bootstrap script in step 2.

</details>

## 2. Bootstrap the server (one time)

SSH in as root and run the bootstrap script, pointing it at your repo:

```bash
ssh root@167.233.26.185

curl -fsSL https://raw.githubusercontent.com/<you>/<repo>/main/deploy/hetzner-setup.sh -o hetzner-setup.sh
chmod +x hetzner-setup.sh
./hetzner-setup.sh https://github.com/<you>/<repo>.git
```

(If your repo is **private**, either use a URL with a
[personal access token](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)
embedded — `https://<token>@github.com/<you>/<repo>.git` — or add a
[deploy key](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/managing-deploy-keys#deploy-keys)
to the repo and use the SSH clone URL instead. Either way, everything
after cloning works identically.)

This script (see [deploy/hetzner-setup.sh](deploy/hetzner-setup.sh) for
the full commented source) does five things:

1. Installs Docker Engine + the Compose plugin.
2. Creates a dedicated, non-root **`deploy`** user in the `docker` group, with its own SSH keypair.
3. Clones your repo to `/opt/swing-bot`.
4. Copies `.env.example` to `.env` (you still need to fill in real values — see next step).
5. Enables `ufw` and allows only SSH inbound — the bot needs nothing else.

At the end it prints a private key. **Copy the whole block** (including
the `BEGIN`/`END` lines) — you'll paste it into a GitHub secret in step 4.

## 3. Configure `.env` and start it once manually

```bash
sudo -u deploy nano /opt/swing-bot/.env
```

Fill in at minimum: `DISCORD_TOKEN`, `DISCORD_CHANNEL_ID`,
`CLOSED_TRADES_CHANNEL_ID`, and set `ADMIN_USERNAME`/`ADMIN_PASSWORD` to
something real (not the defaults). See `.env.example` for the full list
with explanations, or edit later from the admin UI's Settings page
(once it's running).

Also add the published image, so the deploy script knows what to pull
(step 4 covers where the path comes from):

```bash
echo 'SWING_BOT_IMAGE=ghcr.io/<owner>/<repo>:latest' | sudo -u deploy tee -a /opt/swing-bot/.env
```

Then log in to GHCR once (step 4 explains the token) and start it through
the deploy script, which pulls the published image rather than building:

```bash
cd /opt/swing-bot
sudo -u deploy ./deploy/deploy.sh
sudo -u deploy docker compose logs -f bot
```

Confirm the bot logs in and `!ping` responds in Discord, then Ctrl-C out
of the log tail (the bot keeps running in the background).

This needs a published image to exist, so let CI run at least once first.
To bring it up before that — or to debug without the registry — build
locally on the server instead:

```bash
sudo -u deploy docker compose up -d --build
```

## 4. Wire up GitHub Actions

In your GitHub repo: **Settings → Secrets and variables → Actions → New
repository secret**. Add:

| Secret | Value |
|---|---|
| `HETZNER_HOST` | `167.233.26.185` |
| `HETZNER_USER` | `deploy` (or whatever you passed as the second argument to the bootstrap script) |
| `HETZNER_SSH_KEY` | The **private** key the bootstrap script printed — paste the entire block |
| `HETZNER_SSH_PORT` | Optional, only needed if you changed SSH off port 22 |

**No registry secret is needed for pushing.** GHCR authenticates with the
`GITHUB_TOKEN` that Actions mints per run; the workflow just declares
`permissions: packages: write`. Nothing to create, nothing to rotate.

**The server does need one credential to pull**, because the package is
private. Create a classic PAT with only `read:packages`, then, once:

```bash
ssh deploy@167.233.26.185
echo <the-PAT> | docker login ghcr.io -u <your-github-username> --password-stdin
```

It persists in `~/.docker/config.json`, so every later deploy runs
unattended. Also record the image in the server's `.env`, so a manual
`deploy.sh` knows what to pull:

```bash
echo 'SWING_BOT_IMAGE=ghcr.io/<owner>/<repo>:latest' >> /opt/swing-bot/.env
```

The exact path is printed as `Publishing as …` by every CI run — GHCR
lowercases it, so `Discord-Bot` becomes `discord-bot`. A CI deploy overrides
this with the immutable `sha-` tag it just published and does not depend on
the value; it is the fallback for a by-hand deploy.

(If you'd rather make the package public, skip the PAT entirely — `docker
pull` on a public GHCR package needs no login.)

Then push to `main` (or **Actions → Deploy to Hetzner → Run workflow**) and
watch it deploy.

### What CI must *not* have

The application's `.env` — Discord token, admin password, FMP key — stays on
the server and nowhere else. The pipeline never needs it: the test jobs run
against literal stubs (`DISCORD_TOKEN=ci-stub`), and the containers read the
real file from disk at runtime, where the admin UI's settings page also
rewrites it.

Resist base64-ing `.env` into a GitHub Secret. It puts production
credentials in reach of every workflow and every fork's logs, and it
immediately desynchronises from what the admin UI writes on the server, so
the next settings change is silently reverted by the following deploy. If a
single value is genuinely needed at *build* time, add that one value as its
own secret and pass it as a build arg.

## Rolling back

Every build is published under an immutable `sha-<12>` tag, so a rollback is
a pull of an older tag — no rebuild, no revert commit, seconds not minutes:

```bash
ssh deploy@167.233.26.185
cd /opt/swing-bot
SWING_BOT_IMAGE=ghcr.io/<owner>/<repo>:sha-<good-sha> ./deploy/deploy.sh
```

Find the tag under **your profile → Packages → <repo> → versions**, or in
the "Publishing as …" line of the run that shipped it.

That leaves `main` ahead of production, which is deliberate — it's a
stop-the-bleeding move. Follow it with the real fix:

```bash
git revert <bad-commit-sha>
git push origin main
```

...which runs the full pipeline and publishes a new tag as normal.

Note the retention policy (`.github/workflows/registry-retention.yml`)
prunes builds older than 14 days, keeping the 10 most recent plus `latest`.
Rolling back further than that means rebuilding from the tag instead.

Separately, the `cleanup` job in `.github/workflows/deploy.yml` runs
`docker image prune -af` on the Hetzner box itself **before** every deploy
pulls — it starts as soon as the workflow does, alongside `test`/`frontend`/
`container-healthcheck`, and `deploy` waits for it to finish before pulling.
That order is deliberate: it stops old locally-cached `sha-*` images (each
deploy pulls a new one and never removes the last) from filling the disk
right when the next pull needs the space, rather than tidying up after the
fact. This only touches the server's local image cache, not GHCR — a
rollback still works exactly as above, since `docker pull` fetches whatever
tag you ask for regardless of what's cached locally.

## Accessing the admin UI

The admin UI runs on port `1234` (or `$ADMIN_PORT`). The firewall keeps
that port closed to the internet — reach it via SSH tunnel:

```bash
# On your local machine:
ssh -L 1234:localhost:1234 deploy@167.233.26.185 -N
# Then open http://localhost:1234 in your browser
```

To keep it open in the background: add `-f` to the ssh command.

If you want to expose it publicly (only with a real `ADMIN_PASSWORD`):

```bash
ssh deploy@167.233.26.185
sudo ufw allow 1234/tcp   # opens the port
```

Or put nginx in front with TLS — see `deploy/nginx.conf.example` for a
ready-made config.

A third option needing no open port at all: [CLOUDFLARE_TUNNEL.md](CLOUDFLARE_TUNNEL.md)
gives the admin UI a real public hostname via a Cloudflare Tunnel
(`docker-compose.yml`'s `cloudflared` service, off by default behind the
`tunnel` Compose profile).

## Useful one-liners on the server

```bash
ssh deploy@167.233.26.185

# View live bot logs
cd /opt/swing-bot && docker compose logs -f bot

# Restart just the bot (after .env change)
cd /opt/swing-bot && docker compose restart bot

# Run a manual on-demand deploy (same as CI does)
/opt/swing-bot/deploy/deploy.sh

# Check container status
cd /opt/swing-bot && docker compose ps
```

## Updating settings without a code deploy

You don't need to push code or redeploy just to change a setting —
that's exactly what the admin UI's Settings page and `!account`/
`!watchlist` commands are for (see [DOCKER.md](DOCKER.md)); most
settings hot-reload the bot in place via `SIGHUP`, no restart needed.
The CI pipeline above is for *code* changes.

## Not scheduled yet: the option-chain archive

`scripts/data/record_option_snapshots.py` is built and tested but **nothing runs
it** — not compose, not cron, not the bot loop — so `market_data/options/` is
still empty.

It is meant to run once daily near the US close, writing
`market_data/options/YYYY/MM/DD/SYMBOL.parquet` for a capped symbol set. It is
idempotent (re-running a date overwrites), a failed symbol is logged and
skipped, and nothing under `swingbot/` imports it — so it cannot affect the
live path. Roughly 0.5 GB/year at ~10 symbols.

The point of it is that yfinance keeps no option history: **every day it does
not run is a day that can never be recovered.** It gates nothing and improves
nothing today, which is exactly why it is easy to leave unscheduled
indefinitely. Design rationale in
`docs/superpowers/specs/implemented/2026-08-08-v17-market-context-and-level-lifecycle-design.md`
§8.

## Extending this to a staging server

Since the pipeline is just "SSH in, run a script", a second environment
is another server + another bootstrap run + a second set of
`HETZNER_*_STAGING` secrets and a second job (or a separate workflow
file) that deploys a different branch to it. Not set up by default here
to keep a single-server setup simple, but the pieces are all reusable.

## Troubleshooting

- **`sanity-check` fails in CI**: the error is a real Python import
  problem — the server was never touched. Fix it locally, confirm
  `pip install -r requirements.txt` then the same `python -c "..."`
  import block from `.github/workflows/deploy.yml` works, and push again.
- **`deploy` job fails to connect**: double check `HETZNER_HOST` (just
  the IP, no `ssh://` prefix), that the `deploy` user's *public* key is
  in `/home/deploy/.ssh/authorized_keys` on the server (the bootstrap
  script does this automatically), and that you pasted the matching
  *private* key completely into `HETZNER_SSH_KEY`.
- **Deploy succeeds but the bot doesn't come up**: SSH in and check
  `docker compose logs bot` — almost always a `.env` problem (missing
  token, bad channel ID) rather than a deploy problem, since the image
  itself was already started and smoke-tested in CI before it shipped.
- **`docker pull` fails with `denied` / `unauthorized`**: the server's
  GHCR login has expired or was never done. Re-run the `docker login
  ghcr.io` from step 4 with a `read:packages` PAT. Note a PAT belonging to
  someone without access to the package fails the same way.
- **The UI is stale but the API is current**: this was the anonymous-volume
  bug, and it cannot recur — nothing on the host mounts over the image's
  code any more, and `deploy.sh` fails the deploy if either container is
  not running the digest it just pulled. If you see it, check that nobody
  has re-added a `.:/app` mount to `docker-compose.yml`.
