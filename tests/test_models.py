"""Date axes, trip lengths, and what a cell costs a party.

These are the calculations every price on the board is derived from, and several of them
encode decisions that were expensive to get wrong (see the comments in models.py).
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from models import Cell, DestinationMatrix, SearchRequest


def make_request(**kw) -> SearchRequest:
    base = dict(origin="TLV", depart_date="2026-10-01", return_date="2026-10-15",
                adults=2, children=0, currency="ils", nights_min=5, nights_max=7)
    base.update(kw)
    return SearchRequest(**base)


class TestNightsSpan:
    def test_inclusive_of_both_ends(self):
        assert make_request(nights_min=5, nights_max=7).nights_span() == [5, 6, 7]

    def test_single_length(self):
        assert make_request(nights_min=7, nights_max=7).nights_span() == [7]

    def test_missing_range_falls_back_to_a_band_not_to_the_dates(self):
        # The two date fields bound a PERIOD, not a trip, so a missing nights range must
        # not be inferred from them.
        span = make_request(nights_min=None, nights_max=None).nights_span()
        assert span == [5, 6, 7, 8, 9]

    def test_reversed_range_is_tolerated(self):
        assert make_request(nights_min=9, nights_max=4).nights_span() == [4, 5, 6, 7, 8, 9]

    def test_zero_nights_allowed(self):
        assert make_request(nights_min=0, nights_max=1).nights_span() == [0, 1]


class TestRangeAxes:
    def test_departures_stop_where_the_shortest_trip_still_fits(self):
        departs, returns = make_request().range_axes()
        # Window is Oct 1-15 and the shortest trip is 5 nights, so the last useful
        # departure is Oct 10; departing later cannot return inside the window.
        assert departs[0] == date(2026, 10, 1)
        assert departs[-1] == date(2026, 10, 10)

    def test_returns_start_at_the_shortest_trip_from_the_window_start(self):
        _, returns = make_request().range_axes()
        assert returns[0] == date(2026, 10, 6)     # Oct 1 + 5 nights
        assert returns[-1] == date(2026, 10, 15)

    def test_reversed_dates_are_swapped_not_rejected(self):
        a = make_request(depart_date="2026-10-15", return_date="2026-10-01").range_axes()
        b = make_request(depart_date="2026-10-01", return_date="2026-10-15").range_axes()
        assert a == b

    def test_every_axis_pair_is_reachable_by_some_allowed_trip_length(self):
        req = make_request()
        departs, returns = req.range_axes()
        span = set(req.nights_span())
        assert any((r - d).days in span for d in departs for r in returns)


class TestPartyPricing:
    def test_single_ticket_estimate_is_scaled_by_the_party(self):
        req = make_request(adults=2, children=3)
        cell = Cell(depart_date="2026-10-01", return_date="2026-10-08", price=100.0,
                    currency="ils", source="travelpayouts", is_total=False)
        # child_factor 1.0 means five full fares
        assert cell.party_total(req, 1.0) == pytest.approx(500.0)
        assert cell.party_total(req, 0.5) == pytest.approx(350.0)

    def test_a_party_total_is_never_scaled_again(self):
        req = make_request(adults=2, children=3)
        cell = Cell(depart_date="2026-10-01", return_date="2026-10-08", price=500.0,
                    currency="ils", source="kiwi", is_total=True)
        assert cell.party_total(req, 1.0) == pytest.approx(500.0)

    def test_a_verified_total_wins_over_both(self):
        req = make_request(adults=2)
        cell = Cell(depart_date="2026-10-01", return_date="2026-10-08", price=100.0,
                    currency="ils", source="travelpayouts", is_total=False,
                    verified=True, verified_total=1234.0)
        assert cell.party_total(req, 1.0) == pytest.approx(1234.0)

    def test_party_key_distinguishes_passenger_mixes(self):
        assert make_request(adults=2, children=0).party_key == "2a0c"
        assert make_request(adults=2, children=3).party_key == "2a3c"


class TestBookingLink:
    """Passenger counts must not be baked into a cached link: the cell cache is keyed by
    route, dates and currency only, so a 2-adult link would be served to a family search."""

    def _cell(self):
        return Cell(depart_date="2026-10-01", return_date="2026-10-08", price=100.0,
                    currency="ils",
                    link="https://www.kiwi.com/en/search/results/tel-aviv/athens/x/y?adults=2")

    def test_passenger_mix_is_rebuilt_from_the_live_request(self):
        link = self._cell().booking_link(make_request(adults=2, children=3))
        assert "adults=2" in link and "children=3" in link
        assert link.count("adults=") == 1

    def test_nonstop_filter_is_carried_into_the_link(self):
        req = make_request(nonstop_only=True)
        assert "stopNumber=0" in self._cell().booking_link(req)

    def test_non_kiwi_links_are_left_alone(self):
        cell = Cell(depart_date="2026-10-01", return_date="2026-10-08", price=1.0,
                    currency="ils", link="https://example.com/deal?a=1")
        assert cell.booking_link(make_request()) == "https://example.com/deal?a=1"


class TestSearchFilters:
    def test_plain_search_has_no_filters(self):
        assert make_request().has_search_filters is False

    def test_nonstop_is_a_search_filter(self):
        assert make_request(nonstop_only=True).has_search_filters is True

    def test_a_whole_day_time_window_is_not_a_filter(self):
        assert make_request(depart_hours=(0, 23)).has_search_filters is False

    def test_a_narrowed_time_window_is_a_filter(self):
        assert make_request(depart_hours=(6, 11)).has_search_filters is True


class TestCellDerivations:
    def test_nights_is_the_gap_between_the_dates(self):
        cell = Cell(depart_date="2026-10-01", return_date="2026-10-08",
                    price=1.0, currency="ils")
        assert cell.nights == 7

    def test_stops_take_the_worse_leg(self):
        cell = Cell(depart_date="2026-10-01", return_date="2026-10-08", price=1.0,
                    currency="ils", transfers=0, return_transfers=2)
        assert cell.max_transfers == 2
        assert cell.is_nonstop is False

    def test_nonstop_needs_both_legs_direct(self):
        cell = Cell(depart_date="2026-10-01", return_date="2026-10-08", price=1.0,
                    currency="ils", transfers=0, return_transfers=0)
        assert cell.is_nonstop is True


class TestMatrixBest:
    def test_keeps_the_cheaper_of_two_cells_for_one_date_pair(self):
        m = DestinationMatrix(origin="TLV", destination="ATH")
        m.add(Cell(depart_date="2026-10-01", return_date="2026-10-08", price=900.0,
                   currency="ils"))
        m.add(Cell(depart_date="2026-10-01", return_date="2026-10-08", price=500.0,
                   currency="ils"))
        assert len(m.cells) == 1
        assert m.best().price == 500.0

    def test_best_ranks_on_what_is_displayed_not_on_raw_price(self):
        """A verified total supersedes the estimate and is often much higher, so the
        lowest unit price is not necessarily the cheapest cell on screen."""
        req = make_request(adults=2)
        m = DestinationMatrix(origin="TLV", destination="ATH")
        m.add(Cell(depart_date="2026-10-01", return_date="2026-10-08", price=100.0,
                   currency="ils", is_total=False, verified=True, verified_total=9999.0))
        m.add(Cell(depart_date="2026-10-02", return_date="2026-10-09", price=300.0,
                   currency="ils", is_total=False))
        assert m.best(req, 1.0).depart_date == "2026-10-02"    # 600 beats 9999
