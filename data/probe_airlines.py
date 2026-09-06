"""Probe keyless airline endpoints as a coverage source.

Ryanair and Wizz Air expose the endpoints their own websites call. They are not
documented public APIs, but they need no key and Ryanair's `farfnd` is shaped exactly
like this app: cheapest round trips from an origin to EVERY destination over a date range.

    py -3 data/probe_airlines.py [ORIGIN]
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import config  # noqa: E402

ORIGIN = sys.argv[1] if len(sys.argv) > 1 else "TLV"
OUT_FROM = date.today() + timedelta(days=14)
OUT_TO = date.today() + timedelta(days=28)
IN_FROM = date.today() + timedelta(days=21)
IN_TO = date.today() + timedelta(days=35)

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}

client = httpx.Client(timeout=30.0, verify=config.CA_BUNDLE, headers=UA, follow_redirects=True)


def show(label: str, url: str, params: dict | None = None) -> dict | list | None:
    try:
        r = client.get(url, params=params)
    except Exception as exc:
        print(f"  {label}: {type(exc).__name__}: {str(exc)[:90]}")
        return None
    print(f"  {label}: HTTP {r.status_code}  {len(r.content)} bytes")
    if r.status_code != 200:
        print(f"      {r.text[:160]}")
        return None
    try:
        return r.json()
    except Exception:
        print(f"      not json: {r.text[:120]}")
        return None


print(f"origin {ORIGIN}   outbound {OUT_FROM}..{OUT_TO}   inbound {IN_FROM}..{IN_TO}\n")

print("RYANAIR")
data = show(
    "farfnd v4 roundTripFares (all destinations)",
    "https://services-api.ryanair.com/farfnd/v4/roundTripFares",
    {
        "departureAirportIataCode": ORIGIN,
        "outboundDepartureDateFrom": OUT_FROM.isoformat(),
        "outboundDepartureDateTo": OUT_TO.isoformat(),
        "inboundDepartureDateFrom": IN_FROM.isoformat(),
        "inboundDepartureDateTo": IN_TO.isoformat(),
        "market": "en-gb",
        "adultPaxCount": 2,
        "limit": 200,
    },
)
if isinstance(data, dict):
    fares = data.get("fares") or []
    print(f"      fares: {len(fares)}")
    for fare in fares[:5]:
        out = fare.get("outbound", {})
        inb = fare.get("inbound", {})
        print(f"        {out.get('departureAirport',{}).get('iataCode')} -> "
              f"{out.get('arrivalAirport',{}).get('iataCode')} "
              f"{str(out.get('departureDate'))[:10]} / {str(inb.get('departureDate'))[:10]} "
              f"{fare.get('summary',{}).get('price',{}).get('value')} "
              f"{fare.get('summary',{}).get('price',{}).get('currencyCode')}")
    if not fares:
        print("      (no fares - Ryanair may not serve this origin)")

show("active airports", "https://www.ryanair.com/api/views/locate/5/airports/en/active")

print("\nWIZZ AIR")
meta = show("map/cities", "https://be.wizzair.com/27.4.0/Api/asset/map", {"languageCode": "en-gb"})
if meta is None:
    show("metadata fallback", "https://be.wizzair.com/27.4.0/Api/asset/farechart")

print("\nRYANAIR one-way fares (price calendar shape)")
show(
    "farfnd v4 oneWayFares",
    "https://services-api.ryanair.com/farfnd/v4/oneWayFares",
    {
        "departureAirportIataCode": ORIGIN,
        "outboundDepartureDateFrom": OUT_FROM.isoformat(),
        "outboundDepartureDateTo": OUT_TO.isoformat(),
        "market": "en-gb",
        "adultPaxCount": 1,
        "limit": 200,
    },
)

client.close()
