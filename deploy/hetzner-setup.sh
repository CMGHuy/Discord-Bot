#!/usr/bin/env bash
# One-time bootstrap for a fresh Hetzner Cloud server (Ubuntu 22.04/24.04).
# Run this ONCE, as root, right after creating the server.
#
#   ssh root@<server-ip>
#   curl -fsSL https://raw.githubusercontent.com/<you>/<repo>/main/deploy/hetzner-setup.sh -o hetzner-setup.sh
#   chmod +x hetzner-setup.sh
#   ./hetzner-setup.sh <git-repo-url> [deploy-user]
#
# (If the repo is private, either use an HTTPS URL with a personal access
# token embedded, an SSH URL with a deploy key already added to the
# repo's Deploy Keys, or just `scp`/`rsync` the project directory to
# /opt/swing-bot yourself instead of cloning -- everything after that
# step works the same either way.)
#
# What this does:
#   1. Installs Docker Engine + the Compose plugin (official Docker apt repo)
#   2. Creates a dedicated, non-root deploy user (default: deploy) in the
#      docker group, with its own SSH keypair for CI to use
#   3. Clones the repo to /opt/swing-bot
#   4. Copies .env.example to .env (YOU must edit this before starting --
#      this script deliberately does not try to guess your secrets)
#   5. Configures ufw: allows SSH, denies everything else inbound by
#      default -- the bot itself needs ZERO inbound ports (see
#      DEPLOY_HETZNER.md for why, and how to reach the admin UI safely)
set -euo pipefail

REPO_URL="${1:?Usage: ./hetzner-setup.sh <git-repo-url> [deploy-user]}"
DEPLOY_USER="${2:-deploy}"
APP_DIR="/opt/swing-bot"
DEPLOY_HOME="/home/$DEPLOY_USER"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this as root (or with sudo)." >&2
  exit 1
fi

echo "==> Updating apt and installing prerequisites"
apt-get update -y
apt-get install -y ca-certificates curl gnupg git ufw

echo "==> Installing Docker Engine + Compose plugin"
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker

echo "==> Creating deploy user '$DEPLOY_USER'"
if ! id "$DEPLOY_USER" &>/dev/null; then
  adduser --disabled-password --gecos "" "$DEPLOY_USER"
fi
usermod -aG docker "$DEPLOY_USER"

echo "==> Setting up an SSH keypair for CI to use"
sudo -u "$DEPLOY_USER" mkdir -p "$DEPLOY_HOME/.ssh"
if [ ! -f "$DEPLOY_HOME/.ssh/id_ed25519" ]; then
  sudo -u "$DEPLOY_USER" ssh-keygen -t ed25519 -N "" -f "$DEPLOY_HOME/.ssh/id_ed25519" -C "swing-bot-ci"
fi
touch "$DEPLOY_HOME/.ssh/authorized_keys"
if ! grep -qxF "$(cat "$DEPLOY_HOME/.ssh/id_ed25519.pub")" "$DEPLOY_HOME/.ssh/authorized_keys" 2>/dev/null; then
  cat "$DEPLOY_HOME/.ssh/id_ed25519.pub" >> "$DEPLOY_HOME/.ssh/authorized_keys"
fi
chmod 700 "$DEPLOY_HOME/.ssh"
chmod 600 "$DEPLOY_HOME/.ssh/authorized_keys" "$DEPLOY_HOME/.ssh/id_ed25519"
chown -R "$DEPLOY_USER:$DEPLOY_USER" "$DEPLOY_HOME/.ssh"

echo "==> Cloning $REPO_URL into $APP_DIR"
if [ ! -d "$APP_DIR/.git" ]; then
  git clone "$REPO_URL" "$APP_DIR"
else
  echo "    $APP_DIR already exists and looks like a git checkout -- leaving it as-is."
fi
chown -R "$DEPLOY_USER:$DEPLOY_USER" "$APP_DIR"
chmod +x "$APP_DIR"/deploy/*.sh 2>/dev/null || true

if [ ! -f "$APP_DIR/.env" ]; then
  cp "$APP_DIR/.env.example" "$APP_DIR/.env"
  chown "$DEPLOY_USER:$DEPLOY_USER" "$APP_DIR/.env"
  echo "    Created $APP_DIR/.env from .env.example -- YOU must edit it before starting the bot."
fi

echo "==> Configuring firewall (ufw) -- SSH only, everything else denied by default"
ufw allow OpenSSH
ufw --force enable

CI_PRIVATE_KEY="$(cat "$DEPLOY_HOME/.ssh/id_ed25519")"

cat <<EOF

============================================================
Bootstrap complete.

Next steps:
  1. Edit $APP_DIR/.env with your real settings:
       sudo -u $DEPLOY_USER nano $APP_DIR/.env
     (DISCORD_TOKEN, DISCORD_CHANNEL_ID, CLOSED_TRADES_CHANNEL_ID,
     ADMIN_USERNAME, ADMIN_PASSWORD -- don't leave the admin defaults.)

  2. Start it manually once, to confirm it comes up clean:
       cd $APP_DIR && sudo -u $DEPLOY_USER docker compose up -d --build
       sudo -u $DEPLOY_USER docker compose logs -f bot

  3. In your GitHub repo -> Settings -> Secrets and variables -> Actions,
     add these repo secrets so .github/workflows/deploy.yml can deploy
     here automatically on every push to main:
       HETZNER_HOST     = $(curl -s -4 ifconfig.me || echo "<this server's IP>")
       HETZNER_USER     = $DEPLOY_USER
       HETZNER_SSH_KEY  = the PRIVATE key printed below (paste the WHOLE
                           block, including the BEGIN/END lines)

  4. To reach the admin UI (port \${ADMIN_PORT:-1234}) from your own
     machine WITHOUT opening the port publicly, use an SSH tunnel:
       ssh -L 1234:localhost:1234 $DEPLOY_USER@<this-server-ip>
     then browse to http://localhost:1234 on YOUR machine.
     (To open it publicly instead: 'ufw allow 1234/tcp' -- only do this
     with a real ADMIN_PASSWORD set, and ideally a reverse proxy with
     TLS in front of it. See DEPLOY_HETZNER.md.)

---- CI private key for HETZNER_SSH_KEY (keep this secret!) ----
$CI_PRIVATE_KEY
------------------------------------------------------------------
EOF
