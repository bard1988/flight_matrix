"""Count cached Kiwi links still in the old IATA-code form."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import cache  # noqa: E402

conn = cache.connect()
good = bad = withpax = 0
sample = []
for r in conn.execute("SELECT rowid, link FROM cells WHERE link LIKE '%kiwi.com/en/search%'"):
    link = r["link"]
    if "?" in link:
        withpax += 1
    seg = link.split("/search/results/", 1)[1].split("/")[0]
    if len(seg) <= 3:
        bad += 1
        if len(sample) < 3:
            sample.append(link)
    else:
        good += 1

print(f"slug-form: {good}   code-form: {bad}   still carrying a query: {withpax}")
for s in sample:
    print("  ", s)
