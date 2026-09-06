"""Fetch real flight times for one cell from Kiwi, including far-out dates."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from models import SearchRequest  # noqa: E402
from providers.base import ProviderError  # noqa: E402
from providers.kiwi import KiwiProvider  # noqa: E402

CASES = [
    ("LCA", "2027-08-16", "2027-08-26", 2, 3),   # far out - Google has nothing here
    ("LCA", "2026-10-03", "2026-10-13", 2, 3),
    ("ATH", "2026-10-20", "2026-10-27", 2, 0),
]

provider = KiwiProvider()
for dest, dep, ret, adults, children in CASES:
    req = SearchRequest(origin="TLV", depart_date=dep, return_date=ret,
                        adults=adults, children=children, currency="ils")
    label = f"{dest} {dep}->{ret} {adults}a{children}c"
    try:
        d = provider.itinerary_details(req, dest, dep, ret)
    except ProviderError as exc:
        print(f"{label}: {str(exc)[:70]}")
        continue
    print(f"\n{label}: {d['price']:,.0f} ILS")
    for way in ("outbound", "inbound"):
        s = d.get(way)
        if not s:
            print(f"   {way}: -")
            continue
        print(f"   {way}: {s['departs']} -> {s['arrives']}  "
              f"{s['duration']}  {s['stops']} stops  {s['carriers']}")
        for leg in s["legs"]:
            print(f"       {leg['from']} -> {leg['to']}  {leg['departs']} -> {leg['arrives']}"
                  f"  {leg['carrier'] or ''} {leg['code'] or ''}")
