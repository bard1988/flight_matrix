"""Verify the board still works when the live provider is rate-limited."""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import board  # noqa: E402
from models import SearchRequest  # noqa: E402

d = date.today() + timedelta(days=21)
r = d + timedelta(days=7)
req = SearchRequest(origin="TLV", depart_date=d.isoformat(), return_date=r.isoformat(),
                    adults=2, children=3, currency="ils", max_destinations=3)

for ev in board.build(req):
    kind = ev["type"]
    if kind == "provider_fallback":
        print("FALLBACK:", ev["message"][:150])
    elif kind == "destination":
        best, cov = ev["best"], ev["coverage"]
        print(f"  {ev['destination']:4} {ev['city'][:14]:14} best={best['estimate']:>8,.0f} "
              f"src={best.get('source')} total={best.get('is_total')} "
              f"cov={cov['populated']}/{cov['valid']}")
    elif kind == "error":
        print("ERROR:", ev["message"][:150])
    elif kind == "done":
        print("done:", ev["destinations"], "strategy", ev.get("strategy"))
