#!/usr/bin/env bash
# One-shot provisioning for an Oracle Cloud "Always Free" Ubuntu VM (also works on any
# fresh Ubuntu 22.04/24.04 box). Installs FlightMatrix as a single systemd service behind
# Caddy (automatic HTTPS + a shared-password gate).
#
# Re-runnable: a second run pulls the latest code, reinstalls deps and restarts.
#
#   # required
#   export FLIGHTMATRIX_BASIC_PASSWORD='pick-a-password'   # the shared login
#
#   # hostname — either bring your own, or let DuckDNS handle it (free)
#   export FLIGHTMATRIX_DOMAIN=flightmatrix.example.org       # an A record must point here
#     -- OR --
#   export FLIGHTMATRIX_DUCKDNS_DOMAIN=flight-matrix       # the label only, no .duckdns.org
#   export FLIGHTMATRIX_DUCKDNS_TOKEN=xxxxxxxx-xxxx-...    # from https://www.duckdns.org
#
#   # optional
#   export FLIGHTMATRIX_BASIC_USER=team                    # default: team
#   export TRAVELPAYOUTS_TOKEN=xxxxxxxx                 # real data needs it
#
#   sudo -E bash deploy/provision.sh
#
# `sudo -E` matters: it keeps the exported variables.
set -euo pipefail

REPO="${FLIGHTMATRIX_REPO:-https://github.com/bard1988/flight_matrix.git}"
APP_DIR="${FLIGHTMATRIX_APP_DIR:-/opt/flight_matrix}"
BASIC_USER="${FLIGHTMATRIX_BASIC_USER:-team}"
BASIC_PASSWORD="${FLIGHTMATRIX_BASIC_PASSWORD:-}"   # empty => no auth gate, site is open
TP_TOKEN="${TRAVELPAYOUTS_TOKEN:-}"
DUCKDNS_LABEL="${FLIGHTMATRIX_DUCKDNS_DOMAIN:-}"
DUCKDNS_TOKEN="${FLIGHTMATRIX_DUCKDNS_TOKEN:-}"

if [ -n "$DUCKDNS_TOKEN" ]; then
    : "${DUCKDNS_LABEL:?export FLIGHTMATRIX_DUCKDNS_DOMAIN=your-subdomain (label only)}"
    DOMAIN="${FLIGHTMATRIX_DOMAIN:-${DUCKDNS_LABEL}.duckdns.org}"
else
    DOMAIN="${FLIGHTMATRIX_DOMAIN:?export FLIGHTMATRIX_DOMAIN=your.hostname  (or FLIGHTMATRIX_DUCKDNS_DOMAIN + FLIGHTMATRIX_DUCKDNS_TOKEN)}"
fi

[ "$(id -u)" -eq 0 ] || { echo "Run with sudo -E." >&2; exit 1; }

echo "==> Swap (1 GB micro shapes OOM during pip install without it)"
if ! swapon --show | grep -q .; then
    fallocate -l 2G /swapfile 2>/dev/null || dd if=/dev/zero of=/swapfile bs=1M count=2048
    chmod 600 /swapfile
    mkswap /swapfile >/dev/null
    swapon /swapfile
    grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

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

if [ -n "$DUCKDNS_TOKEN" ]; then
    echo "==> DuckDNS updater for ${DOMAIN}"
    ( umask 077
      cat > /usr/local/bin/duckdns-update <<EOF
#!/bin/sh
# blank ip= => DuckDNS uses the request's source address (this VM's public IP)
exec curl -fsS -o /var/log/duckdns.log \\
  "https://www.duckdns.org/update?domains=${DUCKDNS_LABEL}&token=${DUCKDNS_TOKEN}&ip="
EOF
    )
    chmod 700 /usr/local/bin/duckdns-update
    /usr/local/bin/duckdns-update || echo "  (first DuckDNS update failed — check the token)"
    cat > /etc/systemd/system/duckdns.service <<'EOF'
[Unit]
Description=DuckDNS IP update
After=network-online.target
Wants=network-online.target
[Service]
Type=oneshot
ExecStart=/usr/local/bin/duckdns-update
EOF
    cat > /etc/systemd/system/duckdns.timer <<'EOF'
[Unit]
Description=Refresh DuckDNS record every 5 minutes
[Timer]
OnBootSec=1min
OnUnitActiveSec=5min
[Install]
WantedBy=timers.target
EOF
    systemctl daemon-reload
    systemctl enable --now duckdns.timer
fi

echo "==> App user and code"
id flightmatrix >/dev/null 2>&1 \
    || useradd --system --home-dir "$APP_DIR" --shell /usr/sbin/nologin flightmatrix
if [ -d "$APP_DIR/.git" ]; then
    git config --global --add safe.directory "$APP_DIR"
    git -C "$APP_DIR" pull --ff-only
else
    git clone --depth 1 "$REPO" "$APP_DIR"
fi
mkdir -p "$APP_DIR/data"
chown -R flightmatrix:flightmatrix "$APP_DIR"

echo "==> Python environment"
sudo -u flightmatrix python3 -m venv "$APP_DIR/venv"
sudo -u flightmatrix "$APP_DIR/venv/bin/pip" install -q --upgrade pip
sudo -u flightmatrix "$APP_DIR/venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"

echo "==> .env"
if [ ! -f "$APP_DIR/.env" ]; then
    install -o flightmatrix -g flightmatrix -m 600 "$APP_DIR/.env.example" "$APP_DIR/.env"
fi
set_env() {  # set_env KEY VALUE  — replace if present, append if not
    local key="$1" val="$2"
    if grep -q "^${key}=" "$APP_DIR/.env"; then
        sed -i "s|^${key}=.*|${key}=${val}|" "$APP_DIR/.env"
    else
        printf '%s=%s\n' "$key" "$val" >> "$APP_DIR/.env"
    fi
}
[ -n "$TP_TOKEN" ] && set_env TRAVELPAYOUTS_TOKEN "$TP_TOKEN"
# 1 GB micro: keep concurrency low so a fill does not thrash swap.
grep -q '^FM_FILL_WORKERS=' "$APP_DIR/.env" || set_env FM_FILL_WORKERS 2
grep -q '^FM_KIWI_WORKERS=' "$APP_DIR/.env" || set_env FM_KIWI_WORKERS 1
chown flightmatrix:flightmatrix "$APP_DIR/.env"

echo "==> systemd service"
install -m 644 "$APP_DIR/deploy/flightmatrix.service" /etc/systemd/system/flightmatrix.service
systemctl daemon-reload
systemctl enable --now flightmatrix
systemctl restart flightmatrix

echo "==> Caddy (automatic HTTPS)"
mkdir -p /etc/caddy
if [ -n "$BASIC_PASSWORD" ]; then
    HASH="$(caddy hash-password --plaintext "$BASIC_PASSWORD")"
    AUTH_BLOCK="$(printf '\tbasicauth {\n\t\t%s %s\n\t}' "$BASIC_USER" "$HASH")"
    AUTH_NOTE="  Login: ${BASIC_USER} / (the password you set)"
else
    AUTH_BLOCK=""
    AUTH_NOTE="  Auth:  none — anyone with the URL can use it"
fi
cat > /etc/caddy/Caddyfile <<EOF
${DOMAIN} {
	encode zstd gzip
${AUTH_BLOCK}
	reverse_proxy 127.0.0.1:8712 {
		# Server-Sent Events: stream board/fill events through without buffering.
		flush_interval -1
	}
}
EOF
# Drop the env-file drop-in from earlier script versions, if present.
rm -f /etc/systemd/system/caddy.service.d/flightmatrix.conf /etc/caddy/flightmatrix.env
systemctl daemon-reload
systemctl restart caddy

cat <<EOF

Done.

  URL:   https://${DOMAIN}
${AUTH_NOTE}

  systemctl status flightmatrix caddy
  journalctl -u flightmatrix -f

If the page does not load:
  - VCN Security List / NSG must allow ingress TCP 80 and 443 from 0.0.0.0/0
    (Oracle console — this script cannot do it).
  - DNS: ${DOMAIN} must resolve to this instance's public IP before Caddy can
    get a certificate.  dig +short ${DOMAIN}
EOF
