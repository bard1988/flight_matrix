"""Hit /api/details for a cell Google cannot price, and confirm times come back."""
from __future__ import annotations

import json
import sys
import urllib.request

PORT = sys.argv[1] if len(sys.argv) > 1 else "8712"

CASES = [
    ("LCA", "2027-08-16", "2027-08-26", 2, 3),   # 344 days out - no Google data
    ("ATH", "2026-10-20", "2026-10-27", 2, 0),
]

for dest, dep, ret, adults, children in CASES:
    body = json.dumps({
        "origin": "TLV", "destination": dest, "depart_date": dep, "return_date": ret,
        "adults": adults, "children": children, "currency": "ils",
    }).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}/api/details", data=body,
                                 headers={"Content-Type": "application/json"})
    d = json.load(urllib.request.urlopen(req))
    print(f"\n{dest} {dep} -> {ret} ({adults}a{children}c)")
    if d.get("error"):
        print("  error:", d["error"][:80])
        continue
    print(f"  price: {d.get('price'):,.0f}")
    for way in ("outbound", "inbound"):
        s = d.get(way) or {}
        departs = s.get("departs")
        arrives = s.get("arrives")
        print(f"  {way:9}: {departs} -> {arrives}   {s.get('duration')}   "
              f"{s.get('stops')} stops   {s.get('carriers')}")
