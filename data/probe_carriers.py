"""Does the existing Google Flights source surface El Al / Arkia / Israir / Wizz?

If it does, direct airline feeds would mostly duplicate what we already have, and the
argument for them is cross-checking rather than coverage.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from providers.base import ProviderError  # noqa: E402

DEP = (date.today() + timedelta(days=25)).isoformat()
RET = (date.today() + timedelta(days=32)).isoformat()

# Routes chosen to force particular carriers into the results.
ROUTES = [
    ("LON", "El Al, BA, Wizz all fly TLV-London"),
    ("BUD", "Wizz stronghold"),
    ("ATH", "Aegean / Israir / El Al"),
    ("LCA", "Israir / El Al / Wizz"),
    ("CDG", "El Al / Transavia"),
    ("EDI", "long thin route"),
]

print(f"TLV round trips {DEP} -> {RET}, 2 adults + 3 children\n")
print("Listing EVERY priced itinerary returned, not just the cheapest.\n")

try:
    from fast_flights import FlightQuery, Passengers, create_query, get_flights
except ImportError as exc:
    print("fast-flights missing:", exc)
    raise SystemExit(1)

from providers.google_flights import _airlines, _parse_price  # noqa: E402

seen: dict[str, int] = {}
for dest, why in ROUTES:
    try:
        q = create_query(
            flights=[
                FlightQuery(date=DEP, from_airport="TLV", to_airport=dest),
                FlightQuery(date=RET, from_airport=dest, to_airport="TLV"),
            ],
            trip="round-trip", seat="economy",
            passengers=Passengers(adults=2, children=3, infants_in_seat=0, infants_on_lap=0),
            currency="ILS",
        )
        results = list(get_flights(q) or [])
    except Exception as exc:
        print(f"TLV-{dest:4} ({why}): FAILED {type(exc).__name__}")
        continue

    rows = []
    for item in results:
        price = _parse_price(getattr(item, "price", None))
        name = _airlines(item) or "?"
        if price is not None:
            rows.append((name, price))
            for part in name.split(","):
                part = part.strip()
                seen[part] = seen.get(part, 0) + 1
    rows.sort(key=lambda r: r[1])
    print(f"TLV-{dest:4} ({why}): {len(rows)} itineraries")
    for name, price in rows[:6]:
        print(f"        {price:>8,.0f} ILS   {name}")

print("\ncarriers seen across all routes:")
for name, n in sorted(seen.items(), key=lambda kv: -kv[1]):
    print(f"  {n:>3}  {name}")

for target in ("El Al", "Arkia", "Israir", "Wizz"):
    hit = [k for k in seen if target.lower() in k.lower()]
    print(f"  {target:8} present? {'YES -> ' + ', '.join(hit) if hit else 'no'}")
