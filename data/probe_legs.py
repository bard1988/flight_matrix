"""Find a connecting itinerary so the numbered-leg rendering is actually exercised."""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from models import SearchRequest  # noqa: E402
from providers.base import ProviderError  # noqa: E402
from providers.kiwi import KiwiProvider  # noqa: E402

dep = date.today() + timedelta(days=45)
ret = dep + timedelta(days=7)

# Long-haul / thin routes from TLV that normally need a connection.
DESTS = ["EDI", "DUB", "LIS", "OPO", "BIO", "GLA", "KEF", "TLL"]

provider = KiwiProvider()
for dest in DESTS:
    req = SearchRequest(origin="TLV", depart_date=dep.isoformat(), return_date=ret.isoformat(),
                        adults=2, children=0, currency="ils")
    try:
        d = provider.itinerary_details(req, dest, dep.isoformat(), ret.isoformat())
    except ProviderError as exc:
        print(f"{dest}: {str(exc)[:50]}")
        continue
    out = d.get("outbound") or {}
    if not out.get("stops"):
        print(f"{dest}: nonstop, not useful for this test")
        continue
    print(f"\n{dest}: {d['price']:,.0f} ILS")
    for way in ("outbound", "inbound"):
        s = d.get(way) or {}
        print(f"  {way}: {s.get('departs')} -> {s.get('arrives')} · {s.get('duration')} · "
              f"{s.get('stops')} stops")
        for i, leg in enumerate(s.get("legs") or [], 1):
            print(f"     {i}. {leg['from']} -> {leg['to']}  {leg['departs']} -> {leg['arrives']}"
                  f"  {leg['carrier'] or ''} {leg['code'] or ''}")
    break
