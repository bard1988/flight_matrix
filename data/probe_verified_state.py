"""What did the auto cross-check actually store?"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import cache  # noqa: E402

conn = cache.connect()
print("verified rows by destination:")
for r in conn.execute(
    "SELECT destination, COUNT(*) n, SUM(total IS NULL) errs, MIN(total) mn "
    "FROM verified GROUP BY destination ORDER BY n DESC"
):
    print(f"  {r['destination']:5} rows={r['n']:4} failed={r['errs']:4} min={r['mn']}")

print("\nmost recent failures:")
for r in conn.execute(
    "SELECT destination, depart_date, return_date, error FROM verified "
    "WHERE error IS NOT NULL ORDER BY fetched_at DESC LIMIT 6"
):
    print(f"  {r['destination']} {r['depart_date']}->{r['return_date']}: {str(r['error'])[:95]}")

print("\nmost recent successes:")
for r in conn.execute(
    "SELECT destination, depart_date, return_date, total, airline FROM verified "
    "WHERE total IS NOT NULL ORDER BY fetched_at DESC LIMIT 6"
):
    print(f"  {r['destination']} {r['depart_date']}->{r['return_date']}: "
          f"{r['total']:,.0f} {r['airline']}")
