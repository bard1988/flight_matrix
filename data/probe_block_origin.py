"""Is the Kiwi 403 coming from Kiwi, or from the corporate proxy?

`x-symc-transaction-uuid` on the 403 points at Symantec Web Security Service, which is a
corporate egress proxy, not Kiwi. If the proxy is denying the host then waiting will not
help and the fix is a policy exception, not backoff.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import config  # noqa: E402

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
     "Accept": "application/json", "Content-Type": "application/json",
     "Origin": "https://www.kiwi.com", "Referer": "https://www.kiwi.com/"}

client = httpx.Client(timeout=25.0, verify=config.CA_BUNDLE, follow_redirects=False)

TARGETS = [
    ("GET  www.kiwi.com", "GET", "https://www.kiwi.com/en/", None),
    ("GET  api.skypicker.com root", "GET", "https://api.skypicker.com/", None),
    ("POST api.skypicker.com graphql", "POST", "https://api.skypicker.com/umbrella/v2/graphql",
     json.dumps({"query": "{__typename}"})),
    ("GET  api.skypicker.com graphql", "GET", "https://api.skypicker.com/umbrella/v2/graphql", None),
    ("GET  tequila.kiwi.com", "GET", "https://api.tequila.kiwi.com/v2/search", None),
]

for label, method, url, body in TARGETS:
    try:
        if method == "POST":
            r = client.post(url, content=body, headers=H)
        else:
            r = client.get(url, headers={k: v for k, v in H.items() if k != "Content-Type"})
    except Exception as exc:
        print(f"{label:34} ERR {type(exc).__name__}: {str(exc)[:50]}")
        continue

    symc = any("symc" in k.lower() for k in r.headers)
    server = r.headers.get("server", "-")
    via = r.headers.get("via", "-")
    print(f"{label:34} {r.status_code}  server={server:12} symc={symc}  len={len(r.content)}")
    if r.status_code == 403:
        # A proxy denial usually has no upstream fingerprints (no fastly/cloudflare ids).
        marks = {k: v for k, v in r.headers.items()
                 if any(s in k.lower() for s in ("symc", "served-by", "cache", "via", "x-request"))}
        print(f"{'':34}   {marks}")

print("\nHeaders on a KNOWN-GOOD request to the same domain family, for comparison:")
try:
    r = client.get("https://www.kiwi.com/en/", headers={k: v for k, v in H.items() if k != "Content-Type"})
    print("  www.kiwi.com:", dict(list(r.headers.items())[:8]))
except Exception as exc:
    print("  failed:", exc)

client.close()
