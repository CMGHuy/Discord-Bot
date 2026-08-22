# Cloudflare Tunnel: exposing the admin UI at a real domain

This is an optional add-on to the [Hetzner deploy](DEPLOY_HETZNER.md) — it
assumes the server is already up and running `bot`/`admin` per that doc.

If you'd rather have a permanent HTTPS URL (e.g. `https://www.bomeo-capital.com`)
than an SSH tunnel or an open firewall port (the two options in
[DEPLOY_HETZNER.md's "Accessing the admin UI"](DEPLOY_HETZNER.md#accessing-the-admin-ui)),
`docker-compose.yml` has a `cloudflared` service ready to go. A Cloudflare
Tunnel makes the connection **outbound** from the server to Cloudflare's edge
— same shape as the bot's own outbound-only connection to Discord — so no
port needs to be opened, and TLS/auth-in-front is Cloudflare's problem, not
nginx's. It's off by default (gated behind the `tunnel` Compose profile) so
it never affects a plain local `docker compose up`.

Prerequisite: the domain (`bomeo-capital.com`) must already be added as a
zone in your Cloudflare account, with its nameservers pointed at Cloudflare.
If that's not done yet, do it first in the Cloudflare dashboard — it can take
a few minutes to hours to propagate.

## 1. Create the tunnel (one-time, in the Cloudflare dashboard)

1. [Cloudflare Zero Trust dashboard](https://one.dash.cloudflare.com/) →
   **Networks → Tunnels → Create a tunnel**.
2. Choose **Cloudflared**, name it (e.g. `swing-bot-admin`), **Save tunnel**.
3. On the next screen (**Install and run a connector**) you only need the
   token — skip the OS-specific install command shown there, since it runs
   as its own container instead (step 2 below). The token is the long string
   after `--token` in the sample command, or copy it directly from the
   **Docker** tab.
4. Click **Next**, then add a **Public Hostname**:
   - Subdomain: `www` (and repeat this whole tunnel step for the bare
     `bomeo-capital.com` apex if you want both to resolve)
   - Domain: `bomeo-capital.com`
   - Type: `HTTP`
   - URL: `admin:1234` — the compose service name, not `localhost`; both
     containers share the same Docker network, and `cloudflared` reaches
     `admin` the same way the healthchecks in `docker-compose.yml` do.
   - Save.

This is a *dashboard-managed* tunnel — the hostname → service routing rule
lives in Cloudflare, not in a `config.yml` in this repo, so changing it later
is just editing the Public Hostname entry, no redeploy needed.

## 2. Configure the server

```bash
ssh deploy@167.233.26.185
cd /opt/swing-bot
echo 'CLOUDFLARE_TUNNEL_TOKEN=<the-token-from-step-1>' | sudo -u deploy tee -a .env
echo 'COMPOSE_PROFILES=tunnel' | sudo -u deploy tee -a .env
sudo -u deploy docker compose up -d --wait
```

`COMPOSE_PROFILES` is one of the special variables Compose reads straight out
of the project's `.env` file (same file `deploy.sh` already relies on for
`SWING_BOT_IMAGE`, see [DEPLOY_HETZNER.md](DEPLOY_HETZNER.md)), so every
future `deploy.sh` run keeps starting `cloudflared` automatically — nothing
to add to the pipeline itself.

## 3. Verify

`docker compose logs -f cloudflared` should show it registering connections;
then browse to `https://www.bomeo-capital.com` and confirm the admin UI's
login prompt appears. The admin UI's own HTTP Basic Auth
(`ADMIN_USERNAME`/`ADMIN_PASSWORD`) is still the only auth in front of it
unless you add a [Cloudflare Access](https://developers.cloudflare.com/cloudflare-one/policies/access/)
policy on the same hostname in the Zero Trust dashboard for a second,
stronger layer — worth doing since this makes the admin UI reachable from
the open internet by hostname, which the SSH-tunnel and closed-firewall
options in [DEPLOY_HETZNER.md](DEPLOY_HETZNER.md#accessing-the-admin-ui)
deliberately avoid.

## Turning it off again

```bash
docker compose stop cloudflared && docker compose rm -f cloudflared
```

Then remove/blank `COMPOSE_PROFILES` in `.env` so the next deploy doesn't
recreate it.
