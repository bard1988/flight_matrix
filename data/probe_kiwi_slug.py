"""What identifiers does kiwi.com's own search URL expect?

Our deeplink used bare IATA codes (/results/tlv/vce/...) and Kiwi loaded the page with
empty From/To boxes. Kiwi's City type exposes `slug`, so ask the API for the real ones.
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import config  # noqa: E402

ENDPOINT = "https://api.skypicker.com/umbrella/v2/graphql"
HEAD = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
        "Accept": "application/json", "Content-Type": "application/json",
        "Origin": "https://www.kiwi.com", "Referer": "https://www.kiwi.com/"}
client = httpx.Client(timeout=60.0, verify=config.CA_BUNDLE, headers=HEAD, follow_redirects=True)

Q = """
query OnePerCity($search: SearchReturnInput, $options: ItinerariesOptionsInput) {
  returnOnePerCityItineraries(search: $search, filter: {}, options: $options) {
    __typename
    ... on AppError { error: message }
    ... on OnePerCityItineraries {
      itineraries {
        price { amount }
        source { station { code slug city { name slug legacyId } } }
        destination { station { code slug city { name slug legacyId } } }
      }
    }
  }
}
"""

dep = date.today() + timedelta(days=60)
variables = {
    "search": {
        "itinerary": {
            "source": {"ids": ["Station:airport:TLV"]},
            "outboundDepartureDate": {"start": f"{dep.isoformat()}T00:00:00",
                                      "end": f"{(dep + timedelta(days=3)).isoformat()}T23:59:59"},
            "inboundDepartureDate": {"start": f"{(dep + timedelta(days=5)).isoformat()}T00:00:00",
                                     "end": f"{(dep + timedelta(days=9)).isoformat()}T23:59:59"},
        },
        "passengers": {"adults": 2, "children": 0, "infants": 0},
        "cabinClass": {"cabinClass": "ECONOMY", "applyMixedClasses": False},
    },
    "options": {"currency": "ils", "locale": "en", "partner": "skypicker", "market": "il"},
}

r = client.post(ENDPOINT, content=json.dumps(
    {"query": Q, "variables": variables, "operationName": "OnePerCity"}))
payload = r.json()
if payload.get("errors"):
    print("errors:", json.dumps(payload["errors"])[:400])
node = (payload.get("data") or {}).get("returnOnePerCityItineraries") or {}
print("typename:", node.get("__typename"), node.get("error") or "")

for item in (node.get("itineraries") or [])[:6]:
    src = (item.get("source") or {}).get("station") or {}
    dst = (item.get("destination") or {}).get("station") or {}
    sc, dc = src.get("city") or {}, dst.get("city") or {}
    print(f"\n  {src.get('code')} -> {dst.get('code')}")
    print(f"    source  station.slug={src.get('slug')!r}  city.slug={sc.get('slug')!r}")
    print(f"    dest    station.slug={dst.get('slug')!r}  city.slug={dc.get('slug')!r}")
    print(f"    candidate URL: https://www.kiwi.com/en/search/results/"
          f"{sc.get('slug')}/{dc.get('slug')}/{dep.isoformat()}/"
          f"{(dep + timedelta(days=5)).isoformat()}")

client.close()
