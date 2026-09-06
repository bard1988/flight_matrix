"""Can the calendar be pinned to a RETURN date instead of a nights count?

The board currently pins `nightsCount` and infers return = departure + nights. That
inference is what put a price on a Catania trip that cannot be booked. If `returnDates`
can be pinned instead, the return date is known by construction and nothing is inferred.

Verifies by re-pricing each returned departure with a full search for that exact pair.
"""
import sys
import pathlib
from datetime import date, timedelta

sys.path.insert(0, str(pathlib.Path("backend").resolve()))

import httpx
import config
from models import SearchRequest, parse_date
from providers.kiwi import ENDPOINT, _CALENDAR, KiwiProvider, _day_start, _day_end

DEST = (sys.argv[1] if len(sys.argv) > 1 else "CTA").upper()
RET = sys.argv[2] if len(sys.argv) > 2 else "2027-08-20"
FIRST = sys.argv[3] if len(sys.argv) > 3 else "2027-08-05"
LAST = sys.argv[4] if len(sys.argv) > 4 else "2027-08-12"

prov = KiwiProvider()
req = SearchRequest(origin="TLV", depart_date=FIRST, return_date=RET,
                    adults=2, children=0, currency="ils")

variables = {
    "search": {
        "source": {"ids": [f"Station:airport:{req.origin.upper()}"]},
        "destination": {"ids": [f"Station:airport:{DEST}"]},
        "visibleDates": {"start": _day_start(parse_date(FIRST)),
                         "end": _day_end(parse_date(LAST))},
        "returnDates": {"start": _day_start(parse_date(RET)),
                        "end": _day_end(parse_date(RET))},
        "passengers": prov._passengers(req),
        "cabinClass": {"cabinClass": "ECONOMY", "applyMixedClasses": False},
    },
    "filter": prov._filter(req),
    "options": prov._options(req),
}

with httpx.Client(timeout=60, verify=config.CA_BUNDLE,
                  headers={"content-type": "application/json"}) as client:
    r = client.post(ENDPOINT, json={"query": _CALENDAR, "variables": variables})
    payload = r.json()

node = (payload.get("data") or {}).get("returnItineraryPricesCalendar") or {}
if payload.get("errors"):
    print("GraphQL errors:", payload["errors"][:2])
if node.get("error"):
    print("AppError:", node["error"])

entries = node.get("calendar") or []
print(f"returnDates pinned to {RET}, visibleDates {FIRST}..{LAST} -> {len(entries)} entries\n")
print(f"{'entry date':<14}{'calendar':>10}   full search for (entry date -> pinned return)")
for item in entries:
    try:
        d = date.fromisoformat(str(item["date"])[:10])
        price = float(item["ratedPrice"]["price"]["amount"])
    except (KeyError, TypeError, ValueError):
        continue
    try:
        det = f"{prov.itinerary_details(req, DEST, d.isoformat(), RET)['price']:,.0f}"
    except Exception as exc:
        det = type(exc).__name__
    match = "MATCH" if det.replace(",", "") == f"{price:.0f}" else ""
    print(f"{d.isoformat():<14}{price:>10,.0f}   {det:>22}  {match}", flush=True)
