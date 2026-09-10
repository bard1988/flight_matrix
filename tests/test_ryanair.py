"""Ryanair provider: the route map, the cheap-dozen discovery, and cheapestPerDay -> grid.

No network -- the farfnd/site calls are stubbed with canned payloads. The live endpoints
are exercised by data/probe_lccs.py.
"""
from __future__ import annotations

import pytest

import board
import fx
from models import SearchRequest
from providers.ryanair import RyanairProvider


@pytest.fixture(autouse=True)
def _fixed_fx(monkeypatch):
    monkeypatch.setattr(fx, "convert",
                        lambda amt, src, dst: amt * 4 if (src, dst) == ("EUR", "ILS") else amt)


@pytest.fixture(autouse=True)
def _quiet(monkeypatch, isolated_cache):
    import config
    monkeypatch.setattr(config, "CHECK_HEADLINE", False)
    monkeypatch.setattr(config, "KIWI_CACHE_HOURS", 0.0)


def _req(**kw):
    base = dict(origin="KRK", depart_date="2026-11-03", return_date="2026-11-27",
                adults=2, children=1, currency="ils", nights_min=7, nights_max=9)
    base.update(kw)
    return SearchRequest(**base)


ROUTES = [
    {"arrivalAirport": {"code": "AGP", "name": "Malaga", "city": {"name": "Malaga"},
                        "country": {"code": "es", "name": "Spain"}}},
    {"arrivalAirport": {"code": "BCN", "name": "Barcelona", "city": {"name": "Barcelona"},
                        "country": {"code": "es", "name": "Spain"}}},
    {"arrivalAirport": {"code": "STN", "name": "London Stansted", "city": {"name": "London"},
                        "country": {"code": "gb", "name": "United Kingdom"}}},
]

RTF = {"fares": [
    {"outbound": {"arrivalAirport": {"iataCode": "BCN"}},
     "summary": {"price": {"value": 42.0, "currencyCode": "EUR"}}},
    {"outbound": {"arrivalAirport": {"iataCode": "AGP"}},
     "summary": {"price": {"value": 58.5, "currencyCode": "EUR"}}},
]}


def _perday(days):
    return {"outbound": {"fares": [
        {"day": d, "price": {"value": v, "currencyCode": "EUR"}} for d, v in days.items()
    ]}}


def _provider(monkeypatch, out=None, back=None):
    p = RyanairProvider()
    out = out or {"2026-11-03": 20.0, "2026-11-06": 15.0, "2026-11-10": 30.0}
    back = back or {"2026-11-11": 25.0, "2026-11-14": 18.0, "2026-11-18": 40.0}

    def fake_get(baseurl, path, params):
        if "searchWidget/routes" in path:
            return ROUTES
        if path == "roundTripFares":
            return RTF
        if "cheapestPerDay" in path:
            return _perday(out if path.startswith("oneWayFares/KRK/") else back)
        raise AssertionError(f"unexpected path {path}")

    monkeypatch.setattr(p, "_get", fake_get)
    return p


def test_route_map_and_serves(monkeypatch):
    p = _provider(monkeypatch)
    r = p.routes("KRK")
    assert set(r) == {"AGP", "BCN", "STN"}
    assert r["AGP"] == {"city": "Malaga", "country": "ES", "name": "Malaga"}
    assert p.serves("KRK", "BCN") and not p.serves("KRK", "TLV")


def test_discover_is_the_priced_cheap_dozen(monkeypatch):
    p = _provider(monkeypatch)
    req = _req()
    dd, rd = board.date_axes(req)
    disc = dict(p.discover(req, dd, rd))
    # per-person EUR * 4 (fx) * 3 travellers
    assert disc["BCN"] == pytest.approx(42.0 * 4 * 3)
    assert disc["AGP"] == pytest.approx(58.5 * 4 * 3)
    assert list(dict(p.discover(req, dd, rd)))[0] == "BCN"      # cheapest first


def test_cheapest_per_day_pairs_into_a_grid(monkeypatch):
    p = _provider(monkeypatch)
    req = _req()
    dd, rd = board.date_axes(req)
    m = p.fill_matrix(req, "AGP", dd, rd)
    assert m.cells
    for c in m.cells.values():
        assert 7 <= c.nights <= 9
        assert c.source == "ryanair" and c.airline == "Ryanair"
        assert c.transfers == 0 and not c.is_total
        assert "ryanair.com" in c.link and "originIata=KRK" in c.link
    # Nov 3 -> Nov 11 is 8 nights: (20 + 25) EUR pp * 4 = 180 pp; party of 3 = 540
    c = next(x for x in m.cells.values()
             if x.depart_date == "2026-11-03" and x.return_date == "2026-11-11")
    assert c.price == pytest.approx(180.0)
    assert c.party_total(req, 1.0) == pytest.approx(540.0)


def test_no_routes_when_origin_is_off_network(monkeypatch):
    p = RyanairProvider()
    monkeypatch.setattr(p, "_get", lambda *a, **k: [] if "routes" in a[1] else {"fares": []})
    assert p.routes("TLV") == {}
    assert p.discover(_req(origin="TLV"), *board.date_axes(_req(origin="TLV"))) == []
