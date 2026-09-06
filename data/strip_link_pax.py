"""Remove passenger counts from cached booking links.

The cells cache is keyed by route/dates/currency with no passenger counts, so a link with
?adults=2&children=0 baked in gets served unchanged to a 2-adult-3-children search and
silently drops the children. The counts are now appended at serialisation time instead.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import cache  # noqa: E402

conn = cache.connect()
before = conn.execute(
    "SELECT COUNT(*) c FROM cells WHERE link LIKE '%adults=%'").fetchone()["c"]
print(f"cached links carrying a passenger query: {before}")

conn.execute(
    "UPDATE cells SET link = substr(link, 1, instr(link, '?') - 1) "
    "WHERE link LIKE '%kiwi.com%' AND instr(link, '?') > 0"
)
conn.commit()

after = conn.execute(
    "SELECT COUNT(*) c FROM cells WHERE link LIKE '%adults=%'").fetchone()["c"]
print(f"after stripping: {after}")

for r in conn.execute("SELECT link FROM cells WHERE link LIKE '%kiwi.com%' LIMIT 3"):
    print("  ", r["link"])
