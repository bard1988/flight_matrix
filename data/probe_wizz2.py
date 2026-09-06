"""Test Wizz Air's API at the version discovered from their own homepage bundle."""
from __future__ import annotations

import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import config  # noqa: E402

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Origin": "https://wizzair.com",
    "Referer": "https://wizzair.com/en-gb/flights/timetable",
    "Accept-Language": "en-US,en;q=0.9",
}
client = httpx.Client(timeout=30.0, verify=config.CA_BUNDLE, headers=UA, follow_redirects=True)

# Re-discover the version rather than hardcoding, since Wizz bumps it often.
home = client.get("https://wizzair.com/")
m = re.search(r"be\.wizzair\.com/([\d.]+)/Api", home.text)
version = m.group(1) if m else "29.15.1"
api = f"https://be.wizzair.com/{version}/Api"
print(f"discovered version {version}\napi base {api}\n")

print("1) route map")
r = client.get(f"{api}/asset/map", params={"languageCode": "en-gb"})
print(f"   asset/map -> HTTP {r.status_code}  {len(r.content)} bytes")
tlv_conns = []
if r.status_code == 200:
    try:
        cities = r.json().get("cities", [])
        print(f"   cities: {len(cities)}")
        tlv = [c for c in cities if c.get("iata") == "TLV"]
        if tlv:
            tlv_conns = [c.get("iata") for c in tlv[0].get("connections", [])]
            print(f"   TLV connections: {len(tlv_conns)}")
            print(f"   {sorted(tlv_conns)}")
        else:
            print("   TLV not in Wizz city list")
    except Exception as exc:
        print("   parse failed:", exc)
else:
    print("   body:", r.text[:160])

print("\n2) timetable TLV -> BUD (flexible dates, real pax)")
frm = date.today() + timedelta(days=16)
to = frm + timedelta(days=20)
body = {
    "flightList": [
        {"departureStation": "TLV", "arrivalStation": "BUD", "from": frm.isoformat(), "to": to.isoformat()},
        {"departureStation": "BUD", "arrivalStation": "TLV", "from": frm.isoformat(), "to": to.isoformat()},
    ],
    "priceType": "regular",
    "adultCount": 2,
    "childCount": 3,
    "infantCount": 0,
}
r = client.post(f"{api}/search/timetable", content=json.dumps(body))
print(f"   HTTP {r.status_code}  {len(r.content)} bytes")
if r.status_code == 200:
    data = r.json()
    for key in ("outboundFlights", "returnFlights"):
        flights = data.get(key, [])
        print(f"   {key}: {len(flights)}")
        for f in flights[:6]:
            p = f.get("price") or {}
            print(f"      {str(f.get('departureDate'))[:10]}  {p.get('amount')} {p.get('currencyCode')}"
                  f"  classOfService={f.get('classOfService')}")
else:
    print("   body:", r.text[:300])

client.close()
