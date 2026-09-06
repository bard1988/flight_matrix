"""Setting the filter BEFORE searching must restrict the search, not just the view."""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import board  # noqa: E402
from models import SearchRequest  # noqa: E402

dep = date.today() + timedelta(days=40)
ret = dep + timedelta(days=7)


def run(dest_filter: str, want: int = 6) -> None:
    req = SearchRequest(origin="TLV", depart_date=dep.isoformat(), return_date=ret.isoformat(),
                        adults=2, children=0, currency="ils", max_destinations=want,
                        destination_filter=dest_filter)
    print(f"\n=== filter {dest_filter!r} (want {want} destinations) ===")
    got = []
    for ev in board.build(req):
        if ev["type"] == "filter_applied":
            print(f"  discovery: {ev['matched']} of {ev['considered']} reachable matched")
        elif ev["type"] == "candidates":
            print(f"  candidates carried forward: {ev['count']}")
        elif ev["type"] == "destination":
            got.append(f"{ev['destination']}/{ev['city']}/{ev.get('country')}")
        elif ev["type"] == "done":
            print(f"  filled {ev['destinations']}: {got}")
            if ev.get("note"):
                print(f"  note: {ev['note'][:80]}")


run("")        # baseline: cheapest anywhere
run("IT")      # country code
run("greece")  # country name is not in our data - should match nothing
run("ATH")     # single IATA code
