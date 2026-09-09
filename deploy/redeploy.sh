#!/usr/bin/env bash
# Pull the latest main and restart the service. Runs ON THE VM, as any sudo-capable
# user (it drops to the `skymatrix` user for every git call). Idempotent and safe to
# re-run. Invoked by deploy/deploy.sh over SSH, or by hand:
#
#   ssh ubuntu@<vm> 'sudo bash /opt/flight_matrix/deploy/redeploy.sh'
#
set -euo pipefail

APP_DIR=${FM_APP_DIR:-/opt/flight_matrix}
APP_USER=${FM_APP_USER:-skymatrix}
SERVICE=${FM_SERVICE:-skymatrix}

echo ">> redeploy: $APP_DIR  (user=$APP_USER  service=$SERVICE)"
cd "$APP_DIR"

run_git() { sudo -u "$APP_USER" git -C "$APP_DIR" "$@"; }

before=$(run_git rev-parse --short HEAD)

# The running app rewrites data/kiwi_slugs.json (a tracked file), which blocks a pull.
# Stash just that file if it is dirty, so the pull is always a clean fast-forward.
if ! run_git diff --quiet -- data/kiwi_slugs.json 2>/dev/null; then
  echo ">> stashing runtime-modified data/kiwi_slugs.json"
  run_git stash push -u -m "redeploy-$(date +%s)" -- data/kiwi_slugs.json
fi

run_git fetch origin --quiet
run_git pull --ff-only origin main

after=$(run_git rev-parse --short HEAD)

if [ "$before" = "$after" ]; then
  echo ">> already up to date at $after"
else
  echo ">> $before -> $after"
fi

# Only reinstall deps when requirements.txt actually changed between the two revisions.
if [ "$before" != "$after" ] && ! run_git diff --quiet "$before" "$after" -- requirements.txt; then
  echo ">> requirements.txt changed -> pip install"
  sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"
fi

sudo systemctl restart "$SERVICE"
sleep 3
systemctl is-active --quiet "$SERVICE" && echo ">> $SERVICE active" || {
  echo "!! $SERVICE did not come up:"; journalctl -u "$SERVICE" -n 30 --no-pager; exit 1;
}

# Local health check (the service binds 127.0.0.1). Port comes from the committed unit
# file's ExecStart (--port N), default 8712.
port=$(grep -oE -- '--port[= ][0-9]+' "$APP_DIR/deploy/flightmatrix.service" 2>/dev/null | grep -oE '[0-9]+' | head -1)
port=${port:-8712}
if curl -fsS "http://127.0.0.1:$port/api/health" >/dev/null; then
  echo ">> health OK on :$port"
else
  echo "!! health check failed on :$port"; exit 1
fi

echo ">> deployed $after"
