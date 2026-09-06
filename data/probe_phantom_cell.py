"""Why does the calendar price a date pair that a full search cannot fill?

Checks the exact cell from the report (CTA, Sun 8 Aug -> Fri 20 Aug 2027) both with and
without the depart-hours filter, to separate "the calendar ignores a filter the details
search applies" from "the calendar is simply advertising a trip that no longer exists".
"""
import sys
import pathlib
from datetime import timedelta

sys.path.insert(0, str(pathlib.Path("backend").resolve()))

from models import SearchRequest, parse_date
from providers.kiwi import KiwiProvider

DEST = (sys.argv[1] if len(sys.argv) > 1 else "CTA").upper()
DEP, RET = (sys.argv[2] if len(sys.argv) > 2 else "2027-08-08"), \
           (sys.argv[3] if len(sys.argv) > 3 else "2027-08-20")

prov = KiwiProvider()
nights = (parse_date(RET) - parse_date(DEP)).days
print(f"{DEST}  {DEP} -> {RET}  ({nights} nights)\n")

for label, hours in (("no time filter", None), ("depart 11:00-23:00", (11, 23))):
    req = SearchRequest(origin="TLV", depart_date=DEP, return_date=RET,
                        adults=2, children=0, currency="ils", depart_hours=hours)
    dd = [parse_date(DEP) + timedelta(days=i) for i in (-1, 0, 1)]
    rd = [d + timedelta(days=nights) for d in dd]

    cal = "-"
    try:
        m = prov.fill_matrix(req, DEST, dd, rd)
        cell = m.cells.get((DEP, RET))
        cal = f"{cell.price:,.0f}" if cell else "no cell"
    except Exception as exc:
        cal = f"{type(exc).__name__}: {exc}"

    det = "-"
    try:
        info = prov.itinerary_details(req, DEST, DEP, RET)
        out = info.get("outbound") or {}
        det = f"{info['price']:,.0f}  (outbound departs {out.get('departs')})"
    except Exception as exc:
        det = f"{type(exc).__name__}: {exc}"

    print(f"{label:<22} calendar: {cal:<14} details: {det}")

# What the calendar thinks the neighbouring nights cost, to show whether the whole
# diagonal is phantom or just this pair.
print("\nSame departure, other return dates (calendar vs full search):")
req = SearchRequest(origin="TLV", depart_date=DEP, return_date=RET,
                    adults=2, children=0, currency="ils")
for extra in (-2, -1, 0, 1, 2):
    ret = (parse_date(RET) + timedelta(days=extra)).isoformat()
    n = (parse_date(ret) - parse_date(DEP)).days
    dd = [parse_date(DEP) + timedelta(days=i) for i in (-1, 0, 1)]
    rd = [d + timedelta(days=n) for d in dd]
    try:
        cell = prov.fill_matrix(req, DEST, dd, rd).cells.get((DEP, ret))
        cal = f"{cell.price:,.0f}" if cell else "no cell"
    except Exception as exc:
        cal = f"{type(exc).__name__}"
    try:
        det = f"{prov.itinerary_details(req, DEST, DEP, ret)['price']:,.0f}"
    except Exception as exc:
        det = type(exc).__name__
    print(f"  {DEP} -> {ret}  ({n:>2}n)  calendar {cal:>10}   details {det:>22}", flush=True)
