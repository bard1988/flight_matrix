"""The SQLite cache: what it stores, and which rows it refuses to hand back.

The refusals matter more than the round trip. A cell served under the wrong passenger mix,
the wrong provider or an older fill strategy is not stale, it is wrong.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from conftest import make_cell


def test_round_trip(isolated_cache, req, axes):
    cache = isolated_cache
    departs, returns = axes
    cells = [make_cell(departs[0].isoformat(), returns[0].isoformat(), 750.0)]
    assert cache.put_cells("TLV", "ATH", "ils", cells, party=req.party_key) == 1

    grid = cache.get_matrix("TLV", "ATH", "ils", departs, returns, party=req.party_key)
    assert len(grid.cells) == 1
    only = next(iter(grid.cells.values()))
    assert only.price == 750.0
    assert only.source == "kiwi"
    assert only.is_total is True


def test_party_totals_are_not_served_to_a_different_mix(isolated_cache, req, axes):
    """A 2-adult total handed to a family search would quote two fifths of the real price."""
    cache = isolated_cache
    departs, returns = axes
    cache.put_cells("TLV", "ATH", "ils",
                    [make_cell(departs[0].isoformat(), returns[0].isoformat())],
                    party="2a0c")

    same = cache.get_matrix("TLV", "ATH", "ils", departs, returns, party="2a0c")
    other = cache.get_matrix("TLV", "ATH", "ils", departs, returns, party="2a3c")
    assert len(same.cells) == 1
    assert len(other.cells) == 0


def test_per_ticket_rows_are_mix_independent(isolated_cache, axes):
    """Estimates are a single fare the caller scales itself, so any mix may reuse them."""
    cache = isolated_cache
    departs, returns = axes
    cache.put_cells("TLV", "ATH", "ils",
                    [make_cell(departs[0].isoformat(), returns[0].isoformat(),
                               source="travelpayouts", is_total=False)],
                    party="2a0c")
    for party in ("2a0c", "2a3c", "5a0c"):
        assert len(cache.get_matrix("TLV", "ATH", "ils", departs, returns,
                                    party=party).cells) == 1


def test_source_filter_separates_the_providers(isolated_cache, axes):
    cache = isolated_cache
    departs, returns = axes
    cache.put_cells("TLV", "ATH", "ils",
                    [make_cell(departs[0].isoformat(), returns[0].isoformat(),
                               source="travelpayouts", is_total=False)], party="")
    assert len(cache.get_matrix("TLV", "ATH", "ils", departs, returns,
                                source="kiwi").cells) == 0
    assert len(cache.get_matrix("TLV", "ATH", "ils", departs, returns,
                                source="travelpayouts").cells) == 1


def test_rows_from_an_older_fill_strategy_are_refused(isolated_cache, req, axes, monkeypatch):
    """Cells written before the return date was pinned are wrong, not merely old: the
    return was inferred from a nights count measured at arrival, so an overnight outbound
    was filed against a date pair that cannot be booked."""
    import config
    cache = isolated_cache
    departs, returns = axes
    cache.put_cells("TLV", "ATH", "ils",
                    [make_cell(departs[0].isoformat(), returns[0].isoformat())],
                    party=req.party_key)
    monkeypatch.setattr(config, "FILL_VERSION", config.FILL_VERSION + 1)
    assert len(cache.get_matrix("TLV", "ATH", "ils", departs, returns,
                                party=req.party_key).cells) == 0


def test_age_filter_excludes_rows_older_than_the_window(isolated_cache, req, axes):
    """Backdate the row explicitly rather than leaning on max_age_hours=0.

    A zero-hour window puts the cutoff within microseconds of the write, so whether the
    row falls inside it depends on clock resolution. That made this test flaky: it passed
    on one run and failed on the next against identical code.
    """
    from datetime import timedelta
    from models import utcnow

    cache = isolated_cache
    departs, returns = axes
    cache.put_cells("TLV", "ATH", "ils",
                    [make_cell(departs[0].isoformat(), returns[0].isoformat())],
                    party=req.party_key)

    two_days_ago = (utcnow() - timedelta(hours=48)).isoformat()
    conn = cache.connect()
    conn.execute("UPDATE cells SET fetched_at = ?", (two_days_ago,))
    conn.commit()

    within = cache.get_matrix("TLV", "ATH", "ils", departs, returns,
                              max_age_hours=72, party=req.party_key)
    outside = cache.get_matrix("TLV", "ATH", "ils", departs, returns,
                               max_age_hours=24, party=req.party_key)
    assert len(within.cells) == 1
    assert len(outside.cells) == 0


def test_window_bounds_exclude_cells_outside_the_axes(isolated_cache, req, axes):
    cache = isolated_cache
    departs, returns = axes
    far = (departs[0] + timedelta(days=400)).isoformat()
    cache.put_cells("TLV", "ATH", "ils",
                    [make_cell(far, (departs[0] + timedelta(days=407)).isoformat())],
                    party=req.party_key)
    assert len(cache.get_matrix("TLV", "ATH", "ils", departs, returns,
                                party=req.party_key).cells) == 0


def test_verified_rows_are_keyed_by_the_passenger_mix(isolated_cache):
    cache = isolated_cache
    record = dict(origin="TLV", destination="ATH", depart_date="2026-10-01",
                  return_date="2026-10-08", adults=2, children=0, currency="ils",
                  total=1500.0, airline="A3", stops_out=0, stops_back=0,
                  duration="3h", link="https://example.com", error=None)
    cache.put_verified(record)

    assert cache.get_verified("TLV", "ATH", "2026-10-01", "2026-10-08", 2, 0, "ils")
    assert cache.get_verified("TLV", "ATH", "2026-10-01", "2026-10-08", 2, 3, "ils") is None

    everything = cache.get_all_verified("TLV", 2, 0, "ils")
    assert ("ATH", "2026-10-01", "2026-10-08") in everything


def _vrecord(**kw):
    base = dict(origin="TLV", destination="ATH", depart_date="2026-10-01",
                return_date="2026-10-08", adults=2, children=0, currency="ils",
                total=1500.0, airline="A3", stops_out=0, stops_back=0,
                duration="3h", link="https://example.com", error=None)
    base.update(kw)
    return base


def test_a_failed_recheck_never_clobbers_a_stored_price(isolated_cache):
    """#10-ish: /api/verify writes a null-total record when Google returns nothing. That
    must not overwrite a real price we already have -- the aged number is the fallback."""
    cache = isolated_cache
    cache.put_verified(_vrecord(total=1500.0))
    cache.put_verified(_vrecord(total=None, error="Google Flights found no flights."))

    row = cache.get_verified("TLV", "ATH", "2026-10-01", "2026-10-08", 2, 0, "ils")
    assert row["total"] == 1500.0


def test_fresh_minutes_filters_out_aged_verifications(isolated_cache, monkeypatch):
    cache = isolated_cache
    cache.put_verified(_vrecord(total=1500.0))
    # Backdate the row well past any freshness window.
    conn = cache.connect()
    conn.execute("UPDATE verified SET fetched_at = ?", ("2020-01-01T00:00:00",))
    conn.commit()

    assert cache.get_all_verified("TLV", 2, 0, "ils") != {}                       # no filter: still there
    assert cache.get_all_verified("TLV", 2, 0, "ils", fresh_minutes=60) == {}      # filtered: too old


def test_search_history_is_pruned(isolated_cache, monkeypatch):
    """Saved boards run to megabytes and nothing used to delete one; 324 rows had grown to
    69 MB of a 77 MB database."""
    import config
    cache = isolated_cache
    monkeypatch.setattr(config, "SEARCH_HISTORY_KEEP", 3)
    for i in range(8):
        sid = f"search{i:02d}"
        cache.create_search(sid, {"origin": "TLV"})
        cache.finish_search(sid, {"destinations": []})
    rows = cache.connect().execute("SELECT COUNT(*) FROM searches").fetchone()[0]
    assert rows == 3
    assert cache.get_search("search07") is not None       # newest survives
    assert cache.get_search("search00") is None           # oldest pruned
