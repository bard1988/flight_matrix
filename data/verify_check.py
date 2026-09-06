"""Live-verify a few real cells and compare against the cached estimate.

This is the number that says how far off the board's estimates actually are for a family.

    py -3 data/verify_check.py [days_out] [nights] [n_destinations]
"""
from __future__ import annotations

import sys
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import board  # noqa: E402
import config  # noqa: E402
from models import SearchRequest  # noqa: E402
from providers.base import ProviderError  # noqa: E402
from providers.google_flights import GoogleFlightsProvider  # noqa: E402

DAYS_OUT = int(sys.argv[1]) if len(sys.argv) > 1 else 21
NIGHTS = int(sys.argv[2]) if len(sys.argv) > 2 else 7
N_DEST = int(sys.argv[3]) if len(sys.argv) > 3 else 4

depart = date.today() + timedelta(days=DAYS_OUT)
ret = depart + timedelta(days=NIGHTS)
request = SearchRequest(
    origin="TLV", depart_date=depart.isoformat(), return_date=ret.isoformat(),
    adults=2, children=3, currency="ils", max_destinations=N_DEST,
)

print(f"TLV, 2 adults + 3 children, depart ~{depart}, return ~{ret}\n")
print("building board...")
targets = []
for event in board.build(request):
    if event["type"] == "destination" and event.get("best"):
        targets.append((event["destination"], event["city"], event["best"]))

print(f"{len(targets)} destinations. Verifying each one's cheapest cell live.\n")
print(f"{'dest':5} {'dates':>24} {'estimate':>10} {'live':>10} {'delta':>9}  detail")
print("-" * 92)

verifier = GoogleFlightsProvider()
deltas = []
for code, city, best in targets:
    start = time.time()
    try:
        result = verifier.verify(
            origin="TLV", destination=code,
            depart_date=best["depart"], return_date=best["ret"],
            adults=2, children=3, currency="ils",
        )
    except ProviderError as exc:
        print(f"{code:5} {best['depart']+' -> '+best['ret']:>24} {best['estimate']:>10,.0f} "
              f"{'-':>10} {'-':>9}  {str(exc)[:40]}")
        continue
    est, live = best["estimate"], result["total"]
    pct = 100 * (live - est) / est if est else 0
    deltas.append(pct)
    detail = f"{result.get('airline') or '?'}, {result.get('duration') or '?'}, {time.time()-start:.0f}s"
    print(f"{code:5} {best['depart']+' -> '+best['ret']:>24} {est:>10,.0f} {live:>10,.0f} "
          f"{pct:>+8.0f}%  {detail}")

print("-" * 92)
if deltas:
    print(f"live total vs estimate: mean {sum(deltas)/len(deltas):+.0f}%, "
          f"range {min(deltas):+.0f}% to {max(deltas):+.0f}%  (n={len(deltas)})")
    print(f"child factor in use: {config.CHILD_FACTOR}")
