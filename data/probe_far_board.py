"""Build a board far ahead and check the advisory note is now correct."""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import board  # noqa: E402
from models import SearchRequest  # noqa: E402

for days in [int(a) for a in sys.argv[1:]] or [208, 340]:
    dep = date.today() + timedelta(days=days)
    ret = dep + timedelta(days=7)
    req = SearchRequest(origin="TLV", depart_date=dep.isoformat(), return_date=ret.isoformat(),
                        adults=2, children=3, currency="ils", max_destinations=2)
    print(f"\n=== {days} days out, departing {dep} ===")
    for ev in board.build(req):
        if ev["type"] == "destination":
            cov = ev["coverage"]
            print(f"  {ev['destination']:4} {ev['city'][:14]:14} "
                  f"cov={cov['populated']}/{cov['valid']} "
                  f"best={ev['best']['estimate']:,.0f} src={ev['best'].get('source')}")
        elif ev["type"] == "done":
            print(f"  note: {ev['note']}")
        elif ev["type"] in ("error", "provider_fallback"):
            print(f"  {ev['type']}: {ev['message'][:110]}")
