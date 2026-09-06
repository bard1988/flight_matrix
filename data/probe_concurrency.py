"""Can Google Flights lookups be run in parallel without getting blocked?

If yes, bulk-filling a whole 197-cell grid becomes practical (minutes, not an hour) and
the coverage problem is solved with real family prices and no new API key.

Deliberately modest: a small number of cells at low concurrency.

    py -3 data/probe_concurrency.py [n_cells] [workers]
"""
from __future__ import annotations

import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from providers.base import ProviderError  # noqa: E402
from providers.google_flights import GoogleFlightsProvider  # noqa: E402

N = int(sys.argv[1]) if len(sys.argv) > 1 else 12
WORKERS = int(sys.argv[2]) if len(sys.argv) > 2 else 4

base = date.today() + timedelta(days=25)
pairs = []
for i in range(N):
    dep = base + timedelta(days=i % 5)
    ret = dep + timedelta(days=6 + (i // 5))
    pairs.append((dep.isoformat(), ret.isoformat()))

provider = GoogleFlightsProvider()


def one(pair):
    dep, ret = pair
    start = time.time()
    try:
        result = provider.verify("TLV", "ATH", dep, ret, 2, 3, "ils")
        return ("ok", result["total"], time.time() - start, None)
    except ProviderError as exc:
        return ("err", None, time.time() - start, str(exc)[:60])


for workers in (1, WORKERS):
    subset = pairs[: max(4, N // 2)] if workers == 1 else pairs
    print(f"\n--- {len(subset)} lookups at concurrency {workers} ---")
    start = time.time()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(one, subset))
    elapsed = time.time() - start
    ok = [r for r in results if r[0] == "ok"]
    errs = [r for r in results if r[0] == "err"]
    print(f"  {len(ok)} ok, {len(errs)} failed in {elapsed:.1f}s "
          f"({elapsed / len(subset):.2f}s per lookup wall-clock)")
    if ok:
        lat = [r[2] for r in ok]
        print(f"  latency per call: min {min(lat):.1f}s  max {max(lat):.1f}s")
        print(f"  sample totals: {[round(r[1]) for r in ok[:6]]}")
    for r in errs[:3]:
        print(f"  error: {r[3]}")
    if workers == 1:
        per_cell = elapsed / len(subset)
        print(f"  => a full 197-cell grid at this rate: {197 * per_cell / 60:.1f} min")
    else:
        per_cell = elapsed / len(subset)
        print(f"  => a full 197-cell grid at this rate: {197 * per_cell / 60:.1f} min")
