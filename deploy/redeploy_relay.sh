#!/usr/bin/env bash
# Pull the latest main and restart the relay. Runs ON THE RELAY VM. Idempotent and safe
# to re-run.
#
#   ssh ubuntu@<relay-vm> 'sudo bash /opt/flight_matrix/deploy/redeploy_relay.sh'
#
set -euo pipefail

APP_DIR=${FM_APP_DIR:-/opt/flight_matrix}
APP_USER=${FM_APP_USER:-flightmatrix}
SERVICE=${FM_RELAY_SERVICE:-flightmatrix-relay}
PORT=${FM_RELAY_PORT:-8080}

echo ">> redeploy relay: $APP_DIR  (user=$APP_USER  service=$SERVICE)"
cd "$APP_DIR"

run_git() { sudo -u "$APP_USER" git -C "$APP_DIR" "$@"; }

before=$(run_git rev-parse --short HEAD)
run_git fetch origin --quiet
run_git pull --ff-only origin main
after=$(run_git rev-parse --short HEAD)

if [ "$before" = "$after" ]; then
  echo ">> already up to date at $after"
else
  echo ">> $before -> $after"
fi

if [ "$before" != "$after" ] && ! run_git diff --quiet "$before" "$after" -- requirements.txt; then
  echo ">> requirements.txt changed -> pip install"
  sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"
fi

# The unit file itself may have changed (this repo owns it) -- reinstall it every time,
# cheap and idempotent.
install -m 644 "$APP_DIR/deploy/relay.service" "/etc/systemd/system/${SERVICE}.service"
systemctl daemon-reload

sudo systemctl restart "$SERVICE"
sleep 2
systemctl is-active --quiet "$SERVICE" && echo ">> $SERVICE active" || {
  echo "!! $SERVICE did not come up:"; journalctl -u "$SERVICE" -n 30 --no-pager; exit 1;
}

if curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null; then
  echo ">> health OK on :$PORT"
else
  echo "!! health check failed on :$PORT"; exit 1
fi

echo ">> deployed $after"
