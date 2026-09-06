"""How wrong are the cached estimates, and is the error worse for the cheapest cells?

Verifying only a destination's cheapest cell is a worst case by construction: the cheapest
cached fare is the one most likely to be a one-or-two-seat headline price that cannot take
five passengers. Sampling a median cell as well separates that selection effect from the
general estimate error.

    py -3 data/estimate_error.py [days_out] [n_destinations]
"""
from __future__ import annotations

import statistics
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import board  # noqa: E402
from models import SearchRequest  # noqa: E402
from providers.base import ProviderError  # noqa: E402
from providers.google_flights import GoogleFlightsProvider  # noqa: E402

DAYS_OUT = int(sys.argv[1]) if len(sys.argv) > 1 else 21
N_DEST = int(sys.argv[2]) if len(sys.argv) > 2 else 5

depart = date.today() + timedelta(days=DAYS_OUT)
ret = depart + timedelta(days=7)
request = SearchRequest(
    origin="TLV", depart_date=depart.isoformat(), return_date=ret.isoformat(),
    adults=2, children=3, currency="ils", max_destinations=N_DEST,
)

print(f"TLV, 2 adults + 3 children, depart ~{depart}\n")
destinations = []
for event in board.build(request):
    if event["type"] == "destination" and event.get("cells"):
        cells = sorted(
            (c for c in event["cells"] if c.get("estimate") is not None),
            key=lambda c: c["estimate"],
        )
        if cells:
            destinations.append((event["destination"], cells))

verifier = GoogleFlightsProvider()
buckets: dict[str, list[float]] = {"cheapest": [], "median": []}

print(f"{'dest':5} {'bucket':9} {'dates':>24} {'estimate':>9} {'live':>9} {'delta':>8}")
print("-" * 72)
for code, cells in destinations:
    picks = [("cheapest", cells[0])]
    if len(cells) > 2:
        picks.append(("median", cells[len(cells) // 2]))
    for bucket, cell in picks:
        try:
            result = verifier.verify(
                origin="TLV", destination=code,
                depart_date=cell["depart"], return_date=cell["ret"],
                adults=2, children=3, currency="ils",
            )
        except ProviderError as exc:
            print(f"{code:5} {bucket:9} {cell['depart']+' -> '+cell['ret']:>24} "
                  f"{cell['estimate']:>9,.0f} {'-':>9} {str(exc)[:22]:>8}")
            continue
        est, live = cell["estimate"], result["total"]
        pct = 100 * (live - est) / est
        buckets[bucket].append(pct)
        print(f"{code:5} {bucket:9} {cell['depart']+' -> '+cell['ret']:>24} "
              f"{est:>9,.0f} {live:>9,.0f} {pct:>+7.0f}%")

print("-" * 72)
for name, values in buckets.items():
    if values:
        print(f"{name:9} n={len(values)}  mean {statistics.mean(values):+.0f}%  "
              f"median {statistics.median(values):+.0f}%  "
              f"range {min(values):+.0f}% to {max(values):+.0f}%")
