# Deploying SkyMatrix on an Oracle Cloud "Always Free" VM

This serves the board to a handful of people over the internet. It is **not** a public
launch — see [Operating notes](#operating-notes) for why.

## Constraints baked into the setup

- **One process only.** Search progress streams from an in-memory registry
  (`backend/app.py` `_streams`) and the Kiwi rate limiter is process-global. Never run
  a second worker, replica, or instance.
- **Persistent disk.** The SQLite cache, airport table, and merged CA file live in
  `data/`. On a VM that is just the boot volume — fine. The app still works if the
  cache is wiped; the next visitor just re-fetches.
- **No built-in auth.** Caddy adds a single shared username/password in front.

---

## 1. Create the VM

Oracle Cloud console → **Compute → Instances → Create instance**:

| Field | Value |
|---|---|
| Image | Canonical Ubuntu 22.04 or 24.04 |
| Shape | `VM.Standard.E2.1.Micro` (AMD, 1 GB) — *Always Free*, always available. `provision.sh` adds 2 GB of swap and pins `FM_FILL_WORKERS=2` / `FM_KIWI_WORKERS=1` so it fits. |
| SSH keys | upload your public key |

Then **reserve the public IP** so DNS doesn't break on a stop/start: after the
instance is up, **Instance → Attached VNICs → the VNIC → IPv4 Addresses → edit the
primary → "Reserve" / "No ephemeral" → assign a Reserved Public IP** (also Always
Free). Note that IP.

> Prefer more headroom and willing to gamble on capacity? `VM.Standard.A1.Flex`
> (ARM, up to 4 OCPU / 24 GB free) is the alternative — but it frequently returns
> "Out of host capacity", needing retries or a different availability domain. The
> DuckDNS updater the script installs also covers an ephemeral IP if you skip the
> reservation step.

## 2. Open the firewall — two layers

**a) Oracle VCN** (console). Networking → your VCN → the public subnet's **Security
List** → add two **Ingress Rules**:

| Source CIDR | IP Protocol | Destination Port |
|---|---|---|
| `0.0.0.0/0` | TCP | `80` |
| `0.0.0.0/0` | TCP | `443` |

**b) The instance's own iptables.** Oracle's Ubuntu images ship a locked-down
firewall. `provision.sh` opens 80/443 and persists it — nothing to do by hand.

## 3. Set up DuckDNS

1. Go to [duckdns.org](https://www.duckdns.org), sign in (GitHub/Google), create a
   subdomain — e.g. `flight-matrix` → `flight-matrix.duckdns.org`.
2. Copy your **token** from the top of the page.
3. Point it at the instance now: open
   `https://www.duckdns.org/update?domains=flight-matrix&token=YOUR_TOKEN&ip=YOUR_INSTANCE_IP`
   in a browser — it should print `OK`. (`provision.sh` then installs a systemd timer
   that keeps it current.)
4. Confirm: `dig +short flight-matrix.duckdns.org` returns the instance IP.

## 4. Provision

SSH in, then:

```bash
sudo apt-get update && sudo apt-get install -y git
git clone https://github.com/bard1988/flight_matrix.git
cd flight_matrix

export SKYMATRIX_DUCKDNS_DOMAIN=flight-matrix              # label only, no .duckdns.org
export SKYMATRIX_DUCKDNS_TOKEN=xxxxxxxx-xxxx-xxxx-...      # from duckdns.org
export TRAVELPAYOUTS_TOKEN=xxxxxxxx                        # free: https://app.travelpayouts.com/profile/api-token

# optional: gate the site behind a shared login (Caddy basic-auth).
# omit both and the site is open to anyone with the URL.
export SKYMATRIX_BASIC_PASSWORD='choose-a-shared-password'
export SKYMATRIX_BASIC_USER=team

sudo -E bash deploy/provision.sh
```

`sudo -E` preserves those variables. The script adds swap, installs Python deps,
registers the `skymatrix` systemd service, installs Caddy + the DuckDNS updater, and
gets a Let's Encrypt certificate.

When it finishes: **`https://flight-matrix.duckdns.org`** (log in if you set a
password).

No token? The board still loads in **demo mode** if you set `FM_DEMO=1` in
`/opt/flight_matrix/.env` — synthetic data, good for showing the UI.

## 5. Day-to-day

```bash
systemctl status skymatrix caddy
journalctl -u skymatrix -f            # app logs (rate-limit waits, errors)

# deploy a new version
sudo -E bash /opt/flight_matrix/deploy/provision.sh   # pulls, reinstalls, restarts
# or just:
sudo -u skymatrix git -C /opt/flight_matrix pull && sudo systemctl restart skymatrix
```

Config knobs (all `FM_*`, documented in `README.md`) go in `/opt/flight_matrix/.env`,
then `sudo systemctl restart skymatrix`. `provision.sh` already sets
`FM_FILL_WORKERS=2` and `FM_KIWI_WORKERS=1` for the 1 GB shape — raise them only if
`free -m` shows plenty of headroom during a fill.

---

## Docker alternative

If you'd rather containerise (same one-process rule applies — do not scale the
`skymatrix` service):

```bash
cp .env.example .env && $EDITOR .env          # set TRAVELPAYOUTS_TOKEN
export SKYMATRIX_DOMAIN=your.hostname
export SKYMATRIX_BASIC_USER=team
export SKYMATRIX_BASIC_HASH="$(docker run --rm caddy caddy hash-password --plaintext 'choose-a-password')"
docker compose up -d --build
```

`compose.yaml` runs the app + Caddy together; `./data` is bind-mounted so the cache
survives `docker compose restart`.

---

## Operating notes

- **Datacenter IP risk.** Kiwi.com and Google Flights block cloud/datacenter IPs
  faster and harder than residential ones. The board may hit `403`s that a home
  connection wouldn't. Mitigations, in order:
  1. The app already waits out Kiwi 403s (up to `FM_KIWI_WAIT_BUDGET`, default 180s)
     before doing anything else.
  2. Set `FM_BOARD_PROVIDER=travelpayouts` to switch the board to the cached API
     source (needs the token; prices become scaled estimates, not real party totals).
  3. If it's unusable from Oracle, run the same setup on a machine at home/office and
     expose it with a [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/)
     instead — no open ports, residential IP.
- **Throughput.** A fresh 20-destination board is ~4–5 minutes of paced provider
  time. Concurrent searches queue. Fine for a few curious colleagues, not a crowd.
- **`fast-flights` version.** `requirements.txt` pins `>=2.2` but the verification
  code targets the 3.x API. If per-cell Google cross-check errors out, bump it:
  `sudo -u skymatrix /opt/flight_matrix/venv/bin/pip install -U fast-flights`.
- **Cost.** Always Free ARM/micro compute + boot volume + the traffic this generates
  stay within the free allowances. No block volume needed.
- **Backups.** The only state worth keeping is `/opt/flight_matrix/data/cache.sqlite`.
  It's a cache — losing it costs re-fetch time, nothing more.
