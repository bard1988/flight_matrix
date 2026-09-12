"""The order board.build emits things in, which is most of its observable behaviour.

Covers the three streaming changes: headline-only previews, the estimate-first pass with a
Kiwi upgrade behind it, and the per-column cell streaming. All providers are doubles.
"""
from __future__ import annotations

import dataclasses

import pytest

import board
from conftest import fill_grid


class FakeProvider:
    """Configurable stand-in for either provider."""

    def __init__(self, name, *, cities=("ATH", "CTA", "VCE"), price=1000.0,
                 is_total=True, nights=None, fail=None, empty=()):
        self.name = name
        self.strategy = f"{name}-double"
        self.rate_limited = False
        self.on_status = None
        self.on_cells = None
        self._cities = cities
        self._price = price
        self._is_total = is_total
        self._nights = nights
        self._fail = fail
        self._empty = set(empty)
        self.discovered = 0
        self.filled = []

    def discover(self, request, dd, rd):
        self.discovered += 1
        return [(c, self._price + i) for i, c in enumerate(self._cities)]

    def fill_matrix(self, request, destination, dd, rd):
        self.filled.append(destination)
        if self._fail:
            raise self._fail
        if destination in self._empty:
            from models import DestinationMatrix
            return DestinationMatrix(origin=request.origin.upper(),
                                     destination=destination.upper())
        grid = fill_grid(request, destination, dd, rd, self._price,
                         source=self.name, is_total=self._is_total, nights=self._nights)
        if self.on_cells:
            by_ret = {}
            for cell in grid.cells.values():
                by_ret.setdefault(cell.return_date, []).append(cell)
            for cells in by_ret.values():
                self.on_cells(destination, cells)
        return grid


@pytest.fixture(autouse=True)
def _quiet(monkeypatch, isolated_cache):
    import config
    monkeypatch.setattr(config, "CHECK_HEADLINE", False)
    monkeypatch.setattr(config, "KIWI_CACHE_HOURS", 0.0)


def collect(req, provider):
    return list(board.build(req, provider=provider))


class TestPreviews:
    def test_every_destination_previews_before_any_grid_lands(self, req, monkeypatch):
        import config
        monkeypatch.setattr(config, "ESTIMATE_FIRST", False)
        events = collect(req, FakeProvider("kiwi"))
        kinds = [(e["type"], e.get("preview", False)) for e in events
                 if e["type"] == "destination"]
        previews = [i for i, k in enumerate(kinds) if k[1]]
        filled = [i for i, k in enumerate(kinds) if not k[1]]
        assert previews and filled
        assert max(previews) < min(filled), "all previews must precede all filled cards"

    def test_a_preview_carries_a_price_but_no_cells_and_no_best(self, req, monkeypatch):
        import config
        monkeypatch.setattr(config, "ESTIMATE_FIRST", False)
        pv = [e for e in collect(req, FakeProvider("kiwi"))
              if e["type"] == "destination" and e.get("preview")]
        assert pv
        for e in pv:
            assert e["cells"] == []
            assert e["best"] is None
            assert e["preview_price"] > 0

    def test_previews_are_capped_at_the_requested_destination_count(self, req, monkeypatch):
        """Discovery over-fetches by CANDIDATE_MULTIPLIER; previewing a destination the
        loop never reaches would leave a card stuck saying it is still loading."""
        import config
        monkeypatch.setattr(config, "ESTIMATE_FIRST", False)
        provider = FakeProvider("kiwi", cities=tuple(f"C{i:02d}" for i in range(20)))
        pv = [e for e in collect(req, provider)
              if e["type"] == "destination" and e.get("preview")]
        assert len(pv) == req.max_destinations

    def test_sort_key_ranks_a_preview_on_its_discovery_price(self):
        assert board.sort_key({"preview": True, "preview_price": 900.0, "best": None}) == 900.0
        assert board.sort_key({"best": {"estimate": 500.0}}) == 500.0
        assert board.sort_key({"best": None}) == float("inf")


class TestEstimateFirst:
    def test_cards_paint_from_the_cheap_source_then_the_upgrade_runs(self, req, monkeypatch):
        import config
        monkeypatch.setattr(config, "ESTIMATE_FIRST", True)
        monkeypatch.setattr(config, "TRAVELPAYOUTS_TOKEN", "x")
        cheap = FakeProvider("travelpayouts", is_total=False, nights=[5])
        monkeypatch.setattr(board, "TravelpayoutsProvider", lambda *a, **k: cheap)
        live = FakeProvider("kiwi")

        events = collect(req, live)
        cards = [e for e in events if e["type"] == "destination" and not e.get("preview")]

        assert cards, "the cheap source must produce cards"
        assert all(c["best"]["source"] == "travelpayouts" for c in cards)
        assert cheap.filled, "cheap source ran"
        assert live.filled, "upgrade ran afterwards"
        assert live.discovered == 0, "discovery must come from the cheap source too"

    def test_the_upgrade_streams_its_columns(self, req, monkeypatch):
        import config
        monkeypatch.setattr(config, "ESTIMATE_FIRST", True)
        monkeypatch.setattr(config, "TRAVELPAYOUTS_TOKEN", "x")
        cheap = FakeProvider("travelpayouts", is_total=False, nights=[5])
        monkeypatch.setattr(board, "TravelpayoutsProvider", lambda *a, **k: cheap)

        streamed = []
        live = FakeProvider("kiwi")
        live.on_cells = lambda d, c: streamed.append((d, len(c)))
        collect(req, live)
        assert streamed, "the upgrade must emit cells as columns land"

    def test_a_blocked_upgrade_leaves_the_estimate_board_intact(self, req, monkeypatch):
        from providers.base import ProviderError
        import config
        monkeypatch.setattr(config, "ESTIMATE_FIRST", True)
        monkeypatch.setattr(config, "TRAVELPAYOUTS_TOKEN", "x")
        cheap = FakeProvider("travelpayouts", is_total=False, nights=[5])
        monkeypatch.setattr(board, "TravelpayoutsProvider", lambda *a, **k: cheap)
        live = FakeProvider("kiwi", fail=ProviderError("rate limited"))

        events = collect(req, live)
        cards = [e for e in events if e["type"] == "destination" and not e.get("preview")]
        done = next(e for e in events if e["type"] == "done")

        assert len(cards) == len(cheap.filled) > 0, "board survives a blocked upgrade"
        assert done["destinations"] == len(cards)
        assert len(live.filled) == 1, "one attempt, then it gives up"

    def test_disabled_flag_uses_the_live_provider_directly(self, req, monkeypatch):
        import config
        monkeypatch.setattr(config, "ESTIMATE_FIRST", False)
        live = FakeProvider("kiwi")
        cards = [e for e in collect(req, live)
                 if e["type"] == "destination" and not e.get("preview")]
        assert live.discovered == 1
        assert all(c["best"]["source"] == "kiwi" for c in cards)

    def test_a_search_filter_skips_the_cheap_source_too(self, req, monkeypatch):
        """TravelpayoutsProvider reads no nonstop/hour filter at all, so a filtered search's
        first (fast) pass came back unfiltered under ESTIMATE_FIRST -- only the later Kiwi
        upgrade pass actually honoured what the user asked for. A request with a filter set
        must go straight to the live provider, same as it already skips cache reuse."""
        import config
        monkeypatch.setattr(config, "ESTIMATE_FIRST", True)
        monkeypatch.setattr(config, "TRAVELPAYOUTS_TOKEN", "x")
        cheap = FakeProvider("travelpayouts", is_total=False, nights=[5])
        monkeypatch.setattr(board, "TravelpayoutsProvider", lambda *a, **k: cheap)
        live = FakeProvider("kiwi")

        filtered_req = dataclasses.replace(req, nonstop_only=True)
        cards = [e for e in collect(filtered_req, live)
                 if e["type"] == "destination" and not e.get("preview")]

        assert not cheap.filled, "the cheap source must not run at all for a filtered search"
        assert cards and all(c["best"]["source"] == "kiwi" for c in cards)


class TestBoardHousekeeping:
    def test_empty_destinations_are_reported_not_carded(self, req, monkeypatch):
        import config
        monkeypatch.setattr(config, "ESTIMATE_FIRST", False)
        provider = FakeProvider("kiwi", empty={"CTA"})
        events = collect(req, provider)
        assert any(e["type"] == "destination_empty" and e["destination"] == "CTA"
                   for e in events)
        carded = {e["destination"] for e in events
                  if e["type"] == "destination" and not e.get("preview")}
        assert "CTA" not in carded

    def test_stop_ends_the_build_early(self, req, monkeypatch):
        import config
        monkeypatch.setattr(config, "ESTIMATE_FIRST", False)
        events = list(board.build(req, provider=FakeProvider("kiwi"),
                                  should_stop=lambda: True))
        done = next(e for e in events if e["type"] == "done")
        assert done["stopped"] is True

    def test_cells_outside_the_nights_range_are_pruned(self, req, monkeypatch):
        """Verified cells accumulate across searches, so a 5-7 night board must not pick
        up stray 14-night cells left over from earlier work."""
        import config
        monkeypatch.setattr(config, "ESTIMATE_FIRST", False)
        provider = FakeProvider("kiwi", nights=[5, 6, 7, 14])
        cards = [e for e in collect(req, provider)
                 if e["type"] == "destination" and not e.get("preview")]
        assert cards
        for card in cards:
            assert all(c["nights"] in req.nights_span() for c in card["cells"])


class TestDestinationMatching:
    """A short needle is a code the user typed, not a fragment of a name.

    Regression: the exact-match guard was not enough on its own, because the substring
    fall-through still matched "IT" inside L-it-huania, Un-it-ed Kingdom and Spl-it, so a
    search for Italy returned Vilnius, London and Split.
    """

    @pytest.mark.parametrize("code,city,country", [
        ("VNO", "Vilnius", "LT"),        # Lithuania
        ("LHR", "London", "GB"),         # United Kingdom
        ("SPU", "Split", "HR"),          # the city name itself contains "it"
    ])
    def test_short_needle_does_not_match_inside_a_word(self, code, city, country):
        assert board.destination_matches("it", code, city, country) is False

    def test_country_code_matches_exactly(self):
        assert board.destination_matches("it", "FCO", "Rome", "IT") is True
        assert board.destination_matches("gr", "ATH", "Athens", "GR") is True

    def test_airport_code_matches_exactly(self):
        assert board.destination_matches("ath", "ATH", "Athens", "GR") is True

    @pytest.mark.parametrize("needle,city", [
        ("ath", "Athens"), ("rio", "Rio de Janeiro"), ("nic", "Nice"),
    ])
    def test_short_needle_still_matches_a_word_start(self, needle, city):
        assert board.destination_matches(needle, "XXX", city, "FR") is True

    def test_long_needle_matches_by_substring(self):
        assert board.destination_matches("thens", "ATH", "Athens", "GR") is True
        assert board.destination_matches("italy", "FCO", "Rome", "IT") is True
        assert board.destination_matches("kingdom", "LHR", "London", "GB") is True

    def test_empty_needle_matches_everything(self):
        assert board.destination_matches("", "ATH", "Athens", "GR") is True
