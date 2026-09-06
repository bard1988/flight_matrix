"""Does Kiwi's price calendar actually scale with passenger count?

SkyMatrix stores calendar prices with is_total=1, i.e. "this is the whole party's price".
If the calendar ignores passengers and returns a per-person or single-ticket "from" price,
every board number is understated by roughly the passenger count. Test it directly by
running the identical query at several passenger mixes.
"""
from __future__ import annotations

import json
import sys
import time
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

DEST = sys.argv[1] if len(sys.argv) > 1 else "CTA"
DEP = sys.argv[2] if len(sys.argv) > 2 else "2026-12-10"
NIGHTS = int(sys.argv[3]) if len(sys.argv) > 3 else 16

CAL = """
query Cal($search: SearchReturnPricesCalendarInput, $filter: ItinerariesFilterInput, $options: ItinerariesOptionsInput) {
  returnItineraryPricesCalendar(search: $search, filter: $filter, options: $options) {
    __typename
    ... on AppError { error: message }
    ... on ItineraryPricesCalendar { calendar { date ratedPrice { price { amount } } } }
  }
}
"""

ONE_WAY_CHECK = """
query Ret($search: SearchReturnInput, $filter: ItinerariesFilterInput, $options: ItinerariesOptionsInput) {
  returnItineraries(search: $search, filter: $filter, options: $options) {
    __typename
    ... on AppError { error: message }
    ... on Itineraries { itineraries { price { amount } ... on ItineraryReturn { priceEur { amount } } } }
  }
}
"""

dep = date.fromisoformat(DEP)


def calendar_price(adults: int, children: int) -> float | None:
    variables = {
        "search": {
            "source": {"ids": ["Station:airport:TLV"]},
            "destination": {"ids": [f"Station:airport:{DEST}"]},
            "visibleDates": {"start": f"{DEP}T00:00:00", "end": f"{DEP}T23:59:59"},
            "nightsCount": {"start": NIGHTS, "end": NIGHTS},
            "passengers": {"adults": adults, "children": children, "infants": 0},
            "cabinClass": {"cabinClass": "ECONOMY", "applyMixedClasses": False},
        },
        "filter": {},
        "options": {"currency": "ils", "locale": "en", "partner": "skypicker", "market": "il"},
    }
    time.sleep(1.5)
    r = client.post(ENDPOINT, content=json.dumps(
        {"query": CAL, "variables": variables, "operationName": "Cal"}))
    if r.status_code != 200:
        print(f"    HTTP {r.status_code}")
        return None
    node = (r.json().get("data") or {}).get("returnItineraryPricesCalendar") or {}
    if node.get("error"):
        print(f"    app error: {node['error'][:80]}")
        return None
    for item in node.get("calendar") or []:
        if str(item.get("date", ""))[:10] == DEP:
            return float(item["ratedPrice"]["price"]["amount"])
    return None


def search_price(adults: int, children: int) -> float | None:
    ret = dep + timedelta(days=NIGHTS)
    variables = {
        "search": {
            "itinerary": {
                "source": {"ids": ["Station:airport:TLV"]},
                "destination": {"ids": [f"Station:airport:{DEST}"]},
                "outboundDepartureDate": {"start": f"{DEP}T00:00:00", "end": f"{DEP}T23:59:59"},
                "inboundDepartureDate": {"start": f"{ret.isoformat()}T00:00:00",
                                         "end": f"{ret.isoformat()}T23:59:59"},
            },
            "passengers": {"adults": adults, "children": children, "infants": 0},
            "cabinClass": {"cabinClass": "ECONOMY", "applyMixedClasses": False},
        },
        "filter": {},
        "options": {"currency": "ils", "locale": "en", "partner": "skypicker", "market": "il"},
    }
    time.sleep(1.5)
    r = client.post(ENDPOINT, content=json.dumps(
        {"query": ONE_WAY_CHECK, "variables": variables, "operationName": "Ret"}))
    if r.status_code != 200:
        return None
    node = (r.json().get("data") or {}).get("returnItineraries") or {}
    if node.get("error"):
        return None
    items = node.get("itineraries") or []
    prices = [float(i["price"]["amount"]) for i in items if i.get("price")]
    return min(prices) if prices else None


print(f"TLV -> {DEST}, depart {DEP}, {NIGHTS} nights\n")
print(f"{'passengers':>16} {'calendar':>10} {'full search':>12}")
print("-" * 42)
for adults, children in ((1, 0), (2, 0), (3, 0), (2, 3)):
    cal = calendar_price(adults, children)
    srch = search_price(adults, children)
    label = f"{adults}a" + (f"+{children}c" if children else "")
    print(f"{label:>16} {cal if cal is None else f'{cal:,.0f}':>10} "
          f"{srch if srch is None else f'{srch:,.0f}':>12}")

client.close()
