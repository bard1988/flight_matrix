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


def test_shortlist_round_robins_by_country_so_one_does_not_starve_another():
    """Reported as "Africa, Oct to Jan, only 5-6 destinations -- doesn't add up", still
    true after both prior fixes (probe retry, probe trip length). Root cause: a flat sort
    by (scheduled, OurAirports size, code) put Johannesburg outside a 40-airport African
    shortlist entirely -- OurAirports' size classification is a runway/facility category,
    not a traffic one, so a country with many airports that happen to also qualify (Egypt:
    7 in the same tier) alphabetically crowded out every one of the dozens of other African
    countries with only one or two. Every selected country must get its own best hub
    before any single country gets a second.

    Two real gaps this does NOT close, deliberately not attempted here for lack of a good
    signal: WITHIN one country, the tie-break is still (scheduled, size, code) with no
    traffic data, so a country whose non-primary airport happens to sort first -- Kenya's
    Eldoret before Nairobi, alphabetically, both "large" and scheduled -- still has its
    real hub skipped; and when a region has more eligible COUNTRIES than the cap (Africa's
    ~59 against a much smaller cap), the round-robin's own country order is still
    alphabetical, so late-alphabet countries are what get cut, not a fair sample of them.
    SEED_SHORTLIST was raised to 60 specifically so that second gap does not bite for
    Africa, the widest region on offer -- see its own comment in config.py.
    """
    africa = ["KE", "TZ", "ZA", "ET", "MA", "EG", "NG", "GH", "SN", "MU", "SC", "RW",
              "UG", "DZ", "TN", "CI", "CM", "AO", "MZ", "NA", "ZM", "ZW", "BW", "MW"]
    sl = airports.shortlist(africa, limit=len(africa))   # room for every country, no cutoff
    countries = {airports.describe(c)["country"] for c in sl}
    # Every one of the 24 candidate countries gets its own seat -- the flat sort this
    # replaces let Egypt alone (7 same-tier airports) fill that many seats by itself.
    assert countries == set(africa), sl
    assert len(sl) == len(africa), sl   # one hub per country, not several for the same one


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


# ----------------------------------------------------- probe trip length, not the median

class _NightsSensitiveVerifier:
    """A hub that only sells 7-night round trips -- like a real one measured against
    production (TLV -> Nairobi priced at 7 nights, "no itineraries" at 12, same
    departure date)."""

    def __init__(self, code, good_nights=7):
        self.code = code.upper()
        self.good_nights = good_nights
        self.calls: list[int] = []

    def verify(self, origin, destination, depart, ret, adults, children, currency, nonstop=False):
        from datetime import date as _date
        from providers.base import ProviderError
        if destination.upper() != self.code:
            raise ProviderError("no itineraries")
        nights = (_date.fromisoformat(ret) - _date.fromisoformat(depart)).days
        self.calls.append(nights)
        if nights != self.good_nights:
            raise ProviderError("no itineraries")
        return {"total": 600.0, "currency": currency}


def test_the_probe_uses_a_week_not_the_spans_raw_median(req, monkeypatch):
    """A "Flexible" search (idea.md's 3-21 preset) medians out to ~12 nights -- a
    materially less commonly sold length than 7 for a real scheduled route. Probing with
    that median dropped a real, bookable hub from the whole region for no reason but which
    length the median happened to land on.
    """
    flexible_req = dataclasses.replace(
        req, country_codes=["KE"], max_destinations=5, nights_min=3, nights_max=21)
    verifier = _NightsSensitiveVerifier("NBO", good_nights=7)
    monkeypatch.setattr(board, "_verifier_provider", lambda: verifier)

    events = _events(flexible_req, _Discover([]))
    filled = {e["city"] for e in events if e["type"] == "destination" and not e.get("preview")}
    assert "Nairobi" in filled, f"probed nights: {verifier.calls}"
    assert 7 in verifier.calls
