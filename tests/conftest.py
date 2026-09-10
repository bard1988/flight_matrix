"""Shared fixtures.

Two rules hold for everything under tests/:

1. **No network.** Every provider is a double. The real ones are exercised by the probe
   scripts in `data/`, which are manual tools, not tests.
2. **No shared state between tests.** `cache` keeps a module-level sqlite connection and
   `providers.kiwi` keeps a module-level block latch; both are reset per test rather than
   left to leak into the next one.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from models import Cell, DestinationMatrix, SearchRequest   # noqa: E402


@pytest.fixture
def req():
    """A plain 2-adult search: 15-day window, 5-7 night trips, no filters."""
    start = date(2026, 10, 1)
    return SearchRequest(
        origin="TLV",
        depart_date=start.isoformat(),
        return_date=(start + timedelta(days=14)).isoformat(),
        adults=2, children=0, currency="ils",
        max_destinations=3, nights_min=5, nights_max=7,
    )


@pytest.fixture
def axes(req):
    return req.range_axes()


@pytest.fixture
def isolated_cache(tmp_path, monkeypatch):
    """A cache module pointed at an empty database, with its connection reset.

    `cache.connect` memoises into `cache._conn`, so without the reset every test after the
    first would silently reuse whichever database ran first.
    """
    import cache as cache_module
    import config

    monkeypatch.setattr(config, "CACHE_DB", tmp_path / "test.sqlite")
    monkeypatch.setattr(cache_module, "CACHE_DB", tmp_path / "test.sqlite")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(cache_module, "DATA_DIR", tmp_path)
    monkeypatch.setattr(cache_module, "_conn", None)
    yield cache_module
    conn = getattr(cache_module, "_conn", None)
    if conn is not None:
        conn.close()
    monkeypatch.setattr(cache_module, "_conn", None)


@pytest.fixture(autouse=True)
def clear_kiwi_block():
    """The block latch is module-level on purpose (it models a per-IP block), so a test
    that latches it would otherwise disable Kiwi for every test after it."""
    from providers import kiwi
    kiwi.clear_block()
    yield
    kiwi.clear_block()


@pytest.fixture(autouse=True)
def no_wizz(monkeypatch):
    """Wizz is a live HTTP source (rule 1: no network). Off by default; the Wizz tests
    re-enable it with a stub. Also drop any singleton a prior test may have built."""
    import config
    import board
    monkeypatch.setattr(config, "WIZZ_ENABLED", False)
    board._wizz_singleton = None
    yield
    board._wizz_singleton = None


def make_cell(depart: str, ret: str, price: float = 1000.0, *,
              source: str = "kiwi", is_total: bool = True, **kw) -> Cell:
    return Cell(depart_date=depart, return_date=ret, price=price,
                currency="ils", source=source, is_total=is_total, **kw)


def fill_grid(request: SearchRequest, destination: str, depart_dates, return_dates,
              price: float = 1000.0, *, source: str = "kiwi", is_total: bool = True,
              nights=None) -> DestinationMatrix:
    """A matrix covering exactly the date pairs the request's nights range allows."""
    matrix = DestinationMatrix(origin=request.origin.upper(), destination=destination.upper())
    allowed = nights if nights is not None else request.nights_span()
    lo, hi = allowed[0], allowed[-1]
    for ret in return_dates:
        for dep in depart_dates:
            if lo <= (ret - dep).days <= hi:
                matrix.add(make_cell(dep.isoformat(), ret.isoformat(), price,
                                     source=source, is_total=is_total))
    return matrix
