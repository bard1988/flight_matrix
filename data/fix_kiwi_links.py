"""Rewrite already-cached Kiwi booking links to the slug form that actually prefills.

Cells cached before the fix carry /results/tlv/vce/... which loads kiwi.com with empty
From/To. The correct URL is /results/tel-aviv-israel/venice-italy/... The link is derived
data, so it can be regenerated in place rather than throwing the cache away.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import cache  # noqa: E402
from providers.kiwi import KIWI_WEB, slug_for  # noqa: E402

conn = cache.connect()
rows = conn.execute(
    # Match on the LINK, not on `source`: rows written before the source column existed
    # have source NULL and were silently skipped by an earlier version of this script.
    "SELECT rowid, origin, destination, depart_date, return_date, link FROM cells "
    "WHERE link LIKE '%kiwi.com/en/search%'"
).fetchall()
print(f"{len(rows)} cached Kiwi cells")

fixed = skipped = already = 0
updates = []
def is_slug_link(link: str | None) -> bool:
    """True only if the ORIGIN path segment is a slug, not a 3-letter code.

    Checking merely for a hyphen matches the dates further along the path, which made an
    earlier version report every broken link as already correct.
    """
    if not link or "/search/results/" not in link:
        return False
    parts = link.split("/search/results/", 1)[1].split("/")
    return len(parts) >= 2 and len(parts[0]) > 3 and "-" in parts[0]


for r in rows:
    if is_slug_link(r["link"]):
        already += 1
        continue
    src, dst = slug_for(r["origin"]), slug_for(r["destination"])
    if not src or not dst:
        skipped += 1
        continue
    # No passenger query: the cache key has no passenger counts, so they are appended at
    # serialisation time from the live request instead.
    url = (f"{KIWI_WEB}/en/search/results/{src}/{dst}/"
           f"{r['depart_date']}/{r['return_date']}")
    updates.append((url, r["rowid"]))
    fixed += 1

if updates:
    conn.executemany("UPDATE cells SET link=? WHERE rowid=?", updates)
    conn.commit()

print(f"  rewritten: {fixed}")
print(f"  already correct: {already}")
print(f"  skipped (no slug known): {skipped}")

sample = conn.execute(
    "SELECT destination, link FROM cells WHERE source='kiwi' AND link IS NOT NULL LIMIT 3"
).fetchall()
for s in sample:
    print(f"  e.g. {s['destination']}: {s['link'][:110]}")
