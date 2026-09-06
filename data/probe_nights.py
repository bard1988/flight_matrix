"""Which trip lengths (diagonals) actually exist for a destination?

Each Kiwi calendar call fills one constant-nights diagonal, and the fill is capped at
KIWI_MAX_DIAGONALS. If the cap bites, whole diagonals are missing and the grid shows an
unfilled band rather than a full triangle.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import cache  # noqa: E402
import config  # noqa: E402

DEST = sys.argv[1] if len(sys.argv) > 1 else "FCO"
conn = cache.connect()

rows = conn.execute(
    "SELECT depart_date, return_date, source FROM cells WHERE destination=?", (DEST.upper(),)
).fetchall()
if not rows:
    print(f"no cells stored for {DEST}")
    raise SystemExit

by_nights: dict[int, int] = {}
for r in rows:
    n = (date.fromisoformat(r["return_date"]) - date.fromisoformat(r["depart_date"])).days
    by_nights[n] = by_nights.get(n, 0) + 1

print(f"{DEST}: {len(rows)} stored cells")
print(f"config: KIWI_MAX_DIAGONALS={config.KIWI_MAX_DIAGONALS} "
      f"KIWI_MAX_NIGHTS={config.KIWI_MAX_NIGHTS}\n")
print("nights : cells")
present = sorted(by_nights)
for n in range(0, max(present) + 1):
    bar = "#" * min(by_nights.get(n, 0), 45)
    print(f"{n:>6} : {by_nights.get(n, 0):>4} {bar}")

missing = [n for n in range(0, max(present) + 1) if n not in by_nights]
print(f"\npresent trip lengths : {present[0]}..{present[-1]} ({len(present)} distinct)")
print(f"missing in that span : {missing}")
