"""Offline proof of the estimate-first + upgrade flow. No network.

Doubles for both providers, so this asserts the ORDER and the wiring: cheap source paints
every card, expensive source then overlays real party totals and streams them as it goes.
"""
import sys
from datetime import date, timedelta

sys.path.insert(0, r"C:\Users\bdubovski155809\tools\flight-matrix\backend")
import config

config.CHECK_HEADLINE = False
config.KIWI_CACHE_HOURS = 0.0
config.TRAVELPAYOUTS_TOKEN = "fake-token-for-test"   # so _base_provider engages

import board
from models import Cell, DestinationMatrix, SearchRequest


def _grid(origin, dest, dd, rd, nights, price, source, is_total):
    m = DestinationMatrix(origin=origin.upper(), destination=dest.upper())
    for r in rd:
        for d in dd:
            if nights[0] <= (r - d).days <= nights[-1]:
                m.add(Cell(depart_date=d.isoformat(), return_date=r.isoformat(),
                           price=price, currency="ils", source=source, is_total=is_total))
    return m


class FakeTP:
    """Cheap source: every destination, thin coverage, single-ticket estimates."""
    name = "travelpayouts"
    strategy = "latest"

    def __init__(self):
        self.fills = []

    def discover(self, request, dd, rd):
        return [("ATH", 500.0), ("CTA", 600.0), ("VCE", 700.0)]

    def fill_matrix(self, request, destination, dd, rd):
        self.fills.append(destination)
        # thin: only the shortest trip length
        n = request.nights_span()[:1]
        return _grid(request.origin, destination, dd, rd, n, 900.0, "travelpayouts", False)


class FakeKiwi:
    """Expensive source: full coverage, real party totals, streams per column."""
    name = "kiwi"
    strategy = "kiwi-calendar"
    rate_limited = False

    def __init__(self):
        self.on_status = None
        self.on_cells = None
        self.fills = []

    def fill_matrix(self, request, destination, dd, rd):
        self.fills.append(destination)
        m = _grid(request.origin, destination, dd, rd, request.nights_span(),
                  1500.0, "kiwi", True)
        if self.on_cells:                       # stream it, one column at a time
            by_ret = {}
            for cell in m.cells.values():
                by_ret.setdefault(cell.return_date, []).append(cell)
            for cells in by_ret.values():
                self.on_cells(destination, cells)
        return m


start = date.today() + timedelta(days=30)
req = SearchRequest(origin="TLV", depart_date=start.isoformat(),
                    return_date=(start + timedelta(days=14)).isoformat(),
                    adults=2, children=0, currency="ils", max_destinations=3,
                    nights_min=5, nights_max=7)

tp, kiwi = FakeTP(), FakeKiwi()
board.TravelpayoutsProvider = lambda *a, **k: tp        # what _base_provider builds
streamed = []
kiwi.on_cells = lambda d, c: streamed.append((d, len(c)))

order, cards, statuses, done = [], [], [], None
for ev in board.build(req, provider=kiwi):
    k = ev.get("type")
    if k == "destination" and not ev.get("preview"):
        best = ev.get("best") or {}
        cards.append((ev["destination"], best.get("source"), len(ev.get("cells") or [])))
        order.append("card:" + ev["destination"])
    elif k == "provider_status":
        statuses.append(ev["message"])
        order.append("status")
    elif k == "done":
        done = ev

print("cards emitted (destination, source, cells):")
for c in cards:
    print("   ", c)
print("\ncheap source filled :", tp.fills)
print("expensive source ran:", kiwi.fills)
print("columns streamed    :", len(streamed), "->", streamed[:4], "...")
print("\nstatus messages:")
for s in statuses:
    print("   ", s[:100])
print("\ndone note:", (done or {}).get("note"))

assert tp.fills == ["ATH", "CTA", "VCE"], tp.fills
assert kiwi.fills == ["ATH", "CTA", "VCE"], kiwi.fills
assert all(src == "travelpayouts" for _, src, _ in cards), "cards must paint from the cheap source first"
assert order.index("card:VCE") < order.index("status"), "all cards must land before the upgrade starts"
assert streamed, "the upgrade must stream its columns"
assert (done or {}).get("note", "").startswith("Click any cell") or "upgraded" in (done or {}).get("note", "")
print("\nORDER VERIFIED: every card painted from estimates first, then upgraded and streamed.")
