"""Is the CTA gap staleness, or a per-person vs party-total units mismatch?

If the calendar returns a PER-PERSON price while itinerary_details returns a party TOTAL,
the details/calendar ratio doubles when going from 1 adult to 2. If both are party totals,
the ratio is flat and the gap is genuine staleness.
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path("backend").resolve()))

from datetime import timedelta

from models import SearchRequest, parse_date
from providers.kiwi import KiwiProvider

PAIRS = [("2027-08-05", "2027-08-14"), ("2027-08-08", "2027-08-16")]
DESTS = [d.upper() for d in (sys.argv[1:] or ["CTA", "ATH"])]

prov = KiwiProvider()

for dest in DESTS:
    print(f"\n=== {dest} ===")
    print(f"{'dates':<26}{'adults':>7}{'calendar':>11}{'details':>10}{'ratio':>8}")
    for dep, ret in PAIRS:
        for adults in (1, 2):
            req = SearchRequest(origin="TLV", depart_date=dep, return_date=ret,
                                adults=adults, children=0, currency="ils")
            nights = (parse_date(ret) - parse_date(dep)).days
            cal = None
            try:
                dd = [parse_date(dep) + timedelta(days=i) for i in (-1, 0, 1)]
                rd = [d + timedelta(days=nights) for d in dd]
                m = prov.fill_matrix(req, dest, dd, rd)
                cell = m.cells.get((dep, ret))
                cal = cell.price if cell else None
            except Exception as exc:
                print(f"  calendar failed: {type(exc).__name__}: {exc}")
            det = None
            try:
                det = float(prov.itinerary_details(req, dest, dep, ret)["price"])
            except Exception as exc:
                print(f"  details failed: {type(exc).__name__}: {exc}")
            ratio = f"{det / cal:.2f}x" if cal and det else "-"
            print(f"{dep}->{ret:<12}{adults:>7}"
                  f"{(f'{cal:,.0f}' if cal else '-'):>11}"
                  f"{(f'{det:,.0f}' if det else '-'):>10}{ratio:>8}", flush=True)
