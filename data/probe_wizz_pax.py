"""What do Wizz timetable prices actually represent: per person, or the whole party?

Critical before using them: if the price ignores passenger counts it is a per-person fare
and must be multiplied, and if it does not it is a party total. Compare identical queries
at different passenger counts.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import config  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept": "application/json, text/plain, */*", "Content-Type": "application/json",
      "Origin": "https://wizzair.com", "Referer": "https://wizzair.com/"}
client = httpx.Client(timeout=30.0, verify=config.CA_BUNDLE, headers=UA, follow_redirects=True)

home = client.get("https://wizzair.com/")
version = (re.search(r"be\.wizzair\.com/([\d.]+)/Api", home.text) or [None, "29.15.1"])[1]
api = f"https://be.wizzair.com/{version}/Api"

frm = date.today() + timedelta(days=16)
to = frm + timedelta(days=10)


def timetable(adults: int, children: int) -> dict[str, float]:
    body = {
        "flightList": [
            {"departureStation": "TLV", "arrivalStation": "BUD",
             "from": frm.isoformat(), "to": to.isoformat()},
        ],
        "priceType": "regular",
        "adultCount": adults, "childCount": children, "infantCount": 0,
    }
    import time

    time.sleep(2.0)  # Wizz rate-limits; space the calls out
    r = client.post(f"{api}/search/timetable", content=json.dumps(body))
    print(f"    [adults={adults} children={children}] HTTP {r.status_code} {len(r.content)}b"
          + ("" if r.status_code == 200 else f"  {r.text[:140]}"))
    if r.status_code != 200:
        return {}
    out = {}
    for f in r.json().get("outboundFlights", []):
        p = f.get("price") or {}
        if p.get("amount"):
            out[str(f.get("departureDate"))[:10]] = (p["amount"], p.get("currencyCode"))
    return out


combos = [(1, 0), (2, 0), (2, 3)]
tables = {}
for a, c in combos:
    tables[(a, c)] = timetable(a, c)
    print(f"adults={a} children={c}: {len(tables[(a,c)])} dated prices")

dates = sorted(set.intersection(*[set(t) for t in tables.values()])) if all(tables.values()) else []
print(f"\n{'date':12} " + "  ".join(f"{a}a{c}c".rjust(12) for a, c in combos))
print("-" * 56)
for d in dates[:10]:
    row = f"{d:12} "
    for combo in combos:
        amt, cur = tables[combo][d]
        row += f"{amt:>9.2f} {cur}".rjust(14)
    print(row)

if dates:
    same = all(tables[combos[0]][d][0] == tables[combos[-1]][d][0] for d in dates)
    print(f"\nprices identical across passenger counts? {same}")
    print("=> " + ("PER PERSON (ignores pax; must multiply)" if same
                   else "scales with party size (already a total)"))

client.close()
