#!/usr/bin/env bash
# One-shot provisioning for a Google Flights relay box (an Oracle "Always Free" Ubuntu VM,
# or any fresh Ubuntu 22.04/24.04 box). Installs just the relay as a systemd service --
# no Caddy, no domain, no auth: it is never meant to be reachable except from the main
# app's own IP, enforced at the VCN security list (the OCI console -- this script cannot
# do it) and, redundantly, at this box's own firewall below.
#
# Re-runnable: a second run pulls the latest code, reinstalls deps and restarts.
#
#   export FM_MAIN_IP=129.159.140.194     # the ONLY address allowed to reach this relay
#   sudo -E bash deploy/provision_relay.sh
#
# `sudo -E` matters: it keeps the exported variable.
set -euo pipefail

REPO="${FLIGHTMATRIX_REPO:-https://github.com/bard1988/flight_matrix.git}"
APP_DIR="${FLIGHTMATRIX_APP_DIR:-/opt/flight_matrix}"
RELAY_PORT="${FM_RELAY_PORT:-8080}"
MAIN_IP="${FM_MAIN_IP:?export FM_MAIN_IP=the.main.app.ip (only address allowed to reach this relay)}"

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
apt-get install -y -qq python3-venv python3-pip git

echo "==> Host firewall (Oracle images block everything but SSH by default)"
if command -v iptables >/dev/null 2>&1; then
    iptables -C INPUT -p tcp -s "$MAIN_IP" --dport "$RELAY_PORT" -j ACCEPT 2>/dev/null \
        || iptables -I INPUT -p tcp -s "$MAIN_IP" --dport "$RELAY_PORT" -j ACCEPT
    command -v netfilter-persistent >/dev/null 2>&1 && netfilter-persistent save || true
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
chown -R flightmatrix:flightmatrix "$APP_DIR"

echo "==> Python environment"
sudo -u flightmatrix python3 -m venv "$APP_DIR/venv"
sudo -u flightmatrix "$APP_DIR/venv/bin/pip" install -q --upgrade pip
sudo -u flightmatrix "$APP_DIR/venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"

echo "==> systemd service"
install -m 644 "$APP_DIR/deploy/relay.service" /etc/systemd/system/flightmatrix-relay.service
systemctl daemon-reload
systemctl enable --now flightmatrix-relay
systemctl restart flightmatrix-relay

cat <<EOF

Done.

  Relay listening on :${RELAY_PORT}, reachable only from ${MAIN_IP} (this box's own
  firewall) -- the VCN security list must ALSO allow it (the OCI console; this script
  cannot do that part).

  systemctl status flightmatrix-relay
  journalctl -u flightmatrix-relay -f

  From the main box, once the security list is in place:
    curl http://<this box's IP>:${RELAY_PORT}/health
EOF
