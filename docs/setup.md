# Setup

## 1. Create the Discord bot

1. Go to https://discord.com/developers/applications → **New Application**.
2. Go to **Bot** → **Add Bot**. Copy the **token**.
3. Under **Privileged Gateway Intents**, enable **Message Content Intent**.
4. **OAuth2 → URL Generator**: check `bot`, then `Send Messages`,
   `Embed Links`, `Attach Files`. Open the generated URL to invite the bot.
5. Right-click your alert channel → **Copy Channel ID** (enable Developer
   Mode in Discord settings first). Do the same for a second channel if
   you want closed-trade notifications separated out.

## 2. Configure

```bash
cp .env.example .env
```

Key settings in `.env` (see the file for the full list with comments):
```
DISCORD_TOKEN=<your bot token>
DISCORD_CHANNEL_ID=<main alert channel id>
CLOSED_TRADES_CHANNEL_ID=<closed-trade notifications channel id>
MIN_ALERT_CONFIDENCE_LEVEL=3
MIN_REWARD_PCT=5.0
DEDUP_TOLERANCE_PCT=2.0
DEFAULT_HISTORY_PERIOD=5y
```

## 3. Install & run

```bash
pip install -r requirements.txt
python bot.py
```

## 5. Running it 24/7

Host this somewhere always-on. The included Docker setup ([DOCKER.md](docs/DOCKER.md))
runs the bot plus an authenticated admin web UI as two containers
sharing one project directory — works on any VPS, a Raspberry Pi, or a
cloud VM. For a push-to-deploy pipeline on a Hetzner Cloud server
specifically (GitHub Actions deploys automatically on every push to
`main`), see [DEPLOY_HETZNER.md](docs/DEPLOY_HETZNER.md). Without Docker, a
`systemd` service or `screen`/`tmux` session running `python bot.py`
works fine too.
