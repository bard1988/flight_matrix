#!/usr/bin/env bash
# One-shot provisioning for an Oracle Cloud "Always Free" Ubuntu VM (also works on any
# fresh Ubuntu 22.04/24.04 box). Installs SkyMatrix as a single systemd service behind
# Caddy (automatic HTTPS + a shared-password gate).
#
# Re-runnable: a second run pulls the latest code, reinstalls deps and restarts.
#
#   export SKYMATRIX_DOMAIN=skymatrix.example.org      # required — an A record must point here
#   export SKYMATRIX_BASIC_PASSWORD='pick-a-password'  # required — the shared login
#   export SKYMATRIX_BASIC_USER=team                   # optional (default: team)
#   export TRAVELPAYOUTS_TOKEN=xxxxxxxx                # optional — real data needs it
#   sudo -E bash deploy/provision.sh
#
# `sudo -E` matters: it keeps the exported variables.
set -euo pipefail

REPO="${SKYMATRIX_REPO:-https://github.com/bard1988/flight_matrix.git}"
APP_DIR="${SKYMATRIX_APP_DIR:-/opt/flight_matrix}"
DOMAIN="${SKYMATRIX_DOMAIN:?export SKYMATRIX_DOMAIN=your.hostname}"
BASIC_USER="${SKYMATRIX_BASIC_USER:-team}"
BASIC_PASSWORD="${SKYMATRIX_BASIC_PASSWORD:?export SKYMATRIX_BASIC_PASSWORD=...}"
TP_TOKEN="${TRAVELPAYOUTS_TOKEN:-}"

[ "$(id -u)" -eq 0 ] || { echo "Run with sudo -E." >&2; exit 1; }

echo "==> Packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3-venv python3-pip git curl gpg debian-keyring \
    debian-archive-keyring apt-transport-https ca-certificates

if ! command -v caddy >/dev/null 2>&1; then
    echo "==> Caddy"
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
        | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
        > /etc/apt/sources.list.d/caddy-stable.list
    apt-get update -qq
    apt-get install -y -qq caddy
fi

echo "==> Host firewall (Oracle images block everything but SSH)"
if command -v iptables >/dev/null 2>&1; then
    iptables -C INPUT -p tcp -m multiport --dports 80,443 -j ACCEPT 2>/dev/null \
        || iptables -I INPUT -p tcp -m multiport --dports 80,443 -j ACCEPT
    command -v netfilter-persistent >/dev/null 2>&1 && netfilter-persistent save || true
fi

echo "==> App user and code"
id skymatrix >/dev/null 2>&1 \
    || useradd --system --home-dir "$APP_DIR" --shell /usr/sbin/nologin skymatrix
if [ -d "$APP_DIR/.git" ]; then
    git config --global --add safe.directory "$APP_DIR"
    git -C "$APP_DIR" pull --ff-only
else
    git clone --depth 1 "$REPO" "$APP_DIR"
fi
mkdir -p "$APP_DIR/data"
chown -R skymatrix:skymatrix "$APP_DIR"

echo "==> Python environment"
sudo -u skymatrix python3 -m venv "$APP_DIR/venv"
sudo -u skymatrix "$APP_DIR/venv/bin/pip" install -q --upgrade pip
sudo -u skymatrix "$APP_DIR/venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"

echo "==> .env"
if [ ! -f "$APP_DIR/.env" ]; then
    install -o skymatrix -g skymatrix -m 600 "$APP_DIR/.env.example" "$APP_DIR/.env"
fi
if [ -n "$TP_TOKEN" ]; then
    sudo -u skymatrix sed -i "s|^TRAVELPAYOUTS_TOKEN=.*|TRAVELPAYOUTS_TOKEN=${TP_TOKEN}|" "$APP_DIR/.env"
fi

echo "==> systemd service"
install -m 644 "$APP_DIR/deploy/skymatrix.service" /etc/systemd/system/skymatrix.service
systemctl daemon-reload
systemctl enable --now skymatrix
systemctl restart skymatrix

echo "==> Caddy (TLS + shared-password gate)"
install -m 644 "$APP_DIR/deploy/Caddyfile" /etc/caddy/Caddyfile
HASH="$(caddy hash-password --plaintext "$BASIC_PASSWORD")"
( umask 077
  cat > /etc/caddy/skymatrix.env <<EOF
SKYMATRIX_DOMAIN=${DOMAIN}
SKYMATRIX_BASIC_USER=${BASIC_USER}
SKYMATRIX_BASIC_HASH=${HASH}
SKYMATRIX_UPSTREAM=127.0.0.1:8712
EOF
)
mkdir -p /etc/systemd/system/caddy.service.d
cat > /etc/systemd/system/caddy.service.d/skymatrix.conf <<'EOF'
[Service]
EnvironmentFile=/etc/caddy/skymatrix.env
EOF
systemctl daemon-reload
systemctl restart caddy

cat <<EOF

Done.

  URL:   https://${DOMAIN}
  Login: ${BASIC_USER} / (the password you set)

  systemctl status skymatrix caddy
  journalctl -u skymatrix -f

If the page does not load:
  - VCN Security List / NSG must allow ingress TCP 80 and 443 from 0.0.0.0/0
    (Oracle console — this script cannot do it).
  - DNS: ${DOMAIN} must resolve to this instance's public IP before Caddy can
    get a certificate.  dig +short ${DOMAIN}
EOF
