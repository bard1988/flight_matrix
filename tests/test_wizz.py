"""Wizz Air provider: timetable parsing, and the board using it to fill an aggregator gap.

No network -- the timetable/map calls are stubbed with canned payloads. The live endpoints
are exercised by data/probe_wizz*.py.
"""
from __future__ import annotations

import pytest

import board
import fx
from conftest import fill_grid
from models import DestinationMatrix, SearchRequest
from providers.wizz import WizzProvider


@pytest.fixture(autouse=True)
def _fixed_fx(monkeypatch):
    # Deterministic conversion: 4 ILS per EUR, 1:1 otherwise.
    monkeypatch.setattr(fx, "convert",
                        lambda amt, src, dst: amt * 4 if (src, dst) == ("EUR", "ILS") else amt)


@pytest.fixture(autouse=True)
def _quiet(monkeypatch, isolated_cache):
    import config
    monkeypatch.setattr(config, "CHECK_HEADLINE", False)
    monkeypatch.setattr(config, "KIWI_CACHE_HOURS", 0.0)


def _req(**kw):
    base = dict(origin="TLV", depart_date="2027-04-01", return_date="2027-04-30",
                adults=2, children=0, currency="ils", nights_min=13, nights_max=15)
    base.update(kw)
    return SearchRequest(**base)


TIMETABLE = {
    "outboundFlights": [
        {"departureStation": "TLV", "arrivalStation": "IAS", "departureDate": "2027-04-01T00:00:00",
         "priceType": "price", "price": {"amount": 100.0, "currencyCode": "EUR"}},
        {"departureStation": "TLV", "arrivalStation": "IAS", "departureDate": "2027-04-04T00:00:00",
         "priceType": "price", "price": {"amount": 90.0, "currencyCode": "EUR"}},
        {"departureStation": "TLV", "arrivalStation": "IAS", "departureDate": "2027-04-02T00:00:00",
         "priceType": "", "price": {"amount": None, "currencyCode": "EUR"}},  # no flight
    ],
    "returnFlights": [
        {"departureStation": "IAS", "arrivalStation": "TLV", "departureDate": "2027-04-15T00:00:00",
         "priceType": "price", "price": {"amount": 120.0, "currencyCode": "EUR"}},
        {"departureStation": "IAS", "arrivalStation": "TLV", "departureDate": "2027-04-18T00:00:00",
         "priceType": "price", "price": {"amount": 60.0, "currencyCode": "EUR"}},
    ],
}


def _provider(monkeypatch, timetable=TIMETABLE):
    w = WizzProvider()
    monkeypatch.setattr(w, "_load_map", lambda: {"TLV": {"IAS", "OTP", "CLJ"}})
    monkeypatch.setattr(w, "_post", lambda path, body: timetable)
    return w


def test_timetable_becomes_a_priced_grid(monkeypatch):
    w = _provider(monkeypatch)
    req = _req()
    dd, rd = board.date_axes(req)
    m = w.fill_matrix(req, "IAS", dd, rd)

    # 2 outbound x 2 return = 4 pairs, minus the ones outside 13-15 nights.
    for cell in m.cells.values():
        assert 13 <= cell.nights <= 15
        assert cell.source == "wizz"
        assert cell.currency == "ILS"
        assert cell.transfers == 0 and cell.return_transfers == 0
        assert cell.airline == "Wizz Air"
        assert "wizzair.com" in cell.link
        assert not cell.is_total                       # per-person, scaled downstream

    # Apr 1 -> Apr 15 is 14 nights: (100 + 120) EUR pp * 4 ILS = 880 pp; party of 2 = 1760.
    apr1 = next(c for c in m.cells.values()
                if c.depart_date == "2027-04-01" and c.return_date == "2027-04-15")
    assert apr1.price == pytest.approx(880.0)
    assert apr1.party_total(req, 1.0) == pytest.approx(1760.0)


def test_unserved_route_returns_empty_without_calling(monkeypatch):
    w = _provider(monkeypatch)
    called = []
    monkeypatch.setattr(w, "_post", lambda *a, **k: called.append(1) or {})
    req = _req()
    dd, rd = board.date_axes(req)
    m = w.fill_matrix(req, "JFK", dd, rd)      # not in the stub map
    assert not m.cells and not called


class _StubWizz:
    """Fills only the routes it is told to, like the real one falling back for a gap."""

    def __init__(self, fills):
        self._fills = fills            # {dest: price} it can fill

    def routes(self, origin):
        return sorted(self._fills)

    def serves(self, origin, dest):
        return dest.upper() in self._fills

    def fill_matrix(self, request, destination, dd, rd):
        if destination.upper() not in self._fills:
            return DestinationMatrix(origin=request.origin.upper(), destination=destination.upper())
        return fill_grid(request, destination, dd, rd, self._fills[destination.upper()],
                         source="wizz", is_total=False)


def test_board_fills_an_empty_route_from_wizz(req, monkeypatch):
    import config
    from test_board_flow import FakeProvider

    monkeypatch.setattr(config, "ESTIMATE_FIRST", False)
    monkeypatch.setattr(config, "WIZZ_ENABLED", True)
    monkeypatch.setattr(board, "_wizz_singleton", _StubWizz({"CTA": 800.0}))

    # The aggregator has nothing for CTA; Wizz flies it.
    provider = FakeProvider("kiwi", empty={"CTA"})
    events = list(board.build(req, provider=provider))

    wizz_fill = [e for e in events if e["type"] == "wizz_fill"]
    assert wizz_fill and wizz_fill[0]["destination"] == "CTA"

    cards = {e["destination"]: e for e in events
             if e["type"] == "destination" and not e.get("preview")}
    assert "CTA" in cards
    assert cards["CTA"]["cells"][0]["source"] == "wizz"
    assert not any(e["type"] == "destination_empty" for e in events)
