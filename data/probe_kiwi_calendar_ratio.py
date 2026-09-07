"""Is Kiwi's price CALENDAR systematically cheaper than its own full search?

On TLV-CTA the calendar came back at almost exactly half the full-search price at every
passenger count. If that holds across routes and dates, the calendar is not a round-trip
total and FlightMatrix is understating every board cell.
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

CAL = """
query Cal($search: SearchReturnPricesCalendarInput, $options: ItinerariesOptionsInput) {
  returnItineraryPricesCalendar(search: $search, filter: {}, options: $options) {
    __typename ... on AppError { error: message }
    ... on ItineraryPricesCalendar { calendar { date ratedPrice { price { amount } } } }
  }
}
"""
SEARCH = """
query Ret($search: SearchReturnInput, $options: ItinerariesOptionsInput) {
  returnItineraries(search: $search, filter: {}, options: $options) {
    __typename ... on AppError { error: message }
    ... on Itineraries { itineraries { price { amount } } }
  }
}
"""
OPTS = {"currency": "ils", "locale": "en", "partner": "skypicker", "market": "il"}
PAX = {"adults": 2, "children": 0, "infants": 0}
CABIN = {"cabinClass": "ECONOMY", "applyMixedClasses": False}


def post(query, variables, op):
    time.sleep(1.6)
    r = client.post(ENDPOINT, content=json.dumps(
        {"query": query, "variables": variables, "operationName": op}))
    return r.json() if r.status_code == 200 else None


def cal_price(dest, dep, nights):
    v = {"search": {"source": {"ids": ["Station:airport:TLV"]},
                    "destination": {"ids": [f"Station:airport:{dest}"]},
                    "visibleDates": {"start": f"{dep}T00:00:00", "end": f"{dep}T23:59:59"},
                    "nightsCount": {"start": nights, "end": nights},
                    "passengers": PAX, "cabinClass": CABIN},
         "options": OPTS}
    d = post(CAL, v, "Cal")
    node = ((d or {}).get("data") or {}).get("returnItineraryPricesCalendar") or {}
    for item in node.get("calendar") or []:
        if str(item.get("date", ""))[:10] == dep:
            return float(item["ratedPrice"]["price"]["amount"])
    return None


def search_price(dest, dep, nights):
    ret = (date.fromisoformat(dep) + timedelta(days=nights)).isoformat()
    v = {"search": {"itinerary": {"source": {"ids": ["Station:airport:TLV"]},
                                  "destination": {"ids": [f"Station:airport:{dest}"]},
                                  "outboundDepartureDate": {"start": f"{dep}T00:00:00", "end": f"{dep}T23:59:59"},
                                  "inboundDepartureDate": {"start": f"{ret}T00:00:00", "end": f"{ret}T23:59:59"}},
                    "passengers": PAX, "cabinClass": CABIN},
         "options": OPTS}
    d = post(SEARCH, v, "Ret")
    node = ((d or {}).get("data") or {}).get("returnItineraries") or {}
    prices = [float(i["price"]["amount"]) for i in (node.get("itineraries") or []) if i.get("price")]
    return min(prices) if prices else None


CASES = [
    ("CTA", "2026-12-10", 16),
    ("ATH", "2026-10-15", 7),
    ("LCA", "2026-11-05", 5),
    ("BUD", "2026-11-20", 9),
    ("FCO", "2026-12-03", 6),
]

print(f"{'route':>10} {'depart':>12} {'nights':>7} {'calendar':>10} {'search':>10} {'ratio':>7}")
print("-" * 62)
ratios = []
for dest, dep, nights in CASES:
    c, s = cal_price(dest, dep, nights), search_price(dest, dep, nights)
    if c and s:
        ratios.append(s / c)
        print(f"{'TLV-'+dest:>10} {dep:>12} {nights:>7} {c:>10,.0f} {s:>10,.0f} {s/c:>7.2f}")
    else:
        print(f"{'TLV-'+dest:>10} {dep:>12} {nights:>7} {str(c):>10} {str(s):>10} {'-':>7}")

if ratios:
    print(f"\nsearch / calendar ratio: min {min(ratios):.2f}  max {max(ratios):.2f}  "
          f"mean {sum(ratios)/len(ratios):.2f}  (n={len(ratios)})")
client.close()
