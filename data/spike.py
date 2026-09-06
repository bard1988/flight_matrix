"""Step-1 spike: which Travelpayouts endpoint can actually fill a departure x return grid?

The docs do not say whether /v3/prices_for_dates returns every (departure, return) pair or
collapses to the cheapest return per departure date. Hit it for real and look.

    py -3 data/spike.py [ORIGIN] [DEST] [YYYY-MM-DD depart] [YYYY-MM-DD return]
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import config  # noqa: E402
from models import SearchRequest, window, parse_date  # noqa: E402
from providers.travelpayouts import TravelpayoutsProvider  # noqa: E402

ORIGIN = sys.argv[1] if len(sys.argv) > 1 else "TLV"
DEST = sys.argv[2] if len(sys.argv) > 2 else "ATH"
DEPART = sys.argv[3] if len(sys.argv) > 3 else "2026-12-10"
RETURN = sys.argv[4] if len(sys.argv) > 4 else "2026-12-17"

request = SearchRequest(origin=ORIGIN, depart_date=DEPART, return_date=RETURN, currency="ils")
depart_dates = window(parse_date(DEPART), config.WINDOW_DAYS)
return_dates = window(parse_date(RETURN), config.WINDOW_DAYS)
provider = TravelpayoutsProvider()

lo_d, hi_d = depart_dates[0].isoformat(), depart_dates[-1].isoformat()
lo_r, hi_r = return_dates[0].isoformat(), return_dates[-1].isoformat()
print(f"route {ORIGIN}->{DEST}   depart window {lo_d}..{hi_d}   return window {lo_r}..{hi_r}\n")


def report(label: str, cells: list) -> dict:
    in_window = [
        c for c in cells
        if lo_d <= c.depart_date <= hi_d and lo_r <= c.return_date <= hi_r and c.return_date >= c.depart_date
    ]
    pairs = {(c.depart_date, c.return_date) for c in in_window}
    per_depart = defaultdict(set)
    for c in in_window:
        per_depart[c.depart_date].add(c.return_date)
    widest = max((len(v) for v in per_depart.values()), default=0)
    valid = sum(1 for d in depart_dates for r in return_dates if r >= d)
    print(f"{label}")
    print(f"   rows returned          {len(cells)}")
    print(f"   rows inside window     {len(in_window)}")
    print(f"   distinct (dep,ret)     {len(pairs)} of {valid} valid cells "
          f"({100 * len(pairs) / valid:.0f}% coverage)")
    print(f"   max returns per depart {widest}  -> {'FULL GRID' if widest > 1 else 'COLLAPSED, cannot fill a grid'}")
    if in_window:
        prices = sorted(c.price for c in in_window)
        print(f"   price range            {prices[0]:.0f} .. {prices[-1]:.0f} ILS (single ticket)")
        have_found = sum(1 for c in in_window if c.found_at)
        have_exp = sum(1 for c in in_window if c.expires_at)
        print(f"   found_at present       {have_found}/{len(in_window)}")
        print(f"   expires_at present     {have_exp}/{len(in_window)}")
        tr = Counter(c.transfers for c in in_window)
        print(f"   transfers histogram    {dict(sorted(tr.items(), key=lambda x: (x[0] is None, x[0])))}")
    print()
    return {"widest": widest, "pairs": len(pairs)}


# --- strategy A -------------------------------------------------------------
try:
    a = provider._fill_prices_for_dates(request, DEST, depart_dates, return_dates)
    res_a = report("A) /aviasales/v3/prices_for_dates", a)
    if a:
        print("   sample row:", json.dumps(a[0].__dict__, default=str)[:300], "\n")
except Exception as exc:
    res_a = {"widest": 0}
    print(f"A) prices_for_dates FAILED: {type(exc).__name__}: {exc}\n")

# --- strategy B -------------------------------------------------------------
try:
    b = provider._fill_week_matrix(request, DEST, depart_dates, return_dates)
    res_b = report("B) /v2/prices/week-matrix", b)
except Exception as exc:
    res_b = {"widest": 0}
    print(f"B) week-matrix FAILED: {type(exc).__name__}: {exc}\n")

# --- discovery --------------------------------------------------------------
try:
    found = provider.discover(request, depart_dates, return_dates)
    print(f"C) discovery (destination omitted): {len(found)} destinations in window")
    for code, price in found[:12]:
        print(f"     {code}  {price:.0f} ILS")
except Exception as exc:
    print(f"C) discovery FAILED: {type(exc).__name__}: {exc}")

print()
winner = "prices_for_dates" if res_a.get("widest", 0) > 1 else "week_matrix"
print(f"=> strategy that fills a grid here: {winner}")
