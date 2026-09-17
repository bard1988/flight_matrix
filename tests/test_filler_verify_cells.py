"""verify_cells() must account for every requested cell, not just the ones it actually
calls the provider for.

A cell that is already a fresh cache hit, or belongs to a route Google has never once
priced, was silently dropped from `pending` with no event at all. A one-shot caller never
noticed; a caller that reruns until every cell it asked for has come back once (the
open-grid band fill, `bandCells` in app.js) never converged -- a cell resolved this way
looked, from the caller's side, exactly like one that was never even tried.
"""
from __future__ import annotations

import pytest

from models import SearchRequest


@pytest.fixture
def req():
    return SearchRequest(
        origin="TLV", depart_date="2026-10-01", return_date="2026-10-20",
        adults=2, children=0, currency="ils",
    )


class _FakeVerifier:
    """Records every call it actually receives; never called for a resolved cell."""

    def __init__(self, answers=None):
        self.calls = []
        self.answers = answers or {}

    def verify(self, origin, destination, depart_date, return_date, adults, children,
               currency, nonstop_only=False):
        self.calls.append((destination, depart_date, return_date))
        return self.answers.get((destination, depart_date, return_date),
                                {"total": 999, "airline": "XX", "stops_out": 0, "duration": "2h"})


@pytest.fixture
def fake_verifier(monkeypatch):
    import filler
    fake = _FakeVerifier()
    monkeypatch.setattr(filler, "_verifier_provider", lambda: fake)
    return fake


def _cell_events(events):
    return [e for e in events if e["type"] == "fill_cell"]


class TestEveryTargetGetsOneEvent:
    def test_a_fresh_cache_hit_is_resolved_with_no_network_call(self, isolated_cache, req, fake_verifier):
        import filler

        isolated_cache.put_verified({
            "origin": "TLV", "destination": "JFK", "depart_date": "2026-10-05",
            "return_date": "2026-10-12", "adults": 2, "children": 0, "currency": "ils",
            "total": 1234.0, "airline": "AA", "stops_out": 1, "stops_back": 1,
            "duration": "11h", "link": None, "error": None,
        })
        targets = [("JFK", "2026-10-05", "2026-10-12")]

        events = list(filler.verify_cells(req, targets))
        cells = _cell_events(events)

        assert len(cells) == 1
        assert cells[0]["ok"] is True
        assert cells[0]["total"] == 1234.0
        assert fake_verifier.calls == [], "a fresh cache hit must never touch the provider"

    def test_a_dead_route_is_resolved_as_a_failure_with_no_network_call(self, isolated_cache, req, fake_verifier):
        import filler

        base = {"origin": "TLV", "destination": "ETM", "adults": 2, "children": 0, "currency": "ils"}
        for i in range(3):   # unpriceable_destinations needs min_failures (default 3)
            isolated_cache.put_verified({**base, "depart_date": f"2026-09-0{i + 1}",
                                          "return_date": f"2026-09-1{i + 1}", "total": None,
                                          "airline": None, "stops_out": None, "stops_back": None,
                                          "duration": None, "link": None, "error": "no fare"})

        targets = [("ETM", "2026-10-05", "2026-10-12")]
        events = list(filler.verify_cells(req, targets))
        cells = _cell_events(events)

        assert len(cells) == 1
        assert cells[0]["ok"] is False
        assert fake_verifier.calls == [], "a route with no fare ever must never be re-tried"

    def test_a_genuinely_new_cell_still_goes_through_the_provider(self, isolated_cache, req, fake_verifier):
        import filler

        targets = [("LHR", "2026-10-05", "2026-10-12")]
        events = list(filler.verify_cells(req, targets))
        cells = _cell_events(events)

        assert len(cells) == 1
        assert cells[0]["ok"] is True
        assert fake_verifier.calls == [("LHR", "2026-10-05", "2026-10-12")]

    def test_a_mixed_batch_gets_one_event_per_target_and_only_new_cells_hit_the_network(
        self, isolated_cache, req, fake_verifier
    ):
        import filler

        isolated_cache.put_verified({
            "origin": "TLV", "destination": "JFK", "depart_date": "2026-10-05",
            "return_date": "2026-10-12", "adults": 2, "children": 0, "currency": "ils",
            "total": 1234.0, "airline": None, "stops_out": None, "stops_back": None,
            "duration": None, "link": None, "error": None,
        })
        base = {"origin": "TLV", "destination": "ETM", "adults": 2, "children": 0, "currency": "ils"}
        for i in range(3):
            isolated_cache.put_verified({**base, "depart_date": f"2026-09-0{i + 1}",
                                          "return_date": f"2026-09-1{i + 1}", "total": None,
                                          "airline": None, "stops_out": None, "stops_back": None,
                                          "duration": None, "link": None, "error": "no fare"})

        targets = [
            ("JFK", "2026-10-05", "2026-10-12"),   # cache hit
            ("ETM", "2026-10-05", "2026-10-12"),   # dead route
            ("LHR", "2026-10-05", "2026-10-12"),   # genuinely new
        ]
        events = list(filler.verify_cells(req, targets))
        cells = _cell_events(events)

        assert len(cells) == 3, "every requested cell must produce exactly one fill_cell event"
        by_dest = {c["destination"]: c for c in cells}
        assert by_dest["JFK"]["ok"] is True and by_dest["JFK"]["total"] == 1234.0
        assert by_dest["ETM"]["ok"] is False
        assert by_dest["LHR"]["ok"] is True
        assert fake_verifier.calls == [("LHR", "2026-10-05", "2026-10-12")]

        fill_start = next(e for e in events if e["type"] == "fill_start")
        assert fill_start["total_cells"] == 3   # the whole batch, not just the one live call
        fill_done = next(e for e in events if e["type"] == "fill_done")
        assert fill_done["filled"] == 2 and fill_done["failed"] == 1

    def test_an_empty_target_list_still_yields_start_and_done(self, isolated_cache, req, fake_verifier):
        import filler

        events = list(filler.verify_cells(req, []))
        assert [e["type"] for e in events] == ["fill_start", "fill_done"]
        assert fake_verifier.calls == []
