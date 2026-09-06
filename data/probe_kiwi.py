"""Probe Kiwi.com's public front-end endpoints.

Kiwi is worth chasing because its virtual-interlining combinations are fares no other
aggregator shows, so it is genuinely additive rather than duplicative.
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import config  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept": "application/json, text/plain, */*",
      "Content-Type": "application/json",
      "Origin": "https://www.kiwi.com", "Referer": "https://www.kiwi.com/"}
client = httpx.Client(timeout=30.0, verify=config.CA_BUNDLE, headers=UA, follow_redirects=True)

dep = date.today() + timedelta(days=25)
ret = dep + timedelta(days=7)
dep_s, ret_s = dep.strftime("%d/%m/%Y"), ret.strftime("%d/%m/%Y")

print("1) legacy skypicker search (was open for years)")
for base in ("https://api.skypicker.com/flights", "https://api.tequila.kiwi.com/v2/search"):
    try:
        r = client.get(base, params={
            "fly_from": "TLV", "fly_to": "BUD",
            "date_from": dep_s, "date_to": dep_s,
            "return_from": ret_s, "return_to": ret_s,
            "adults": 2, "children": 3, "curr": "ILS",
            "partner": "picky", "v": 3, "limit": 5,
        })
        print(f"   {base[:46]:46} HTTP {r.status_code}  {r.text[:90]}")
    except Exception as exc:
        print(f"   {base[:46]:46} {type(exc).__name__}: {str(exc)[:60]}")

print("\n2) umbrella graphql (what kiwi.com itself calls)")
for url in ("https://api.skypicker.com/umbrella/v2/graphql",
            "https://api.kiwi.com/umbrella/v2/graphql"):
    try:
        r = client.post(url, content=json.dumps({"query": "{__typename}"}))
        print(f"   {url[:46]:46} HTTP {r.status_code}  {r.text[:90]}")
    except Exception as exc:
        print(f"   {url[:46]:46} {type(exc).__name__}: {str(exc)[:60]}")

print("\n3) does kiwi.com itself load (is it reachable at all)?")
try:
    r = client.get("https://www.kiwi.com/en/")
    print(f"   HTTP {r.status_code}  {len(r.content)} bytes")
except Exception as exc:
    print(f"   {type(exc).__name__}: {str(exc)[:70]}")

client.close()
