"""Inspect one cell end to end: what the board stored vs what Google returned.

    py -3 data/probe_cell.py CTA 2026-12-10 2026-12-26
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import cache  # noqa: E402

DEST = sys.argv[1] if len(sys.argv) > 1 else "CTA"
DEP = sys.argv[2] if len(sys.argv) > 2 else "2026-12-10"
RET = sys.argv[3] if len(sys.argv) > 3 else "2026-12-26"

conn = cache.connect()

print(f"=== cells (board source) for {DEST} {DEP} -> {RET} ===")
rows = conn.execute(
    "SELECT * FROM cells WHERE destination=? AND depart_date=? AND return_date=?",
    (DEST.upper(), DEP, RET),
).fetchall()
for r in rows:
    print(f"  price={r['price']:,.2f} {r['currency']}  source={r['source']}  "
          f"is_total={r['is_total']}  airline={r['airline']}  transfers={r['transfers']}")
    print(f"  fetched_at={r['fetched_at']}  found_at={r['found_at']}  expires_at={r['expires_at']}")
if not rows:
    print("  (no stored board cell)")

print(f"\n=== verified (Google) for {DEST} {DEP} -> {RET} ===")
for r in conn.execute(
    "SELECT * FROM verified WHERE destination=? AND depart_date=? AND return_date=?",
    (DEST.upper(), DEP, RET),
):
    print(f"  adults={r['adults']} children={r['children']}  total={r['total']}  "
          f"airline={r['airline']}  stops={r['stops_out']}  fetched_at={r['fetched_at']}")
    if r["error"]:
        print(f"  error={r['error'][:90]}")

print(f"\n=== how {DEST} cells are priced generally ===")
for r in conn.execute(
    "SELECT source, is_total, COUNT(*) n, MIN(price) mn, AVG(price) av, MAX(price) mx "
    "FROM cells WHERE destination=? GROUP BY source, is_total", (DEST.upper(),)
):
    print(f"  source={r['source']} is_total={r['is_total']}: n={r['n']} "
          f"min={r['mn']:,.0f} avg={r['av']:,.0f} max={r['mx']:,.0f}")

print("\n=== neighbouring trip lengths from the same departure ===")
for r in conn.execute(
    "SELECT return_date, price, source, is_total FROM cells "
    "WHERE destination=? AND depart_date=? ORDER BY return_date", (DEST.upper(), DEP)
):
    nights = (cache.date.fromisoformat(r["return_date"]) - cache.date.fromisoformat(DEP)).days
    mark = "  <-- this cell" if r["return_date"] == RET else ""
    print(f"  {r['return_date']} ({nights:>2}n) {r['price']:>9,.0f}  {r['source']}{mark}")
