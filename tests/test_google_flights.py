"""Small parser units for the Google Flights verifier -- no network.

The full verify() path is a live scrape (exercised by data/probe_*.py). These cover the
bits that were silently wrong: the trip duration used to report the first segment only,
so a 20-hour TLV->HAN itinerary showed "4h".
"""
from __future__ import annotations

from providers.google_flights import _elapsed_minutes


def test_elapsed_minutes_spans_the_whole_trip_including_layovers():
    # TLV 20 Oct 15:40  ->  (2 stops)  ->  HAN 21 Oct 15:00 local: ~23h20m elapsed.
    mins = _elapsed_minutes([2026, 10, 20], [15, 40], [2026, 10, 21], [15])
    assert mins == 23 * 60 + 20


def test_elapsed_minutes_handles_google_omitting_trailing_zeros():
    # [8] means 08:00, [11, 15] means 11:15 -- Google drops trailing components.
    assert _elapsed_minutes([2026, 6, 1], [8], [2026, 6, 1], [11, 15]) == 3 * 60 + 15


def test_elapsed_minutes_rejects_a_non_positive_or_unparseable_span():
    assert _elapsed_minutes([2026, 6, 7], [10], [2026, 6, 1], [10]) is None   # arrival before departure
    assert _elapsed_minutes(None, None, None, None) is None
