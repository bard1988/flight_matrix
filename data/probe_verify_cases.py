"""Verification must never surface a raw parser crash, and must return times when it works."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from providers.base import ProviderError  # noqa: E402
from providers.google_flights import GoogleFlightsProvider  # noqa: E402

CASES = [
    ("LCA", "2027-08-16", "2027-08-26", 2, 3),   # the one that raised JSONDecodeError
    ("ATH", "2026-10-20", "2026-10-27", 2, 0),
    ("LCA", "2026-10-02", "2026-10-13", 2, 3),
]

provider = GoogleFlightsProvider()
for dest, dep, ret, adults, children in CASES:
    label = f"{dest} {dep} {adults}a{children}c"
    try:
        r = provider.verify("TLV", dest, dep, ret, adults, children, "ils")
        total = r["total"]
        print(f"  {label:26} {total:>8,.0f}  departs {r.get('departs')}  arrives {r.get('arrives')}")
    except ProviderError as exc:
        print(f"  {label:26} {'-':>8}  {str(exc)[:80]}")
