"""Which airlines does the existing Google Flights fill already return?

Answers whether adding direct airline feeds (Wizz, El Al, Arkia, Israir) would add
carriers we do not already see, or merely duplicate them.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import cache  # noqa: E402

conn = cache.connect()
rows = conn.execute(
    "SELECT airline, COUNT(*) n, MIN(total) mn, MAX(total) mx, "
    "       COUNT(DISTINCT destination) d "
    "FROM verified WHERE total IS NOT NULL GROUP BY airline ORDER BY n DESC"
).fetchall()

print(f"{'airline':32} {'cells':>6} {'dests':>6} {'min':>8} {'max':>8}")
print("-" * 64)
for r in rows:
    print(f"{(r['airline'] or '?')[:32]:32} {r['n']:>6} {r['d']:>6} {r['mn']:>8.0f} {r['mx']:>8.0f}")

total = conn.execute("SELECT COUNT(*) c FROM verified WHERE total IS NOT NULL").fetchone()["c"]
print(f"\n{total} verified cells, {len(rows)} distinct airline strings")

# Which carriers appear as the CHEAPEST option for a cell? That is what the board shows.
print("\ncheapest-per-cell winners:")
win = conn.execute(
    "SELECT airline, COUNT(*) n FROM verified v WHERE total IS NOT NULL "
    "AND total = (SELECT MIN(total) FROM verified w WHERE w.destination=v.destination "
    "             AND w.depart_date=v.depart_date AND w.return_date=v.return_date "
    "             AND w.total IS NOT NULL) GROUP BY airline ORDER BY n DESC"
).fetchall()
for r in win:
    print(f"  {(r['airline'] or '?')[:32]:32} {r['n']:>5}")
