"""Discovery seeding (idea.md #15A).

When a region filter is set and the board provider's own discovery under-delivers inside
it, `board.build` probes a curated shortlist of that region's hubs (OurAirports, via
`airports.shortlist`) with one cheap Travelpayouts call each and folds in the ones that
price. This is what turns a TLV -> "Africa" search from "Marrakesh only" into a real board.
"""
from __future__ import annotations

import dataclasses

import pytest

import airports
import board
from conftest import fill_grid


# --------------------------------------------------------------------- airports.shortlist

def test_shortlist_is_region_scoped_and_hub_ranked():
    ke = airports.shortlist(["KE"], limit=50)
    assert "NBO" in ke and "MBA" in ke
    assert all(airports.describe(c)["country"] == "KE" for c in ke)
    # large airports rank ahead of the little strips
    tiers = [airports.describe(c).get("type") for c in ke]
    assert tiers.index("large") < (tiers.index("small") if "small" in tiers else len(tiers))


def test_shortlist_empty_selection_is_empty():
    assert airports.shortlist([], limit=50) == []
    assert airports.shortlist(["ZZ"], limit=50) == []


def test_shortlist_respects_the_limit():
    assert len(airports.shortlist(["KE", "TZ", "ZA", "ET", "MA", "EG"], limit=12)) == 12


# ------------------------------------------------------------------------- board.build

class _Discover:
    """Board provider double: discovery returns a fixed set, grids always fill."""

    name = "kiwi"
    strategy = "double"
    rate_limited = False

    def __init__(self, cities):
        self._cities = cities
        self.on_status = None
        self.on_cells = None
        self.cities = {c: airports.describe(c) for c in cities}

    def discover(self, request, dd, rd):
        return [(c, 900.0 + i) for i, c in enumerate(self._cities)]

    def fill_matrix(self, request, destination, dd, rd):
        return fill_grid(request, destination, dd, rd, 900.0, source=self.name, is_total=True)


class _FakeTP:
    """Stands in for TravelpayoutsProvider inside _seed_candidates: a fixed price book."""

    book = {"NBO": 300.0, "ZNZ": 350.0, "CPT": 500.0, "JNB": 480.0, "ADD": 260.0}

    def __init__(self, *a, **k):
        pass

    def cheapest_fare(self, origin, destination, month, currency, nonstop=False):
        return self.book.get(destination.upper())


@pytest.fixture
def africa_req(req):
    # Kenya, Tanzania, South Africa, Ethiopia — the region the board provider misses.
    return dataclasses.replace(req, country_codes=["KE", "TZ", "ZA", "ET"], max_destinations=5)


@pytest.fixture(autouse=True)
def _quiet(monkeypatch, isolated_cache):
    import config
    monkeypatch.setattr(config, "CHECK_HEADLINE", False)
    monkeypatch.setattr(config, "KIWI_CACHE_HOURS", 0.0)
    monkeypatch.setattr(config, "ESTIMATE_FIRST", False)
    monkeypatch.setattr(config, "TRAVELPAYOUTS_TOKEN", "test-token")
    monkeypatch.setattr(board, "TravelpayoutsProvider", _FakeTP)


def _events(req, provider):
    return list(board.build(req, provider=provider))


def test_thin_region_gets_seeded_from_the_shortlist(africa_req):
    # Discovery finds one African city; the probe adds the reachable hubs.
    events = _events(africa_req, _Discover(["RAK"]))  # RAK is MA, filtered out by the KE/TZ/ZA/ET selection
    seeded = [e for e in events if e["type"] == "region_seeded"]
    assert seeded and seeded[0]["added"] == 5

    filled = {e["city"] for e in events if e["type"] == "destination" and not e.get("preview")}
    # ADD (260) and NBO (300) are the cheapest probes, so they lead the board.
    assert {"Addis Ababa", "Nairobi"} <= filled


def test_seed_prices_are_party_totals(africa_req):
    events = _events(africa_req, _Discover([]))
    previews = {e["city"]: e for e in events if e["type"] == "destination" and e.get("preview")}
    # 2 adults, so the single-ticket 260 for ADD is previewed at ~520.
    assert previews["Addis Ababa"]["preview_price"] == pytest.approx(520.0)


def test_no_region_filter_means_no_probe(req, monkeypatch):
    calls = []
    monkeypatch.setattr(_FakeTP, "cheapest_fare",
                        lambda self, *a, **k: calls.append(a) or 100.0)
    events = _events(req, _Discover(["ATH", "CTA"]))
    assert not calls
    assert not [e for e in events if e["type"] == "region_seeded"]


def test_well_served_region_is_not_probed(africa_req, monkeypatch):
    calls = []
    monkeypatch.setattr(_FakeTP, "cheapest_fare",
                        lambda self, *a, **k: calls.append(1) or 100.0)
    # discovery already returns >= max_destinations inside the selection
    events = _events(africa_req, _Discover(["NBO", "MBA", "ZNZ", "CPT", "JNB", "DAR"]))
    assert not calls
    assert not [e for e in events if e["type"] == "region_seeded"]


def test_no_token_means_no_seeding(africa_req, monkeypatch):
    import config
    monkeypatch.setattr(config, "TRAVELPAYOUTS_TOKEN", "")
    events = _events(africa_req, _Discover(["RAK"]))
    assert not [e for e in events if e["type"] == "region_seeded"]
