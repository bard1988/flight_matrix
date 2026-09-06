"""Range mode: two dates bound a period, nights say what to look for inside it."""
from __future__ import annotations

import sys
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import board  # noqa: E402
from models import SearchRequest  # noqa: E402

start = date.today() + timedelta(days=60)
end = start + timedelta(days=56)          # ~2 months of possible travel

req = SearchRequest(
    origin="TLV", depart_date=start.isoformat(), return_date=end.isoformat(),
    adults=2, children=0, currency="ils", max_destinations=3,
    date_mode="range", nights_min=3, nights_max=4,
)
dd, rd = board.date_axes(req)
print(f"range {start} .. {end}  ({(end-start).days} days), 3-4 night trips")
print(f"  departure axis: {dd[0]}..{dd[-1]} ({len(dd)} days)")
print(f"  return axis   : {rd[0]}..{rd[-1]} ({len(rd)} days)")
print(f"  trip lengths searched: {req.nights_span()}  -> {len(req.nights_span())} calls/destination\n")

t0 = time.time()
for ev in board.build(req):
    if ev["type"] == "destination":
        cells = ev["cells"]
        lens = sorted({c["nights"] for c in cells})
        best = ev["best"]
        print(f"  {ev['destination']:4} {ev['city'][:16]:16} cells={len(cells):>4} "
              f"nights={lens} best={best['estimate']:>7,.0f} on {best['depart']} ({best['nights']}n)")
    elif ev["type"] == "done":
        print(f"\n  {ev['destinations']} destinations in {time.time()-t0:.0f}s")
