"""Regression tests for the bug that made the grid cache dead code.

`board.build` decided whether a cached grid was complete enough to reuse by calling
`DestinationMatrix.coverage(departs, returns)` WITHOUT the `nights` argument. Without it
coverage counts the whole depart <= return triangle, but only the trip lengths in the
nights range are askable, so a fully populated grid scored 115/435 = 0.26 against a 0.85
threshold and was never reused. Every repeat search refetched the entire board, which is
what the cache exists to prevent and the main way the provider's rate limit gets tripped.

`coverage`'s own docstring warns about this and `to_json` already passed it.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

import board
from conftest import fill_grid


class TestCoverageDenominator:
    def test_without_nights_it_counts_the_whole_triangle(self, req, axes):
        departs, returns = axes
        grid = fill_grid(req, "ATH", departs, returns)
        populated, valid = grid.coverage(departs, returns)
        triangle = sum(1 for d in departs for r in returns if r >= d)
        assert valid == triangle
        assert populated < valid                      # the shape of the old bug

    def test_with_nights_the_denominator_is_what_is_askable(self, req, axes):
        departs, returns = axes
        grid = fill_grid(req, "ATH", departs, returns)
        populated, valid = grid.coverage(departs, returns, nights=req.nights_span())
        assert populated == valid, "a fully filled grid must score 100%"

    def test_a_complete_grid_failed_the_old_threshold_and_passes_the_new_one(self, req, axes):
        import config
        departs, returns = axes
        grid = fill_grid(req, "ATH", departs, returns)

        _, valid_wrong = grid.coverage(departs, returns)
        _, valid_right = grid.coverage(departs, returns, nights=req.nights_span())

        assert len(grid.cells) / valid_wrong < config.CACHE_REUSE_MIN_FRACTION
        assert len(grid.cells) / valid_right >= config.CACHE_REUSE_MIN_FRACTION

    def test_a_genuinely_half_filled_grid_still_fails(self, req, axes):
        """The fraction check must keep doing its real job: a grid written by an older,
        narrower fetch must not satisfy a wider request forever."""
        import config
        departs, returns = axes
        grid = fill_grid(req, "ATH", departs, returns)
        for key in list(grid.cells)[: len(grid.cells) // 2]:
            del grid.cells[key]
        _, valid = grid.coverage(departs, returns, nights=req.nights_span())
        assert len(grid.cells) / valid < config.CACHE_REUSE_MIN_FRACTION


class TestBuildReusesACompleteCachedGrid:
    """End to end through board.build: a grid written to the cache must come back on the
    next search without the provider being asked again."""

    def test_second_search_serves_from_cache(self, req, axes, isolated_cache, monkeypatch):
        import config
        departs, returns = axes
        monkeypatch.setattr(config, "CHECK_HEADLINE", False)
        monkeypatch.setattr(config, "ESTIMATE_FIRST", False)
        monkeypatch.setattr(config, "KIWI_CACHE_HOURS", 24.0)

        calls = []

        class Provider:
            name = "kiwi"
            strategy = "kiwi-calendar"
            rate_limited = False
            on_status = None
            on_cells = None

            def discover(self, request, dd, rd):
                return [("ATH", 500.0)]

            def fill_matrix(self, request, destination, dd, rd):
                calls.append(destination)
                return fill_grid(request, destination, dd, rd)

        first = [e for e in board.build(req, provider=Provider())
                 if e["type"] == "destination" and not e.get("preview")]
        assert len(first) == 1
        assert calls == ["ATH"], "first search must fetch"

        second = [e for e in board.build(req, provider=Provider())
                  if e["type"] == "destination" and not e.get("preview")]
        assert len(second) == 1
        assert calls == ["ATH"], (
            "second search must NOT fetch again; the cached grid was rejected as "
            "incomplete, which is the coverage(nights=...) regression"
        )
        assert second[0].get("from_cache") is True

    def test_a_different_passenger_mix_does_not_reuse_the_cached_totals(
        self, req, axes, isolated_cache, monkeypatch
    ):
        """Party totals are only valid for the mix they were priced for. Reusing a 2-adult
        grid for a family would quote roughly two fifths of the true price."""
        import config
        from models import SearchRequest
        monkeypatch.setattr(config, "CHECK_HEADLINE", False)
        monkeypatch.setattr(config, "ESTIMATE_FIRST", False)
        monkeypatch.setattr(config, "KIWI_CACHE_HOURS", 24.0)

        calls = []

        class Provider:
            name = "kiwi"
            strategy = "kiwi-calendar"
            rate_limited = False
            on_status = None
            on_cells = None

            def discover(self, request, dd, rd):
                return [("ATH", 500.0)]

            def fill_matrix(self, request, destination, dd, rd):
                calls.append(request.party_key)
                return fill_grid(request, destination, dd, rd)

        list(board.build(req, provider=Provider()))
        family = SearchRequest(**{**req.__dict__, "adults": 2, "children": 3})
        list(board.build(family, provider=Provider()))

        assert calls == ["2a0c", "2a3c"], "the family search must refetch, not reuse"
