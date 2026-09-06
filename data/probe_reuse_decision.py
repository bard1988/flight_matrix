"""Does the board now refuse to reuse a half-filled cached grid, and refill it?"""
from __future__ import annotations

import sys
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import board  # noqa: E402
import cache  # noqa: E402
import config  # noqa: E402
from models import SearchRequest, window  # noqa: E402

DEST = sys.argv[1] if len(sys.argv) > 1 else "LCA"
DEP = sys.argv[2] if len(sys.argv) > 2 else "2026-12-03"
RET = sys.argv[3] if len(sys.argv) > 3 else "2026-12-08"

request = SearchRequest(origin="TLV", depart_date=DEP, return_date=RET,
                        adults=2, children=0, currency="ils", window_days=7,
                        max_destinations=1)
dd, rd = window(date.fromisoformat(DEP), 7), window(date.fromisoformat(RET), 7)
valid = sum(1 for d in dd for r in rd if r >= d)

before = cache.get_matrix("TLV", DEST, "ils", dd, rd,
                          max_age_hours=config.KIWI_CACHE_HOURS, source="kiwi")
frac = len(before.cells) / valid
print(f"cached before: {len(before.cells)}/{valid} = {frac:.0%}  "
      f"(reuse needs >= {config.CACHE_REUSE_MIN_FRACTION:.0%}) -> "
      f"{'REUSE' if frac >= config.CACHE_REUSE_MIN_FRACTION else 'REFETCH'}")

start = time.time()
payload = board.fill_one(request, DEST)
cov = payload["coverage"]
print(f"\nafter fill_one: {cov['populated']}/{cov['valid']} "
      f"({100*cov['populated']/cov['valid']:.0f}%) in {time.time()-start:.0f}s")

after = cache.get_matrix("TLV", DEST, "ils", dd, rd,
                         max_age_hours=config.KIWI_CACHE_HOURS, source="kiwi")
nights = {}
for (d, r) in after.cells:
    n = (date.fromisoformat(r) - date.fromisoformat(d)).days
    nights[n] = nights.get(n, 0) + 1
want = sorted({(r - d).days for d in dd for r in rd if r >= d})
print(f"  trip lengths now: {sorted(nights)}")
print(f"  still missing   : {[n for n in want if n not in nights]}")
