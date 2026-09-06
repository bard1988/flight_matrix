"""Nail down Wizz specifics before writing the provider.

Open questions: can we ask for ILS, how hard is the rate limit, and does a round-trip
request give separable per-leg prices we can combine into a grid?
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import config  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept": "application/json, text/plain, */*", "Content-Type": "application/json",
      "Origin": "https://wizzair.com", "Referer": "https://wizzair.com/"}
client = httpx.Client(timeout=30.0, verify=config.CA_BUNDLE, headers=UA, follow_redirects=True)

home = client.get("https://wizzair.com/")
version = (re.search(r"be\.wizzair\.com/([\d.]+)/Api", home.text) or [None, "29.15.1"])[1]
api = f"https://be.wizzair.com/{version}/Api"
print(f"api {api}\n")

frm = date.today() + timedelta(days=16)
to = frm + timedelta(days=14)


def call(body: dict, label: str, pause: float = 3.0):
    time.sleep(pause)
    r = client.post(f"{api}/search/timetable", content=json.dumps(body))
    ok = r.status_code == 200
    print(f"  {label:38} HTTP {r.status_code}" + ("" if ok else f"  {r.text[:80]}"))
    return r.json() if ok else None


legs = [
    {"departureStation": "TLV", "arrivalStation": "BUD", "from": frm.isoformat(), "to": to.isoformat()},
    {"departureStation": "BUD", "arrivalStation": "TLV", "from": frm.isoformat(), "to": to.isoformat()},
]

print("1) currency control")
for extra, label in (
    ({}, "no currency field"),
    ({"currencyCode": "ILS"}, "currencyCode=ILS"),
    ({"currency": "ILS"}, "currency=ILS"),
):
    data = call({"flightList": legs, "priceType": "regular",
                 "adultCount": 1, "childCount": 0, "infantCount": 0, **extra}, label)
    if data:
        out = data.get("outboundFlights", [])
        cur = {(f.get("price") or {}).get("currencyCode") for f in out if (f.get("price") or {}).get("amount")}
        print(f"      -> currencies returned: {cur or 'none'}  ({len(out)} outbound rows)")

print("\n2) separability: are outbound and return priced independently?")
data = call({"flightList": legs, "priceType": "regular",
             "adultCount": 1, "childCount": 0, "infantCount": 0}, "round trip both legs")
if data:
    out = {str(f["departureDate"])[:10]: (f.get("price") or {}).get("amount")
           for f in data.get("outboundFlights", [])}
    back = {str(f["departureDate"])[:10]: (f.get("price") or {}).get("amount")
            for f in data.get("returnFlights", [])}
    print(f"      outbound dated prices: {len(out)}  return dated prices: {len(back)}")
    nz_out = {k: v for k, v in out.items() if v}
    nz_back = {k: v for k, v in back.items() if v}
    print(f"      non-zero: outbound {len(nz_out)}, return {len(nz_back)}")
    print(f"      cheapest outbound {min(nz_out.values()) if nz_out else '-'}, "
          f"cheapest return {min(nz_back.values()) if nz_back else '-'}")
    print(f"      => a {len(nz_out)}x{len(nz_back)} grid from ONE call "
          f"= {len(nz_out)*len(nz_back)} cells")

print("\n3) how fast can we call it?")
fails = 0
for i in range(6):
    body = {"flightList": legs, "priceType": "regular",
            "adultCount": 1, "childCount": 0, "infantCount": 0}
    time.sleep(1.0)
    r = client.post(f"{api}/search/timetable", content=json.dumps(body))
    print(f"  call {i+1} @1s spacing -> HTTP {r.status_code}")
    if r.status_code != 200:
        fails += 1
print(f"  {fails}/6 failed at 1s spacing")

client.close()
