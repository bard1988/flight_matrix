"""Measure real grid coverage per source, and for the union, across several destinations.

This answers the plan's coverage question with real numbers instead of a guess.

    py -3 data/coverage.py [YYYY-MM-DD depart] [YYYY-MM-DD return] [DEST,DEST,...]
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import config  # noqa: E402
from models import parse_date, window  # noqa: E402

DEPART = sys.argv[1] if len(sys.argv) > 1 else "2026-12-10"
RETURN = sys.argv[2] if len(sys.argv) > 2 else "2026-12-17"
DESTS = (sys.argv[3].split(",") if len(sys.argv) > 3 else ["LCA", "ATH", "ROM", "MIL", "PRG", "BUD"])
ORIGIN = "TLV"
MONTH = DEPART[:7]

depart_dates = window(parse_date(DEPART), config.WINDOW_DAYS)
return_dates = window(parse_date(RETURN), config.WINDOW_DAYS)
LO_D, HI_D = depart_dates[0].isoformat(), depart_dates[-1].isoformat()
LO_R, HI_R = return_dates[0].isoformat(), return_dates[-1].isoformat()
VALID = sum(1 for d in depart_dates for r in return_dates if r >= d)

client = httpx.Client(timeout=30.0, verify=config.CA_BUNDLE)


def fetch(path: str, params: dict) -> list[dict]:
    try:
        r = client.get(
            f"{config.TRAVELPAYOUTS_HOST}{path}",
            params={k: v for k, v in params.items() if v is not None},
            headers={"X-Access-Token": config.TRAVELPAYOUTS_TOKEN},
        )
        if r.status_code != 200:
            return []
        payload = r.json()
        data = payload.get("data") if isinstance(payload, dict) else payload
        if isinstance(data, dict):
            rows = []
            for v in data.values():
                rows.extend(v if isinstance(v, list) else [v])
            return rows
        return list(data or [])
    except Exception:
        return []


def pairs_of(rows: list[dict]) -> set[tuple[str, str]]:
    out = set()
    for row in rows:
        d = str(row.get("departure_at") or row.get("depart_date") or "")[:10]
        rt = str(row.get("return_at") or row.get("return_date") or "")[:10]
        if d and rt and LO_D <= d <= HI_D and LO_R <= rt <= HI_R and rt >= d:
            out.add((d, rt))
    return out


SOURCES = {
    "latest": lambda dest: fetch("/v2/prices/latest", {
        "origin": ORIGIN, "destination": dest, "currency": "ils", "period_type": "month",
        "beginning_of_period": MONTH + "-01", "limit": 1000, "one_way": "false",
        "show_to_affiliates": "false"}),
    "prices_for_dates": lambda dest: fetch("/aviasales/v3/prices_for_dates", {
        "origin": ORIGIN, "destination": dest, "currency": "ils", "departure_at": MONTH,
        "one_way": "false", "limit": 1000, "sorting": "price", "market": "il"}),
    "calendar": lambda dest: fetch("/v1/prices/calendar", {
        "origin": ORIGIN, "destination": dest, "currency": "ils", "depart_date": MONTH,
        "return_date": MONTH, "calendar_type": "departure_date"}),
    "cheap": lambda dest: fetch("/v1/prices/cheap", {
        "origin": ORIGIN, "destination": dest, "currency": "ils",
        "depart_date": MONTH, "return_date": MONTH}),
}

print(f"window depart {LO_D}..{HI_D}  return {LO_R}..{HI_R}   {VALID} valid cells\n")
header = f"{'dest':6}" + "".join(f"{name:>18}" for name in SOURCES) + f"{'UNION':>12}"
print(header)
print("-" * len(header))

totals = defaultdict(set)
union_pct = []
for dest in DESTS:
    row = f"{dest:6}"
    union: set[tuple[str, str]] = set()
    for name, fn in SOURCES.items():
        p = pairs_of(fn(dest))
        union |= p
        row += f"{len(p):>10} ({100*len(p)/VALID:>3.0f}%)"
    row += f"{len(union):>6} ({100*len(union)/VALID:>3.0f}%)"
    union_pct.append(100 * len(union) / VALID)
    print(row)

print(f"\nmean union coverage: {sum(union_pct)/len(union_pct):.1f}% of {VALID} valid cells")
client.close()
