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
  1. sanity-check job: installs requirements.txt, imports every module
     -- fails the whole run here if something's broken, before touching
     the server at all
  2. deploy job: SSHs into your Hetzner server as the `deploy` user and
     runs /opt/swing-bot/deploy/deploy.sh
        │
        ▼
deploy/deploy.sh (on the server)
  git fetch + reset --hard origin/main
  docker compose up -d --build
  docker image prune -f
```

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

```bash
cd /opt/swing-bot
sudo -u deploy docker compose up -d --build
sudo -u deploy docker compose logs -f bot
```

Confirm the bot logs in and `!ping` responds in Discord, then Ctrl-C out
of the log tail (the bot keeps running in the background).

## 4. Wire up GitHub Actions

In your GitHub repo: **Settings → Secrets and variables → Actions → New
repository secret**. Add:

| Secret | Value |
|---|---|
| `HETZNER_HOST` | `167.233.26.185` |
| `HETZNER_USER` | `deploy` (or whatever you passed as the second argument to the bootstrap script) |
| `HETZNER_SSH_KEY` | The **private** key the bootstrap script printed — paste the entire block |
| `HETZNER_SSH_PORT` | Optional, only needed if you changed SSH off port 22 |

That's it — `.github/workflows/deploy.yml` is already in the repo. Push
to `main` (or go to **Actions → Deploy to Hetzner → Run workflow** to
trigger it manually) and watch it deploy.

## Rolling back

Deploys are just `git reset --hard origin/main` on the server, so
rolling back is reverting on GitHub and letting the pipeline redeploy:

```bash
git revert <bad-commit-sha>
git push origin main
```

...which triggers the same pipeline against the reverted code. For an
immediate rollback without waiting on CI, SSH in and do it directly:

```bash
ssh deploy@167.233.26.185
cd /opt/swing-bot
git fetch origin
git reset --hard <good-commit-sha>
docker compose up -d --build
```

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
  token, bad channel ID) rather than a deploy problem, since the same
  `docker compose up -d --build` step that CI ran is what you'd run by
  hand.
