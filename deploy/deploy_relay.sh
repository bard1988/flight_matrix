#!/usr/bin/env bash
# One-shot deploy from a workstation: ship whatever is on origin/main to a relay VM.
#
#   FM_RELAY_SSH=ubuntu@<relay-ip> bash deploy/deploy_relay.sh
#
# It does NOT push. Push your commit to origin/main first, then run this -- same
# convention as deploy/deploy.sh for the main app.
#
#   FM_RELAY_SSH   ssh target for the relay              (required)
#   FM_KEY         ssh private key path                  (default: ~/.ssh/oracle-skymatrix.key)
#   FM_RELAY_PORT  port the relay listens on              (default: 8080)
#
set -euo pipefail

FM_RELAY_SSH=${FM_RELAY_SSH:?export FM_RELAY_SSH=ubuntu@the.relay.ip}
FM_KEY=${FM_KEY:-$HOME/.ssh/oracle-skymatrix.key}
APP_DIR=${FM_APP_DIR:-/opt/flight_matrix}
RELAY_PORT=${FM_RELAY_PORT:-8080}

ssh_vm() { ssh -i "$FM_KEY" -o ConnectTimeout=20 "$FM_RELAY_SSH" "$@"; }

echo ">> relay target: $FM_RELAY_SSH"

remote_main=$(git ls-remote origin -h refs/heads/main | cut -f1)
echo ">> origin/main:  ${remote_main:0:9}  $(git log -1 --format=%s "$remote_main" 2>/dev/null || echo '(fetch to see subject)')"
live=$(ssh_vm "sudo -u flightmatrix git -C $APP_DIR rev-parse HEAD" 2>/dev/null || echo unknown)
echo ">> relay is at:  ${live:0:9}"
[ "$remote_main" = "$live" ] && echo ">> already deployed; redeploy will just restart."

ssh_vm "sudo bash $APP_DIR/deploy/redeploy_relay.sh"

echo -n ">> internal health (from the relay itself) -> "
ssh_vm "curl -fsS http://127.0.0.1:$RELAY_PORT/health" && echo || { echo; echo "!! failed"; exit 1; }
echo ">> done"
