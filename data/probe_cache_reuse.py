"""Is the board serving a stale, partially-filled grid from cache instead of refetching?

    py -3 data/probe_cache_reuse.py LCA 2026-12-03 2026-12-08 7
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import cache  # noqa: E402
import config  # noqa: E402
from models import SearchRequest, window  # noqa: E402

DEST = sys.argv[1] if len(sys.argv) > 1 else "LCA"
DEP = sys.argv[2] if len(sys.argv) > 2 else "2026-12-03"
RET = sys.argv[3] if len(sys.argv) > 3 else "2026-12-08"
W = int(sys.argv[4]) if len(sys.argv) > 4 else 7

request = SearchRequest(origin="TLV", depart_date=DEP, return_date=RET,
                        adults=2, children=0, currency="ils", window_days=W)
dd, rd = window(date.fromisoformat(DEP), W), window(date.fromisoformat(RET), W)
valid = sum(1 for d in dd for r in rd if r >= d)

print(f"{DEST}  depart {dd[0]}..{dd[-1]}   return {rd[0]}..{rd[-1]}")
print(f"  valid cells in window: {valid}")
print(f"  reuse threshold: CACHE_REUSE_MIN_CELLS={config.CACHE_REUSE_MIN_CELLS}, "
      f"max age {config.KIWI_CACHE_HOURS}h")

cached = cache.get_matrix("TLV", DEST, "ils", dd, rd,
                          max_age_hours=config.KIWI_CACHE_HOURS, source="kiwi")
print(f"\n  cached cells that WOULD be reused: {len(cached.cells)} "
      f"({100*len(cached.cells)/valid:.0f}% of valid)")
print(f"  -> reuse triggers? {len(cached.cells) >= config.CACHE_REUSE_MIN_CELLS}")

nights = {}
for (d, r) in cached.cells:
    n = (date.fromisoformat(r) - date.fromisoformat(d)).days
    nights[n] = nights.get(n, 0) + 1
have = sorted(nights)
want = sorted({(r - d).days for d in dd for r in rd if r >= d})
print(f"\n  trip lengths cached : {have}")
print(f"  trip lengths needed : {want[0]}..{want[-1]}")
print(f"  MISSING lengths     : {[n for n in want if n not in nights]}")

conn = cache.connect()
row = conn.execute(
    "SELECT MIN(fetched_at) a, MAX(fetched_at) b FROM cells WHERE destination=? AND source='kiwi'",
    (DEST.upper(),)).fetchone()
print(f"\n  cached rows fetched between {row['a']} and {row['b']}")
