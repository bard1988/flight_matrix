"""With nonstop_only, does ANY returned itinerary still have a stop (either leg)?"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import board  # noqa: E402
from models import SearchRequest  # noqa: E402
from providers.base import ProviderError  # noqa: E402
from providers.kiwi import KiwiProvider  # noqa: E402

dep = date.today() + timedelta(days=30)
ret = dep + timedelta(days=7)

req = SearchRequest(origin="TLV", depart_date=dep.isoformat(), return_date=ret.isoformat(),
                    adults=2, children=0, currency="ils", max_destinations=3,
                    nonstop_only=True)

print(f"nonstop_only=True, TLV, depart ~{dep}\n")
targets = []
for ev in board.build(req):
    if ev["type"] == "destination":
        cells = sorted(ev["cells"], key=lambda c: c["estimate"])[:4]
        for c in cells:
            targets.append((ev["destination"], c["depart"], c["ret"], c["estimate"]))

provider = KiwiProvider()
violations = 0
for dest, d, r, price in targets:
    try:
        det = provider.itinerary_details(req, dest, d, r)
    except ProviderError as exc:
        print(f"  {dest} {d}->{r}: {str(exc)[:50]}")
        continue
    out = (det.get("outbound") or {}).get("stops")
    back = (det.get("inbound") or {}).get("stops")
    bad = (out or 0) > 0 or (back or 0) > 0
    if bad:
        violations += 1
    flag = "  <-- HAS STOPS" if bad else ""
    print(f"  {dest} {d}->{r}  {det['price']:>7,.0f}  out {out} stops / back {back} stops{flag}")

print(f"\n{violations} of {len(targets)} sampled itineraries violate nonstop-only")
