# Running with Docker

Two containers, one image (see `Dockerfile`):

- **bot** — runs the Discord bot (`python bot.py`)
- **admin** — a small authenticated web UI (`python admin_ui.py`) to clear
  all open paper trades and view/edit `.env`, without needing shell
  access to the container

Both containers bind-mount the whole project directory to `/app`, so the
`swingbot/` source, `data/` (`trades.json`, `state.json`, `account.json`,
`watchlist.json`), `logs/` (`bot.log`), `.env`, and `exports/` are all
shared between them and persisted on your host — nothing extra to
configure there.

**Deploying this to an actual server with push-to-deploy CI/CD?** See
[DEPLOY_HETZNER.md](DEPLOY_HETZNER.md) — a one-time bootstrap script
plus a GitHub Actions pipeline that deploys automatically on every push
to `main`. Everything below still applies; that doc just automates
running these same commands on a remote server instead of by hand.

## Quick start

```bash
cp .env.example .env
# edit .env: DISCORD_TOKEN, DISCORD_CHANNEL_ID, CLOSED_TRADES_CHANNEL_ID,
# and set ADMIN_USERNAME / ADMIN_PASSWORD to something real -- don't
# leave the defaults in place.

docker compose up -d --build
```

- Bot logs: `docker compose logs -f bot`, or the admin UI's **Logs** page
- Admin UI: `http://localhost:1234` (or your server's address/port)

## Admin UI

Protected by HTTP Basic Auth (`ADMIN_USERNAME` / `ADMIN_PASSWORD` from
`.env` — note `.env` is authoritative for these even over shell-exported
values, same as every other setting). Three pages, in the sidebar:

**Dashboard** — open trades at a glance, sorted by confidence,
auto-refreshing every 5 seconds (toggle off if you'd rather it hold
still) so a trade logged by `!check` or the background scan shows up
without a manual browser reload -- the admin process is separate from
the bot process, so it polls rather than being pushed a notification.
Click any row for the full detail: setup, confidence, trade plan, "if
it gets there" branches, a regenerated chart, the original alert's
explanation text, and the confidence score breakdown (which Discord
never showed at all). Trades logged before this feature was added only
show the core plan, not the extra detail. **Clear all open trades**
deletes everything currently `open`; closed win/loss history is left
untouched.

**Settings** — every `.env` variable as its own compact input field,
grouped by section (Discord Connection, Scanning & Session, Trade
Filters & Risk, Data & Display, Account Defaults, Admin UI). Hover the
ⓘ next to a label for what it does. Clicking **Update settings** saves
`.env` (with a `.env.bak` backup written automatically) *and hot-reloads
the bot* — most changes apply within a second or two, no restart needed.
Fields marked **restart** can't apply live (bot token; the admin UI's
own username/password/port) — see below. **Restart bot container** does
a full restart, for those fields or if hot reload isn't picking
something up.

**Logs** — a live-updating tail of the bot's actual log file (same
content as `docker compose logs -f bot`, but browsable without shell
access). Auto-refreshes every 3 seconds; pick how many lines to show,
or turn off auto-refresh to read a specific moment without it jumping
around.

Both the hot-reload and restart buttons need the Docker socket mounted
into the admin container (it is, by default, in `docker-compose.yml`).
Without it, saving settings still works, it just tells you to restart
manually with `docker compose restart bot`.

### How hot reload actually works

Saving settings sends the bot container a `SIGHUP` (via the Docker
socket) rather than restarting it. The bot's signal handler re-reads
`.env` and updates its live configuration in place — the Discord
connection, open trades, and scan state are all undisturbed. Two
exceptions, flagged in the UI:

- **Bot token** — changing it updates the value in memory, but the
  bot's already-open Discord connection was made with the old token and
  won't reconnect with the new one until the process actually restarts.
- **Admin username / password / port** — these configure the *admin*
  process itself, not the bot. Flask can't rebind its own port live, and
  the admin UI only reads its own credentials at its own startup — these
  need the **admin** container restarted (`docker compose restart admin`),
  not the bot.

## Networking: deploying on a different machine

The bot needs **no inbound networking at all**. Discord bots work by the
*bot* opening an outbound WebSocket connection to Discord's Gateway
(`gateway.discord.gg`) and outbound HTTPS calls to Discord's REST API --
Discord never initiates a connection to your server. That means moving
this container to a brand-new VM is just:

1. Copy the project directory (or `git clone` it) onto the new VM.
2. `cp .env.example .env` and fill in the same `DISCORD_TOKEN` /
   channel IDs (or copy your existing `.env` over directly).
3. `docker compose up -d --build`.

No port forwarding, no firewall inbound rules, no domain name, no TLS
certificate needed for the **bot** service -- it just needs outbound
internet access (which every VM has by default) so it can reach Discord
and Yahoo Finance. The bot token is the only thing that identifies it to
Discord; whichever machine holds a valid token and runs the process *is*
the bot, regardless of its IP address, hosting provider, or region.

The **admin** service is the one exception, since it's a normal web
server you connect *to*: it listens on `ADMIN_PORT` (default 1234) and
needs that port reachable from wherever you're browsing from. If you
want to reach it from outside the VM, either open that port in the VM's
firewall/security group (put a real reverse proxy with TLS and auth in
front of it if you do -- see Security notes below) or just tunnel to it
over SSH (`ssh -L 1234:localhost:1234 user@your-vm`) and browse to
`http://localhost:1234` locally without exposing the port at all.

Running both the bot and a second instance of itself (e.g. testing on
your laptop while the real one runs on a VM) with the **same bot token**
will make both instances receive and respond to the same Discord events
-- use a second application/token in the Developer Portal for a test
instance instead.

## Security notes

- This is meant for trusted, private use — behind your own firewall/VPN,
  or just on `localhost`. It's a single username/password, not a real
  auth system.
- Don't expose port `1234` to the open internet without putting a real
  reverse proxy (with TLS and proper auth) in front of it.
- The `/var/run/docker.sock` mount on the `admin` service grants it the
  ability to control containers on the host. Remove it if you're not
  comfortable with that trade-off — the rest of the admin UI still works.

## Common commands

```bash
docker compose up -d --build      # (re)build and start both services
docker compose restart bot        # full restart of the bot (rarely needed -- Update settings hot-reloads most things)
docker compose restart admin      # restart the admin UI itself (needed after changing its own username/password/port)
docker compose logs -f bot        # follow bot logs
docker compose logs -f admin      # follow admin UI logs
docker compose down               # stop everything
```
