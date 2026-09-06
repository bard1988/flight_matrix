"""Can we reach El Al / Arkia / Israir / Wizz directly, keylessly?

Time-boxed reconnaissance. Airline booking engines are usually behind bot protection and
have no public API; this records what actually happens rather than assuming.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import config  # noqa: E402

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept": "application/json, text/html;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,he;q=0.8",
}

TARGETS = {
    "El Al": [
        "https://www.elal.com/",
        "https://www.elal.com/api/flights/lowfare",
        "https://api.elal.com/",
        "https://booking.elal.com/",
    ],
    "Arkia": [
        "https://www.arkia.com/",
        "https://www.arkia.com/api/flights/search",
        "https://booking.arkia.com/",
    ],
    "Israir": [
        "https://www.israir.co.il/",
        "https://www.israir.co.il/api/flights",
        "https://booking.israir.co.il/",
    ],
    "Wizz Air": [
        "https://wizzair.com/",
        "https://wizzair.com/static/metadata.json",
        "https://be.wizzair.com/",
    ],
}

client = httpx.Client(timeout=20.0, verify=config.CA_BUNDLE, headers=UA, follow_redirects=True)

for airline, urls in TARGETS.items():
    print(f"\n=== {airline} ===")
    for url in urls:
        try:
            r = client.get(url)
        except Exception as exc:
            print(f"  {url[:52]:52} {type(exc).__name__}: {str(exc)[:40]}")
            continue
        ctype = (r.headers.get("content-type") or "").split(";")[0]
        title = re.search(r"<title>(.*?)</title>", r.text, re.S | re.I)
        note = ""
        if "json" in ctype:
            note = f"JSON! {r.text[:80]}"
        elif title:
            note = title.group(1).strip()[:56]
        # Look for tell-tale bot protection
        blob = r.text[:4000].lower()
        for marker in ("captcha", "akamai", "incapsula", "imperva", "cloudflare",
                       "access denied", "are you a human", "datadome", "perimeterx"):
            if marker in blob:
                note += f"  [{marker}]"
                break
        print(f"  {url[:52]:52} {r.status_code} {ctype:24} {note}")

# Does the site expose an API base in its own JS bundle?
print("\n=== scanning homepages for api hints ===")
for airline, urls in TARGETS.items():
    try:
        r = client.get(urls[0])
    except Exception:
        continue
    hints = set()
    for pat in (r"https?://[a-z0-9.\-]*api[a-z0-9.\-]*\.[a-z]{2,}[\w/\-.]*",
                r"be\.wizzair\.com/[\d.]+/Api",
                r"/api/[\w\-/]{3,30}"):
        hints.update(m.group(0) for m in re.finditer(pat, r.text, re.I))
    shown = sorted(hints)[:8]
    print(f"  {airline}: {shown if shown else 'no api references in initial HTML'}")

client.close()
