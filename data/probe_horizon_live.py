"""Does the LIVE source (Kiwi) actually thin out far ahead, the way the cache did?

The horizon warning was measured against Travelpayouts, a cache of other people's
searches. Kiwi runs a real search, so it should be limited by how far airlines have loaded
schedules (~11-12 months), not by search popularity. Measure it.

    py -3 data/probe_horizon_live.py [days_out ...]
"""
from __future__ import annotations

import sys
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import config  # noqa: E402
from models import SearchRequest, window  # noqa: E402
from providers.base import ProviderError  # noqa: E402
from providers.kiwi import KiwiProvider  # noqa: E402

HORIZONS = [int(a) for a in sys.argv[1:]] or [30, 90, 208, 300, 330, 360]
DEST = "ATH"

provider = KiwiProvider(on_status=lambda m: print(f"      ({m})"))
print(f"TLV, 2 adults + 3 children.  Grid = one destination ({DEST}), +-7 window.\n")
print(f"{'days out':>9} {'depart':>12} {'discovered':>11} {'grid cells':>11} {'cheapest':>10}")
print("-" * 60)

for days in HORIZONS:
    dep = date.today() + timedelta(days=days)
    ret = dep + timedelta(days=7)
    request = SearchRequest(origin="TLV", depart_date=dep.isoformat(),
                            return_date=ret.isoformat(), adults=2, children=3,
                            currency="ils", max_destinations=40)
    dd, rd = window(dep, config.WINDOW_DAYS), window(ret, config.WINDOW_DAYS)

    try:
        found = provider.discover(request, dd, rd)
    except ProviderError as exc:
        print(f"{days:>9} {dep.isoformat():>12}  discovery failed: {str(exc)[:40]}")
        continue

    try:
        matrix = provider.fill_matrix(request, DEST, dd, rd)
        best = matrix.best(request, config.CHILD_FACTOR)
        cells = len(matrix.cells)
        price = f"{best.price:,.0f}" if best else "-"
    except ProviderError as exc:
        cells, price = 0, f"err {str(exc)[:20]}"

    valid = sum(1 for d in dd for r in rd if r >= d)
    print(f"{days:>9} {dep.isoformat():>12} {len(found):>11} {cells:>6}/{valid:<4} {price:>10}")
    time.sleep(2)
