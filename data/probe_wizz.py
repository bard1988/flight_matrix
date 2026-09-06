"""Probe Wizz Air's keyless endpoints. Wizz is the dominant low-cost carrier at TLV.

Wizz pins its API to a version string published in its own metadata, so discover that
first rather than hardcoding it.
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
      "Origin": "https://wizzair.com",
      "Referer": "https://wizzair.com/"}
client = httpx.Client(timeout=30.0, verify=config.CA_BUNDLE, headers=UA, follow_redirects=True)

print("1) discover API version")
api_url = None
for url in ("https://wizzair.com/static/metadata.json",
            "https://wizzair.com/en-gb/information-and-services/about-us"):
    try:
        r = client.get(url)
        print(f"   {url} -> HTTP {r.status_code}")
        if r.status_code == 200 and url.endswith(".json"):
            meta = r.json()
            api_url = meta.get("apiUrl")
            print(f"   apiUrl = {api_url}")
            break
        if r.status_code == 200:
            import re
            m = re.search(r"be\.wizzair\.com/(\d+\.\d+\.\d+)", r.text)
            if m:
                api_url = f"https://be.wizzair.com/{m.group(1)}/Api"
                print(f"   scraped version -> {api_url}")
                break
    except Exception as exc:
        print(f"   {url} -> {type(exc).__name__}: {str(exc)[:80]}")

if not api_url:
    print("   could not discover apiUrl; trying a recent guess")
    api_url = "https://be.wizzair.com/27.5.0/Api"

print(f"\n2) city pairs from TLV  ({api_url})")
try:
    r = client.get(f"{api_url}/asset/map", params={"languageCode": "en-gb"})
    print(f"   asset/map -> HTTP {r.status_code}")
    if r.status_code == 200:
        cities = r.json().get("cities", [])
        tlv = [c for c in cities if c.get("iata") == "TLV"]
        print(f"   cities: {len(cities)}   TLV present: {bool(tlv)}")
        if tlv:
            conns = tlv[0].get("connections", [])
            print(f"   TLV connections: {len(conns)}")
            print("   sample:", [c.get("iata") for c in conns[:15]])
except Exception as exc:
    print(f"   asset/map -> {type(exc).__name__}: {str(exc)[:90]}")

print("\n3) timetable (flexible-date prices) TLV -> BUD")
frm = date.today() + timedelta(days=14)
to = frm + timedelta(days=21)
body = {
    "flightList": [
        {"departureStation": "TLV", "arrivalStation": "BUD",
         "from": frm.isoformat(), "to": to.isoformat()},
        {"departureStation": "BUD", "arrivalStation": "TLV",
         "from": frm.isoformat(), "to": to.isoformat()},
    ],
    "priceType": "regular",
    "adultCount": 2,
    "childCount": 3,
    "infantCount": 0,
}
try:
    r = client.post(f"{api_url}/search/timetable", content=json.dumps(body))
    print(f"   HTTP {r.status_code}  {len(r.content)} bytes")
    if r.status_code == 200:
        data = r.json()
        outbound = data.get("outboundFlights", [])
        print(f"   outboundFlights: {len(outbound)}")
        for f in outbound[:8]:
            price = (f.get("price") or {})
            print(f"     {f.get('departureDate','')[:10]}  "
                  f"{price.get('amount')} {price.get('currencyCode')}  "
                  f"classOfService={f.get('classOfService')}")
    else:
        print(f"   {r.text[:200]}")
except Exception as exc:
    print(f"   {type(exc).__name__}: {str(exc)[:120]}")

client.close()
