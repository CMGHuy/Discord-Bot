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
3. On **Install and run a connector**, you only need the token — skip the
   OS-specific install command shown there, since it runs as its own
   container instead (step 2 below). The token is the long string after
   `--token` in the sample command, or copy it directly from the **Docker**
   tab.
4. Open the tunnel's **Hostname routes** tab (Cloudflare has renamed this
   screen more than once — it's the one that sits alongside "CIDR routes",
   "Published application routes" and "Live logs"; older dashboards call it
   "Public Hostname". Whatever the label, it's the tab that maps a domain to
   a local service). Use its add-route button to create **two** entries, both
   pointing at the same service so the admin UI answers on both:

   | Subdomain   | Domain              | Type   | URL           |
   | ----------- | ------------------- | ------ | ------------- |
   | `www`       | `bomeo-capital.com` | `HTTP` | `admin:1234`  |
   | *(blank)*   | `bomeo-capital.com` | `HTTP` | `admin:1234`  |

   `admin:1234` is the compose service name, not `localhost` — both
   containers share the same Docker network, and `cloudflared` reaches
   `admin` the same way the healthchecks in `docker-compose.yml` do.

   **If saving either route fails with "A DNS record with this name already
   exists":** the domain has a leftover DNS record from before it was on this
   tunnel (this happened for both `www` and the bare apex when this doc was
   written). Go to the regular [Cloudflare dashboard](https://dash.cloudflare.com/)
   → the `bomeo-capital.com` site → **DNS → Records**, delete the conflicting
   row (named `www` or `bomeo-capital.com`/`@`), then retry saving the route
   — it auto-creates the correct CNAME once the old record is out of the way.

This is a *dashboard-managed* tunnel — the hostname → service routing rules
live in Cloudflare, not in a `config.yml` in this repo, so changing either
one later is just editing its route entry, no redeploy needed.

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

`docker compose logs -f cloudflared` should show it registering connections
and an `Updated to new configuration` line listing **both**
`www.bomeo-capital.com` and `bomeo-capital.com` in its ingress rules. Then
browse to both `https://www.bomeo-capital.com` and `https://bomeo-capital.com`
and confirm the admin UI's login prompt appears at each. The admin UI's own
HTTP Basic Auth (`ADMIN_USERNAME`/`ADMIN_PASSWORD`) is still the only auth in
front of it unless you add a [Cloudflare Access](https://developers.cloudflare.com/cloudflare-one/policies/access/)
policy on the same hostnames in the Zero Trust dashboard for a second,
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
