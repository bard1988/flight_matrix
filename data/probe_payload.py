"""Is fast-flights discarding itineraries?

Its parser reads only `payload[3][0]`. Google Flights normally returns two blocks
("best" and "other"). If a second list exists we are throwing away results, which would
explain seeing only 4-5 itineraries per route and never seeing El Al or Arkia.
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta

from fast_flights import FlightQuery, Passengers, create_query, fetch_flights_html
from selectolax.lexbor import LexborHTMLParser

DEST = sys.argv[1] if len(sys.argv) > 1 else "LON"
DEP = (date.today() + timedelta(days=25)).isoformat()
RET = (date.today() + timedelta(days=32)).isoformat()

q = create_query(
    flights=[
        FlightQuery(date=DEP, from_airport="TLV", to_airport=DEST),
        FlightQuery(date=RET, from_airport=DEST, to_airport="TLV"),
    ],
    trip="round-trip", seat="economy",
    passengers=Passengers(adults=2, children=3, infants_in_seat=0, infants_on_lap=0),
    currency="ILS",
)

html = fetch_flights_html(q)
parser = LexborHTMLParser(html)
script = parser.css_first(r"script.ds\:1")
js = script.text()
data = js.split("data:", 1)[1].rsplit(",", 1)[0]
payload = json.loads(data)

print(f"TLV-{DEST}  payload top-level length: {len(payload)}\n")
for i, block in enumerate(payload):
    kind = type(block).__name__
    size = len(block) if isinstance(block, (list, dict)) else "-"
    print(f"  payload[{i}]: {kind} len={size}")

# airline dictionary lives at payload[7][1][1]
try:
    airlines = {code: name for code, name in payload[7][1][1]}
    print(f"\nairline dictionary in response: {len(airlines)} carriers")
    for code, name in list(airlines.items()):
        print(f"    {code}  {name}")
except Exception as exc:
    print("airline dict unreadable:", exc)


def count_itins(block, label):
    if not isinstance(block, list) or not block:
        print(f"  {label}: empty/none")
        return
    inner = block[0]
    if not isinstance(inner, list):
        print(f"  {label}: [0] is {type(inner).__name__}")
        return
    print(f"  {label}: {len(inner)} itineraries")
    for k in inner[:8]:
        try:
            price = k[1][0][1]
            codes = k[0][1]
            print(f"      {price:>8} ILS  {codes}")
        except Exception:
            print("      (unparseable row)")


print("\nitinerary blocks:")
for idx in (2, 3, 4, 5):
    if idx < len(payload):
        count_itins(payload[idx], f"payload[{idx}][0]")
