"""Does a widened grid now fill its whole valid triangle?

Reports how many of the geometrically valid (departure <= return) cells came back, and
which trip lengths are still missing.
"""
from __future__ import annotations

import sys
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import config  # noqa: E402
from models import SearchRequest, window  # noqa: E402
from providers.kiwi import KiwiProvider  # noqa: E402

DEST = sys.argv[1] if len(sys.argv) > 1 else "FCO"
WINDOW = int(sys.argv[2]) if len(sys.argv) > 2 else 7
DAYS_OUT = int(sys.argv[3]) if len(sys.argv) > 3 else 40

dep = date.today() + timedelta(days=DAYS_OUT)
ret = dep + timedelta(days=7)
request = SearchRequest(origin="TLV", depart_date=dep.isoformat(), return_date=ret.isoformat(),
                        adults=2, children=0, currency="ils", window_days=WINDOW)
dd, rd = window(dep, WINDOW), window(ret, WINDOW)
valid_pairs = {(d, r) for d in dd for r in rd if r >= d}
valid_nights = sorted({(r - d).days for d, r in valid_pairs})

print(f"TLV-{DEST}, +-{WINDOW} window ({len(dd)}x{len(rd)}), departing ~{dep}")
print(f"  valid cells: {len(valid_pairs)}   valid trip lengths: "
      f"{valid_nights[0]}..{valid_nights[-1]} ({len(valid_nights)} diagonals)")
print(f"  config: MAX_DIAGONALS={config.KIWI_MAX_DIAGONALS or 'uncapped'} "
      f"NIGHTS_CEILING={config.KIWI_NIGHTS_CEILING}")

start = time.time()
matrix = KiwiProvider(on_status=lambda m: print(f"    ({m})")).fill_matrix(request, DEST, dd, rd)
elapsed = time.time() - start

got_nights = {}
for (d, r) in matrix.cells:
    n = (date.fromisoformat(r) - date.fromisoformat(d)).days
    got_nights[n] = got_nights.get(n, 0) + 1

pct = 100 * len(matrix.cells) / len(valid_pairs)
print(f"\n  filled {len(matrix.cells)}/{len(valid_pairs)} valid cells ({pct:.0f}%) in {elapsed:.0f}s")
missing = [n for n in valid_nights if n not in got_nights]
print(f"  diagonals fetched: {len(got_nights)} of {len(valid_nights)}")
print(f"  trip lengths with NO data: {missing if missing else 'none'}")
