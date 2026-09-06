"""Find a Travelpayouts call that actually yields many (departure, return) pairs.

The first spike showed both candidate strategies collapsing to ~1 pair. Try the parameter
space directly and count distinct date pairs per call.

    py -3 data/probe_api.py [ORIGIN] [DEST] [YYYY-MM-DD depart] [YYYY-MM-DD return]
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import config  # noqa: E402

ORIGIN = sys.argv[1] if len(sys.argv) > 1 else "TLV"
DEST = sys.argv[2] if len(sys.argv) > 2 else "ATH"
DEPART = sys.argv[3] if len(sys.argv) > 3 else "2026-12-10"
RETURN = sys.argv[4] if len(sys.argv) > 4 else "2026-12-17"
MONTH = DEPART[:7]

client = httpx.Client(timeout=30.0, verify=config.CA_BUNDLE)


def call(path: str, params: dict, note: str = "") -> None:
    query = {k: v for k, v in params.items() if v is not None}
    try:
        r = client.get(
            f"{config.TRAVELPAYOUTS_HOST}{path}",
            params=query,
            headers={"X-Access-Token": config.TRAVELPAYOUTS_TOKEN},
        )
    except Exception as exc:
        print(f"  !! {path} {query} -> {type(exc).__name__}: {exc}")
        return
    label = " ".join(f"{k}={v}" for k, v in query.items() if k not in ("currency", "market", "token"))
    if r.status_code != 200:
        print(f"  [{r.status_code}] {path}  {label}")
        return
    payload = r.json()
    data = payload.get("data") if isinstance(payload, dict) else payload
    if isinstance(data, dict):
        rows = []
        for v in data.values():
            rows.extend(v if isinstance(v, list) else [v])
    else:
        rows = list(data or [])

    pairs = set()
    per_depart = defaultdict(set)
    for row in rows:
        d = str(row.get("departure_at") or row.get("depart_date") or "")[:10]
        rt = str(row.get("return_at") or row.get("return_date") or "")[:10]
        if d and rt:
            pairs.add((d, rt))
            per_depart[d].add(rt)
    widest = max((len(v) for v in per_depart.values()), default=0)
    flag = "  <== GRID" if widest > 1 and len(pairs) > 10 else ""
    print(f"  rows={len(rows):4}  pairs={len(pairs):4}  departs={len(per_depart):3}  max_ret/dep={widest:3}  {path} {label}{note}{flag}")
    if rows and not pairs:
        print(f"        keys: {sorted(rows[0].keys())}")


print(f"=== {ORIGIN} -> {DEST}, depart {DEPART}, return {RETURN} ===\n")
base = {"origin": ORIGIN, "destination": DEST, "currency": "ils", "market": "il"}

print("/aviasales/v3/prices_for_dates")
for params in (
    {"departure_at": MONTH, "one_way": "false", "limit": 1000, "sorting": "price"},
    {"departure_at": MONTH, "return_at": MONTH, "one_way": "false", "limit": 1000, "sorting": "price"},
    {"departure_at": DEPART, "return_at": MONTH, "one_way": "false", "limit": 1000, "sorting": "price"},
    {"departure_at": DEPART, "return_at": RETURN, "one_way": "false", "limit": 1000, "sorting": "price"},
    {"departure_at": MONTH, "return_at": MONTH, "one_way": "false", "limit": 1000, "group_by": "departure_at"},
    {"departure_at": MONTH, "return_at": MONTH, "one_way": "false", "limit": 1000, "unique": "false"},
):
    call("/aviasales/v3/prices_for_dates", {**base, **params})

print("\n/aviasales/v3/grouped_prices")
for params in (
    {"departure_at": MONTH, "group_by": "departure_at", "one_way": "false", "currency": "ils"},
    {"departure_at": MONTH, "return_at": MONTH, "group_by": "departure_at", "one_way": "false"},
):
    call("/aviasales/v3/grouped_prices", {**base, **params})

print("\nv2 / v1 endpoints")
call("/v2/prices/week-matrix", {**base, "depart_date": DEPART, "return_date": RETURN, "show_to_affiliates": "false"})
call("/v2/prices/month-matrix", {**base, "month": MONTH + "-01", "show_to_affiliates": "false"})
call("/v2/prices/latest", {**base, "period_type": "month", "beginning_of_period": MONTH + "-01",
                           "limit": 1000, "show_to_affiliates": "false", "one_way": "false"})
call("/v1/prices/cheap", {**base, "depart_date": MONTH, "return_date": MONTH})
call("/v1/prices/calendar", {**base, "depart_date": MONTH, "return_date": MONTH, "calendar_type": "departure_date"})
call("/v1/prices/calendar", {**base, "depart_date": MONTH, "return_date": MONTH, "calendar_type": "return_date"})
call("/v2/prices/nearest-places-matrix", {**base, "depart_date": DEPART, "return_date": RETURN,
                                          "flexibility": 7, "limit": 20, "show_to_affiliates": "false"})

client.close()
