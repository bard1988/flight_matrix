"""Discovery seeding (idea.md #15A).

When a region filter is set and the board provider's own discovery under-delivers inside
it, `board.build` probes a curated shortlist of that region's hubs (OurAirports, via
`airports.shortlist`) with one Google Flights lookup each and folds in the ones that
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


class _FakeVerifier:
    """Stands in for GoogleFlightsProvider inside _seed_candidates: a fixed price book.

    Prices are already party totals (Google prices the real mix), so 2 adults doubles
    nothing here.
    """

    book = {"NBO": 600.0, "ZNZ": 700.0, "CPT": 1000.0, "JNB": 960.0, "ADD": 520.0}

    def __init__(self, *a, **k):
        pass

    def verify(self, origin, destination, depart, ret, adults, children, currency, nonstop=False):
        total = self.book.get(destination.upper())
        if total is None:
            from providers.base import ProviderError
            raise ProviderError("no itineraries")
        return {"total": total, "currency": currency}


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
    monkeypatch.setattr(config, "SEED_SHORTLIST", 40)
    # board._seed_candidates builds its verifier through the providers.verifier factory
    # (so demo mode gets the synthetic one). Swap the factory for the price-book double.
    monkeypatch.setattr(board, "_verifier_provider", lambda: _FakeVerifier())


def _events(req, provider):
    return list(board.build(req, provider=provider))


def test_thin_region_gets_seeded_from_the_shortlist(africa_req):
    # Discovery finds one African city; the probe adds the reachable hubs.
    events = _events(africa_req, _Discover(["RAK"]))  # RAK is MA, filtered out by the KE/TZ/ZA/ET selection
    seeded = [e for e in events if e["type"] == "region_seeded"]
    assert seeded and seeded[0]["added"] == 5

    filled = {e["city"] for e in events if e["type"] == "destination" and not e.get("preview")}
    # ADD (520) and NBO (600) are the cheapest probes, so they lead the board.
    assert {"Addis Ababa", "Nairobi"} <= filled


def test_seed_price_is_the_google_party_total(africa_req):
    events = _events(africa_req, _Discover([]))
    previews = {e["city"]: e for e in events if e["type"] == "destination" and e.get("preview")}
    # Google already prices the real party, so the probe total is carried through as-is.
    assert previews["Addis Ababa"]["preview_price"] == pytest.approx(520.0)


def test_unpriceable_routes_are_not_re_probed(africa_req, monkeypatch):
    import cache
    monkeypatch.setattr(cache, "unpriceable_destinations", lambda *a, **k: {"NBO", "ADD"})
    events = _events(africa_req, _Discover([]))
    filled = {e["city"] for e in events if e["type"] == "destination" and not e.get("preview")}
    assert "Nairobi" not in filled and "Addis Ababa" not in filled
    assert "Cape Town" in filled          # still seeded


def test_no_region_filter_means_no_probe(req, monkeypatch):
    calls = []
    monkeypatch.setattr(_FakeVerifier, "verify",
                        lambda self, *a, **k: calls.append(a) or {"total": 100.0})
    events = _events(req, _Discover(["ATH", "CTA"]))
    assert not calls
    assert not [e for e in events if e["type"] == "region_seeded"]


def test_well_served_region_is_not_probed(africa_req, monkeypatch):
    calls = []
    monkeypatch.setattr(_FakeVerifier, "verify",
                        lambda self, *a, **k: calls.append(1) or {"total": 100.0})
    # discovery already returns >= max_destinations inside the selection
    events = _events(africa_req, _Discover(["NBO", "MBA", "ZNZ", "CPT", "JNB", "DAR"]))
    assert not calls
    assert not [e for e in events if e["type"] == "region_seeded"]


def test_seeding_disabled_by_config(africa_req, monkeypatch):
    import config
    monkeypatch.setattr(config, "SEED_SHORTLIST", 0)
    events = _events(africa_req, _Discover(["RAK"]))
    assert not [e for e in events if e["type"] == "region_seeded"]


# --------------------------------------------------------------- probe retries once

class _FlakyVerifier:
    """verify() raises the same ProviderError for "genuinely no fare" and "the scrape
    itself failed" -- there is no way to tell them apart from the exception alone
    (measured: a real TLV -> Africa search saw 36 of 38 hubs fail their first probe).
    Fails each destination in `flaky` exactly once, then succeeds; `dead` never prices."""

    def __init__(self, book, flaky=(), dead=()):
        self.book = dict(book)
        self.flaky = {c.upper() for c in flaky}
        self.dead = {c.upper() for c in dead}
        self.calls: list[str] = []

    def verify(self, origin, destination, depart, ret, adults, children, currency, nonstop=False):
        from providers.base import ProviderError
        code = destination.upper()
        self.calls.append(code)
        if code in self.dead:
            raise ProviderError("no itineraries")
        if code in self.flaky:
            self.flaky.discard(code)   # only the first attempt fails
            raise ProviderError("blip")
        total = self.book.get(code)
        if total is None:
            raise ProviderError("no itineraries")
        return {"total": total, "currency": currency}


def test_a_probe_that_blips_once_is_retried_and_still_lands(africa_req, monkeypatch):
    verifier = _FlakyVerifier({"ADD": 520.0, "NBO": 600.0}, flaky=["ADD"])
    monkeypatch.setattr(board, "_verifier_provider", lambda: verifier)

    events = _events(africa_req, _Discover(["RAK"]))
    filled = {e["city"] for e in events if e["type"] == "destination" and not e.get("preview")}
    assert "Addis Ababa" in filled            # survived its one blip
    assert verifier.calls.count("ADD") == 2   # exactly one retry, not a loop


def test_a_probe_that_never_prices_is_still_dropped_after_the_retry(africa_req, monkeypatch):
    verifier = _FlakyVerifier({"NBO": 600.0}, dead=["ADD"])
    monkeypatch.setattr(board, "_verifier_provider", lambda: verifier)

    events = _events(africa_req, _Discover(["RAK"]))
    filled = {e["city"] for e in events if e["type"] == "destination" and not e.get("preview")}
    assert "Addis Ababa" not in filled
    assert verifier.calls.count("ADD") == 2   # tried twice, then gave up -- not zero, not forever
