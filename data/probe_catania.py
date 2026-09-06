"""Do Catania's board cells correspond to itineraries that actually exist?

Compares each cheap CTA cell's board price against a full search for that exact date pair,
and prints the link so it can be opened.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import board  # noqa: E402
import cache  # noqa: E402
from models import SearchRequest  # noqa: E402
from providers.base import ProviderError  # noqa: E402
from providers.kiwi import KiwiProvider, slug_for  # noqa: E402

DEST = sys.argv[1] if len(sys.argv) > 1 else "CTA"
dep = date(2027, 8, 5)
ret = date(2027, 8, 23)

print(f"{DEST} slug: {slug_for(DEST)!r}")

req = SearchRequest(origin="TLV", depart_date=dep.isoformat(), return_date=ret.isoformat(),
                    adults=2, children=0, currency="ils", max_destinations=1,
                    destination_filter=DEST)

cells = []
for ev in board.build(req):
    if ev["type"] == "destination":
        cells = sorted(ev["cells"], key=lambda c: c["estimate"])[:5]

if not cells:
    print("no cells for that window")
    raise SystemExit

provider = KiwiProvider()
print(f"\n{'depart':12} {'return':12} {'board':>8} {'full search':>12}  status")
print("-" * 74)
for c in cells:
    try:
        d = provider.itinerary_details(req, DEST, c["depart"], c["ret"])
        real = d["price"]
        gap = 100 * (real - c["estimate"]) / c["estimate"]
        status = "ok" if abs(gap) < 15 else f"DIFFERS {gap:+.0f}%"
        print(f"{c['depart']:12} {c['ret']:12} {c['estimate']:>8,.0f} {real:>12,.0f}  {status}")
    except ProviderError as exc:
        print(f"{c['depart']:12} {c['ret']:12} {c['estimate']:>8,.0f} {'-':>12}  {str(exc)[:32]}")
    print(f"   link: {c.get('link')}")
