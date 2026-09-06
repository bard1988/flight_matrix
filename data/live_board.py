"""Build a real board against the live API and print it as text.

    py -3 data/live_board.py [days_out] [nights] [max_destinations]
"""
from __future__ import annotations

import sys
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import board  # noqa: E402
from models import SearchRequest  # noqa: E402

DAYS_OUT = int(sys.argv[1]) if len(sys.argv) > 1 else 21
NIGHTS = int(sys.argv[2]) if len(sys.argv) > 2 else 7
MAX_DEST = int(sys.argv[3]) if len(sys.argv) > 3 else 8

depart = date.today() + timedelta(days=DAYS_OUT)
ret = depart + timedelta(days=NIGHTS)
request = SearchRequest(
    origin="TLV", depart_date=depart.isoformat(), return_date=ret.isoformat(),
    adults=2, children=3, currency="ils", max_destinations=MAX_DEST,
)

print(f"TLV, depart ~{depart} ({DAYS_OUT} days out), return ~{ret}, 2 adults + 3 children\n")
start = time.time()
rows = []

for event in board.build(request):
    kind = event["type"]
    if kind == "meta":
        print(f"depart window {event['depart_dates'][0]} .. {event['depart_dates'][-1]}")
        print(f"return window {event['return_dates'][0]} .. {event['return_dates'][-1]}\n")
    elif kind == "candidates":
        print(f"{event['count']} candidates (want {event['target']} filled)\n")
        print(f"{'dest':5} {'city':18} {'best est':>10} {'dates':>25} {'coverage':>12}")
        print("-" * 76)
    elif kind == "destination":
        best, cov = event["best"], event["coverage"]
        pct = 100 * cov["populated"] / cov["valid"]
        dates = f"{best['depart']} -> {best['ret']}"
        print(f"{event['destination']:5} {event['city'][:18]:18} {best['estimate']:>10,.0f} {dates:>25} "
              f"{cov['populated']:>4}/{cov['valid']} ({pct:>3.0f}%)")
        rows.append(pct)
    elif kind == "destination_error":
        print(f"{event['destination']:5} ERROR {event['message'][:60]}")
    elif kind == "done":
        print("-" * 76)
        print(f"{event['destinations']} filled, {event['empty']} empty, strategy={event['strategy']}")
        if rows:
            print(f"mean coverage {sum(rows)/len(rows):.0f}%")
        print(f"note: {event['note']}")
    elif kind == "error":
        print(f"ERROR: {event['message']}")

print(f"\nelapsed {time.time() - start:.1f}s")
