"""A departure-time window must actually reprice the board, not just hide cells."""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import board  # noqa: E402
from models import SearchRequest  # noqa: E402

dep = date.today() + timedelta(days=45)
ret = dep + timedelta(days=7)


def run(label, **kw):
    req = SearchRequest(origin="TLV", depart_date=dep.isoformat(), return_date=ret.isoformat(),
                        adults=2, children=0, currency="ils", max_destinations=2,
                        destination_filter="ATH", **kw)
    out = []
    for ev in board.build(req):
        if ev["type"] == "destination":
            cov = ev["coverage"]
            out.append((ev["destination"], ev["best"]["estimate"], cov["populated"], cov["valid"]))
    print(f"  {label:32} " + "  ".join(
        f"{c}: best {b:,.0f} ({p}/{v} cells)" for c, b, p, v in out) or "no results")
    return out


print(f"TLV-ATH, depart ~{dep}, 2 adults\n")
run("no time window")
run("depart 06:00-11:00", depart_hours=(6, 11))
run("depart 17:00-23:00", depart_hours=(17, 23))
run("depart 06-11, return 17-23", depart_hours=(6, 11), return_hours=(17, 23))
