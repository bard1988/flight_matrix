"""Kiwi provider internals that do not need the network.

The block latch is the important one. Kiwi blocks on volume, by IP, for minutes, and
without a latch every in-flight call spends its own wait budget rediscovering that: one
25-column grid fill took 176 seconds to conclude what its first column already knew.
"""
from __future__ import annotations

import time
from datetime import date, timedelta

import pytest

from providers import kiwi
from providers.base import ProviderError


class TestBlockLatch:
    def test_starts_clear(self):
        assert kiwi._block_remaining() == 0

    def test_latching_holds_for_the_cooldown(self):
        kiwi._latch_block(30)
        remaining = kiwi._block_remaining()
        assert 25 < remaining <= 30

    def test_clearing_releases_it(self):
        kiwi._latch_block(30)
        kiwi.clear_block()
        assert kiwi._block_remaining() == 0

    def test_latching_never_shortens_an_existing_hold(self):
        kiwi._latch_block(60)
        kiwi._latch_block(5)
        assert kiwi._block_remaining() > 50

    def test_a_latched_call_fails_immediately_without_touching_the_network(self):
        provider = kiwi.KiwiProvider()

        def explode(*a, **kw):                       # any network use is a failure
            raise AssertionError("the latch must short-circuit before any request")

        provider._client.post = explode
        kiwi._latch_block(60)

        started = time.monotonic()
        with pytest.raises(ProviderError, match="rate-limiting"):
            provider._gql("query {}", {}, "Test")
        assert time.monotonic() - started < 0.5, "must fail fast, not wait out a backoff"
        assert provider.rate_limited is True

    def test_the_latch_is_shared_across_provider_instances(self):
        """The block belongs to the egress IP, not to an object, and a provider is built
        per search, so a per-instance latch would forget it on the next search."""
        first = kiwi.KiwiProvider()
        first._client.post = lambda *a, **kw: (_ for _ in ()).throw(AssertionError("no net"))
        kiwi._latch_block(60)

        second = kiwi.KiwiProvider()
        second._client.post = lambda *a, **kw: (_ for _ in ()).throw(AssertionError("no net"))
        with pytest.raises(ProviderError):
            second._gql("query {}", {}, "Test")


class TestReturnColumn:
    """One call fills one COLUMN: every departure for one pinned return date."""

    def _provider(self, calendar_rows):
        provider = kiwi.KiwiProvider()
        provider._pace = lambda: None
        provider._gql = lambda q, v, o: {
            "returnItineraryPricesCalendar": {"calendar": calendar_rows}
        }
        return provider

    def test_every_cell_carries_the_return_date_that_was_asked_for(self, req, axes):
        departs, returns = axes
        ret = returns[3]
        rows = [{"date": d.isoformat(), "ratedPrice": {"price": {"amount": "900"}}}
                for d in departs[:3]]
        cells = self._provider(rows)._return_column(req, "ATH", departs[:3], ret)
        assert cells
        assert all(c.return_date == ret.isoformat() for c in cells)

    def test_cells_are_party_totals_not_single_fares(self, req, axes):
        departs, returns = axes
        rows = [{"date": departs[0].isoformat(),
                 "ratedPrice": {"price": {"amount": "900"}}}]
        cell = self._provider(rows)._return_column(req, "ATH", departs, returns[3])[0]
        assert cell.is_total is True
        assert cell.source == "kiwi"
        assert cell.party_total(req, 1.0) == pytest.approx(900.0)

    def test_a_departure_after_the_return_is_dropped(self, req, axes):
        departs, returns = axes
        ret = returns[0]
        rows = [{"date": (ret + timedelta(days=5)).isoformat(),
                 "ratedPrice": {"price": {"amount": "900"}}}]
        assert self._provider(rows)._return_column(req, "ATH", departs, ret) == []

    def test_unparseable_rows_are_skipped_not_fatal(self, req, axes):
        departs, returns = axes
        rows = [
            {"date": departs[0].isoformat(), "ratedPrice": {"price": {"amount": "900"}}},
            {"date": "not-a-date", "ratedPrice": {"price": {"amount": "900"}}},
            {"date": departs[1].isoformat(), "ratedPrice": {}},
        ]
        cells = self._provider(rows)._return_column(req, "ATH", departs, returns[3])
        assert len(cells) == 1


class TestFilters:
    def test_nonstop_becomes_a_search_side_filter(self, req):
        from models import SearchRequest
        provider = kiwi.KiwiProvider()
        plain = provider._filter(req)
        assert "maxStopsCount" not in plain

        nonstop = SearchRequest(**{**req.__dict__, "nonstop_only": True})
        assert provider._filter(nonstop)["maxStopsCount"] == 0

    def test_time_windows_reach_the_query(self, req):
        from models import SearchRequest
        provider = kiwi.KiwiProvider()
        narrowed = SearchRequest(**{**req.__dict__, "depart_hours": (6, 11)})
        flt = provider._filter(narrowed)
        assert flt["outbound"]["departureHours"] == {"start": 6, "end": 11}

    def test_a_whole_day_window_is_not_sent_as_a_filter(self, req):
        from models import SearchRequest
        provider = kiwi.KiwiProvider()
        whole_day = SearchRequest(**{**req.__dict__, "depart_hours": (0, 23)})
        assert provider._filter(whole_day) == {}

    def test_passengers_come_from_the_request(self, req):
        from models import SearchRequest
        provider = kiwi.KiwiProvider()
        family = SearchRequest(**{**req.__dict__, "adults": 2, "children": 3})
        assert provider._passengers(family) == {"adults": 2, "children": 3, "infants": 0}
