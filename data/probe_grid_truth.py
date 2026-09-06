"""Audit a filled grid: does each cell's price survive a real search for that exact pair?

Samples cells from a freshly built matrix and re-prices each with a full search. Reports
the error distribution and, most importantly, how many cells are phantom - priced by the
board but unbookable.
"""
import random
import sys
import pathlib
from datetime import timedelta

sys.path.insert(0, str(pathlib.Path("backend").resolve()))

from models import SearchRequest, parse_date, window
from providers.base import NoItinerariesError
from providers.kiwi import KiwiProvider

DEST = (sys.argv[1] if len(sys.argv) > 1 else "CTA").upper()
DEP = sys.argv[2] if len(sys.argv) > 2 else "2027-08-05"
RET = sys.argv[3] if len(sys.argv) > 3 else "2027-08-23"
SAMPLE = int(sys.argv[4]) if len(sys.argv) > 4 else 12

req = SearchRequest(origin="TLV", depart_date=DEP, return_date=RET,
                    adults=2, children=0, currency="ils")
dd, rd = req.depart_window(), req.return_window()

prov = KiwiProvider()
matrix = prov.fill_matrix(req, DEST, dd, rd)
valid = sum(1 for d in dd for r in rd if r >= d)
print(f"{DEST}: {len(matrix.cells)}/{valid} cells filled "
      f"({len(dd)} departures x {len(rd)} returns)\n")

cells = sorted(matrix.cells.values(), key=lambda c: (c.depart_date, c.return_date))
random.seed(7)
sample = random.sample(cells, min(SAMPLE, len(cells)))
sample.sort(key=lambda c: c.price)

print(f"{'depart':<12}{'return':<12}{'nights':>7}{'board':>9}{'real':>10}{'err':>9}")
errors, phantom = [], 0
for c in sample:
    try:
        real = float(prov.itinerary_details(req, DEST, c.depart_date, c.return_date)["price"])
        err = (real - c.price) / c.price * 100
        errors.append(abs(err))
        shown = f"{real:,.0f}"
        errtxt = f"{err:+.1f}%"
    except NoItinerariesError:
        phantom += 1
        shown, errtxt = "NONE", "PHANTOM"
    except Exception as exc:
        shown, errtxt = type(exc).__name__, "-"
    print(f"{c.depart_date:<12}{c.return_date:<12}{c.nights:>7}{c.price:>9,.0f}"
          f"{shown:>10}{errtxt:>9}", flush=True)

if errors:
    errors.sort()
    print(f"\nmedian error {errors[len(errors) // 2]:.1f}%, worst {errors[-1]:.1f}%, "
          f"within 5%: {sum(1 for e in errors if e <= 5)}/{len(errors)}")
print(f"phantom cells: {phantom}/{len(sample)}")
