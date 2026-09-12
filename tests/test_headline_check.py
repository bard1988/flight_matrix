"""`_check_headline`: re-prices a card's cheapest cell for real before the user can act on
a stale number.

Regression coverage for a bug that shipped unnoticed: `_check_headline` used to call
`provider.itinerary_details` (Kiwi-only) and no-op via `hasattr` otherwise. Under
ESTIMATE_FIRST the fill provider for the initial pass is Travelpayouts, which has no such
method -- so on every real search the headline was never checked at all, and a stale
calendar price (the exact "click a cheap fare, get quoted 150% more" scenario the
function's own docstring describes) shipped straight to the user. Fixed by always going
through the Google verifier, and moved out of the per-destination fill loop into its own
pass afterward so it never delays a destination's first paint.
"""
from __future__ import annotations

import pytest

import board
from conftest import make_cell
from models import DestinationMatrix
from providers.base import ProviderError


class _StaleFillProvider:
    """Stands in for the ESTIMATE_FIRST initial-pass provider (Travelpayouts): fills a
    grid where exactly one cell (the eventual headline) carries a deliberately-stale low
    price and every other cell is priced well above it, so correcting the headline settles
    in one check rather than promoting another identically-stale cell. No
    itinerary_details -- the exact shape that let the bug through."""

    name = "travelpayouts"
    strategy = "double"
    rate_limited = False

    def __init__(self, cities, stale_price=500.0, other_price=5000.0):
        self._cities = cities
        self._stale_price = stale_price
        self._other_price = other_price
        self.on_status = None
        self.on_cells = None

    def discover(self, request, dd, rd):
        return [(c, self._stale_price) for c in self._cities]

    def fill_matrix(self, request, destination, dd, rd):
        matrix = DestinationMatrix(origin=request.origin.upper(), destination=destination.upper())
        lo, hi = request.nights_span()[0], request.nights_span()[-1]
        stale_used = False
        for ret in rd:
            for dep in dd:
                if lo <= (ret - dep).days <= hi:
                    price = self._stale_price if not stale_used else self._other_price
                    stale_used = True
                    matrix.add(make_cell(dep.isoformat(), ret.isoformat(), price))
        return matrix


class _FakeVerifier:
    """A destination -> real-total price book. Missing from the book means "no fare"."""

    def __init__(self, book):
        self.book = dict(book)
        self.calls = []

    def verify(self, origin, destination, depart, ret, adults, children, currency, nonstop_only=False):
        self.calls.append(destination.upper())
        total = self.book.get(destination.upper())
        if total is None:
            raise ProviderError("no itineraries")
        return {"total": total, "airline": "Verified Air", "stops_out": 0}


@pytest.fixture(autouse=True)
def _quiet(monkeypatch, isolated_cache):
    import config
    monkeypatch.setattr(config, "KIWI_CACHE_HOURS", 0.0)
    monkeypatch.setattr(config, "ESTIMATE_FIRST", False)   # use the passed-in provider as the fill pass
    monkeypatch.setattr(config, "CHECK_HEADLINE", True)
    monkeypatch.setattr(config, "CHECK_HEADLINE_MAX", 8)


def _events(req, provider):
    return list(board.build(req, provider=provider))


def test_headline_is_corrected_even_when_the_fill_provider_has_no_itinerary_details(req, monkeypatch):
    provider = _StaleFillProvider(["ATH"], stale_price=500.0)
    assert not hasattr(provider, "itinerary_details")
    verifier = _FakeVerifier({"ATH": 1900.0})
    monkeypatch.setattr(board, "_verifier_provider", lambda: verifier)

    events = _events(req, provider)
    updates = [e for e in events if e["type"] == "destination" and e.get("headline_update")]
    assert len(updates) == 1
    assert updates[0]["headline_checked"] is True
    assert verifier.calls == ["ATH"]   # the Google verifier did the check, not itinerary_details


def test_headline_check_streams_after_every_destination_is_already_painted(req, monkeypatch):
    """The whole point of the deferred pass: never hold up a destination's first paint."""
    provider = _StaleFillProvider(["ATH", "CTA", "VCE"], stale_price=500.0)
    verifier = _FakeVerifier({"ATH": 1900.0, "CTA": 1200.0, "VCE": 900.0})
    monkeypatch.setattr(board, "_verifier_provider", lambda: verifier)

    events = _events(req, provider)
    dest_events = [e for e in events if e["type"] == "destination" and not e.get("preview")]
    first_pass = [e for e in dest_events if not e.get("headline_update")]
    updates = [e for e in dest_events if e.get("headline_update")]
    assert len(first_pass) == 3
    assert len(updates) == 3
    last_first_pass_index = max(events.index(e) for e in first_pass)
    first_update_index = min(events.index(e) for e in updates)
    assert last_first_pass_index < first_update_index, \
        "a headline_update landed before some destination's first paint"


def test_a_failed_recheck_leaves_the_boards_own_cell_alone(req, monkeypatch):
    """The old Kiwi-only path deleted a cell on NoItinerariesError -- a confirmed "cannot be
    booked" signal from Kiwi's own full search. Google not finding a fare is a much weaker
    signal (routes missing from Google Flights are common and expected, per its own UI
    message elsewhere), so a miss here must never remove the board's own priced cell.
    """
    provider = _StaleFillProvider(["ATH"], stale_price=500.0)
    verifier = _FakeVerifier({})   # ATH never verifies
    monkeypatch.setattr(board, "_verifier_provider", lambda: verifier)

    events = _events(req, provider)
    first = next(e for e in events if e["type"] == "destination" and not e.get("preview"))
    updates = [e for e in events if e["type"] == "destination" and e.get("headline_update")]
    assert len(first["cells"]) > 0                     # the estimate is still there
    assert not any(u.get("headline_checked") for u in updates)
    assert verifier.calls == ["ATH"]                    # it did try


def test_no_check_headline_config_skips_the_pass_entirely(req, monkeypatch):
    import config
    monkeypatch.setattr(config, "CHECK_HEADLINE", False)
    provider = _StaleFillProvider(["ATH"], stale_price=500.0)
    verifier = _FakeVerifier({"ATH": 1900.0})
    monkeypatch.setattr(board, "_verifier_provider", lambda: verifier)

    events = _events(req, provider)
    assert not [e for e in events if e.get("headline_update")]
    assert not verifier.calls
