"""Run Kiwi's anywhere-from-TLV search for a real family, and print the results."""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import config  # noqa: E402

URL = "https://api.skypicker.com/umbrella/v2/graphql"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept": "application/json", "Content-Type": "application/json",
      "Origin": "https://www.kiwi.com", "Referer": "https://www.kiwi.com/"}
client = httpx.Client(timeout=90.0, verify=config.CA_BUNDLE, headers=UA, follow_redirects=True)

QUERY = """
query OnePerCity($search: SearchReturnInput, $filter: ItinerariesFilterInput, $options: ItinerariesOptionsInput) {
  returnOnePerCityItineraries(search: $search, filter: $filter, options: $options) {
    __typename
    ... on AppError { error: message }
    ... on OnePerCityItineraries {
      itineraries {
        __typename
        price { amount }
        departureDate
        destination { station { code city { name country { code } } } }
      }
    }
  }
}
"""

dep = date.today() + timedelta(days=18)
variables = {
    "search": {
        "itinerary": {
            "source": {"ids": ["Station:airport:TLV"]},
            "outboundDepartureDate": {
                "start": f"{dep.isoformat()}T00:00:00",
                "end": f"{(dep + timedelta(days=6)).isoformat()}T23:59:59",
            },
            "inboundDepartureDate": {
                "start": f"{(dep + timedelta(days=5)).isoformat()}T00:00:00",
                "end": f"{(dep + timedelta(days=14)).isoformat()}T23:59:59",
            },
        },
        "passengers": {"adults": 2, "children": 3, "infants": 0},
        "cabinClass": {"cabinClass": "ECONOMY", "applyMixedClasses": False},
    },
    "filter": {},
    "options": {"currency": "ils", "locale": "en", "partner": "skypicker", "market": "il"},
}

r = client.post(URL, content=json.dumps(
    {"query": QUERY, "variables": variables, "operationName": "OnePerCity"}))
print("HTTP", r.status_code)
payload = r.json()
if payload.get("errors"):
    print("errors:")
    for e in payload["errors"][:6]:
        print("   ", e.get("message"), "at", ".".join(str(p) for p in (e.get("path") or [])))

data = (payload.get("data") or {}).get("returnOnePerCityItineraries")
if not data:
    sys.exit(0)
print("typename:", data.get("__typename"))
if data.get("error"):
    print("app error:", data["error"])
    sys.exit(0)

items = data.get("itineraries") or []
print(f"\n{len(items)} destinations returned (one per city), 2 adults + 3 children, ILS\n")
rows = []
for it in items:
    try:
        price = float(it["price"]["amount"])
        station = (it.get("destination") or {}).get("station") or {}
        city = (station.get("city") or {})
        rows.append((price, station.get("code"), city.get("name"),
                     ((city.get("country") or {}).get("code") or ""),
                     str(it.get("departureDate"))[:10]))
    except Exception:
        continue
rows.sort()
print(f"{'price':>9}  {'dest':5} {'city':18} {'cc':3} {'depart':10}")
for p, code, city, cc, d in rows[:30]:
    print(f"{p:>9,.0f}  {(code or '?'):5} {(city or '')[:18]:18} {cc:3} {d:10}")

client.close()
