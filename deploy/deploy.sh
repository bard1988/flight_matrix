#!/usr/bin/env bash
# One-shot deploy from a workstation: ship whatever is on origin/main to the live VM.
#
#   bash deploy/deploy.sh
#
# It does NOT push. Push your commit to origin/main first (see DEPLOY.md), then run this.
# Override any of the connection details with env vars if they ever change:
#
#   FM_SSH   ssh target             (default: ubuntu@129.159.140.194)
#   FM_KEY   ssh private key path   (default: ~/.ssh/oracle-skymatrix.key)
#   FM_URL   public URL to health-check (default: https://flightmatrix.duckdns.org)
#
set -euo pipefail

FM_SSH=${FM_SSH:-ubuntu@129.159.140.194}
FM_KEY=${FM_KEY:-$HOME/.ssh/oracle-skymatrix.key}
FM_URL=${FM_URL:-https://flightmatrix.duckdns.org}
APP_DIR=${FM_APP_DIR:-/opt/flight_matrix}

ssh_vm() { ssh -i "$FM_KEY" -o ConnectTimeout=20 "$FM_SSH" "$@"; }

echo ">> target: $FM_SSH   ($FM_URL)"

# Show what is about to go live vs what is live now.
remote_main=$(git ls-remote origin -h refs/heads/main | cut -f1)
echo ">> origin/main:  ${remote_main:0:9}  $(git log -1 --format=%s "$remote_main" 2>/dev/null || echo '(fetch to see subject)')"
live=$(ssh_vm "cd $APP_DIR && git rev-parse HEAD" 2>/dev/null || echo unknown)
echo ">> VM is at:     ${live:0:9}"
[ "$remote_main" = "$live" ] && echo ">> already deployed; redeploy will just restart."

# Run the on-VM step. redeploy.sh is idempotent: pull --ff-only, deps only if
# requirements.txt moved, restart, health-check.
ssh_vm "sudo bash $APP_DIR/deploy/redeploy.sh"

# Public health-check through Caddy.
echo -n ">> $FM_URL/api/health -> "
if curl -fsS --max-time 15 "$FM_URL/api/health"; then
  echo; echo ">> done"
else
  echo; echo "!! public health check failed"; exit 1
fi
