"""Does cached coverage depend on how far ahead the travel window is?

The first coverage run used dates ~3 months out and got 13%. Cached rows come from real
user searches, so near-term windows should be denser. Measure it.

    py -3 data/coverage_horizon.py
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import config  # noqa: E402
from models import window  # noqa: E402

ORIGIN = "TLV"
DESTS = ["LCA", "ATH", "ROM", "MIL", "PRG", "BUD", "BCN", "VIE"]
TODAY = date.today()
HORIZONS = [14, 30, 45, 60, 90, 150]

client = httpx.Client(timeout=30.0, verify=config.CA_BUNDLE)


def latest_rows(dest: str, month_start: str) -> list[dict]:
    try:
        r = client.get(
            f"{config.TRAVELPAYOUTS_HOST}/v2/prices/latest",
            params={"origin": ORIGIN, "destination": dest, "currency": "ils",
                    "period_type": "month", "beginning_of_period": month_start,
                    "limit": 1000, "one_way": "false", "show_to_affiliates": "false"},
            headers={"X-Access-Token": config.TRAVELPAYOUTS_TOKEN},
        )
        return r.json().get("data", []) if r.status_code == 200 else []
    except Exception:
        return []


print(f"today {TODAY}   origin {ORIGIN}   {len(DESTS)} destinations\n")
print(f"{'days out':>9} {'depart':>12} {'valid':>6} {'mean cov':>9}   per-destination %")
print("-" * 78)

for days in HORIZONS:
    depart = TODAY + timedelta(days=days)
    ret = depart + timedelta(days=7)
    dd, rd = window(depart, config.WINDOW_DAYS), window(ret, config.WINDOW_DAYS)
    lo_d, hi_d = dd[0].isoformat(), dd[-1].isoformat()
    lo_r, hi_r = rd[0].isoformat(), rd[-1].isoformat()
    valid = sum(1 for d in dd for r in rd if r >= d)

    # The window can straddle two months, so pull both.
    months = sorted({dd[0].strftime("%Y-%m-01"), dd[-1].strftime("%Y-%m-01"),
                     rd[0].strftime("%Y-%m-01"), rd[-1].strftime("%Y-%m-01")})

    per_dest = []
    for dest in DESTS:
        pairs = set()
        for month in months:
            for row in latest_rows(dest, month):
                d = str(row.get("depart_date") or "")[:10]
                t = str(row.get("return_date") or "")[:10]
                if d and t and lo_d <= d <= hi_d and lo_r <= t <= hi_r and t >= d:
                    pairs.add((d, t))
        per_dest.append(100 * len(pairs) / valid)
    mean = sum(per_dest) / len(per_dest)
    detail = " ".join(f"{d}:{p:.0f}" for d, p in zip(DESTS, per_dest))
    print(f"{days:>9} {depart.isoformat():>12} {valid:>6} {mean:>8.1f}%   {detail}")

client.close()
