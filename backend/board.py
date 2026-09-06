"""Board assembly: discover destinations, fill each grid, emit progressively.

Runs as a generator so the API layer can stream one destination card at a time instead of
making the user stare at a spinner until all 20 are done.
"""
from __future__ import annotations

import traceback
from datetime import date
from typing import Any, Callable, Iterator

import airports
import cache
import config
from models import Cell, DestinationMatrix, SearchRequest, parse_date
from providers.base import NoItinerariesError, ProviderError
from providers.kiwi import KiwiProvider
from providers.travelpayouts import TravelpayoutsProvider


def make_board_provider():
    """Kiwi by default: it returns real party totals rather than single-adult estimates."""
    if config.BOARD_PROVIDER == "travelpayouts":
        return TravelpayoutsProvider()
    return KiwiProvider()


def _fallback_provider(current: Any):
    """The cached source is the safety net when the live one is unavailable."""
    if isinstance(current, TravelpayoutsProvider) or not config.TRAVELPAYOUTS_TOKEN:
        return None
    return TravelpayoutsProvider()


def _describe(provider: Any, code: str) -> dict[str, str]:
    """City and country for a destination.

    Prefer whatever the provider learned during discovery (Kiwi returns city and country
    with each result), and fall back to the bundled airport table.
    """
    known = getattr(provider, "cities", None)
    if known and code.upper() in known:
        return known[code.upper()]
    return airports.describe(code)


def destination_matches(needle: str, code: str, city: str, country: str) -> bool:
    """Match a destination against a filter term.

    Codes are matched EXACTLY, names by substring. Substring-matching codes against
    country names over-matches badly: "IT" is inside L-it-huania and Un-it-ed Kingdom, so
    a two-letter country code silently pulled in unrelated countries.
    """
    needle = needle.strip().lower()
    if not needle:
        return True
    code, country = (code or "").lower(), (country or "").lower()
    if len(needle) in (2, 3) and needle in (code, country):
        return True
    return needle in (city or "").lower() or needle in airports.country_name(country).lower()


def date_axes(request: SearchRequest) -> tuple[list[date], list[date]]:
    if request.is_range:
        return request.range_axes()
    return request.depart_window(), request.return_window()


def fill_one(
    request: SearchRequest,
    destination: str,
    provider: Any = None,
) -> dict[str, Any]:
    """Fill (or re-fill, at a wider window) a single destination and return its payload.

    Used by the scroll-to-extend path: the axes grow, and each visible destination is
    re-fetched over the larger window.
    """
    provider = provider or make_board_provider()
    depart_dates, return_dates = date_axes(request)
    matrix = provider.fill_matrix(request, destination, depart_dates, return_dates)
    if not request.has_search_filters:
        cache.put_cells(request.origin, destination, request.currency, matrix.cells.values(),
                        party=request.party_key)
    _apply_verified(request, matrix, depart_dates, return_dates)
    _prune_to_nights(request, matrix)
    info = airports.describe(destination)
    matrix.city, matrix.country = info["city"], info["country"]
    matrix.country_name = airports.country_name(info["country"])
    payload = matrix.to_json(request, depart_dates, return_dates,
                             config.CHILD_FACTOR, config.STALE_AFTER_HOURS)
    payload["type"] = "destination"
    return payload


def _check_headline(request: SearchRequest, matrix: DestinationMatrix, provider: Any) -> dict[str, Any]:
    """Re-price a card's cheapest cell with a real search until the headline is bookable.

    Kiwi's price calendar is a precomputed index and individual routes go stale. Measured on
    TLV-CTA: the calendar quoted 773-853 where a full search for the same dates returned
    1,893-2,003, i.e. +135% to +166%. The link was correct, so clicking through showed
    flights at more than double the quoted price and read as "the flight does not exist".

    Checking only once is not enough. Correcting the cheapest cell upward promotes the
    next-cheapest cell to headline, and on a stale route that one is stale by the same
    margin - the first version of this shipped a corrected 1,893 and then displayed 790 from
    an unchecked neighbour. So loop until the cheapest cell is one we priced ourselves, up
    to CHECK_HEADLINE_MAX searches.

    A pair the full search cannot fill at all is deleted: the calendar is claiming a price
    for a trip that cannot be booked, which is the worst cell on the board.
    """
    if not config.CHECK_HEADLINE or not hasattr(provider, "itinerary_details"):
        return {}

    quoted_first: float | None = None
    checks = 0
    dropped = 0
    settled = False
    for _ in range(max(1, config.CHECK_HEADLINE_MAX)):
        best = matrix.best(request, config.CHILD_FACTOR)
        if best is None:
            break
        if best.verified or best.checked:
            settled = True            # the headline is already a price we stand behind
            break
        quoted = best.party_total(request, config.CHILD_FACTOR)
        if quoted_first is None:
            quoted_first = quoted
        try:
            real = provider.itinerary_details(
                request, matrix.destination, best.depart_date, best.return_date)
        except NoItinerariesError:
            matrix.cells.pop((best.depart_date, best.return_date), None)
            dropped += 1
            continue
        except ProviderError:
            break                     # rate limit or transport: leave the grid as it is
        checks += 1
        best.price = float(real["price"])
        best.is_total = True
        best.checked = True
        if real.get("outbound"):
            best.transfers = real["outbound"].get("stops")
            best.airline = real["outbound"].get("carriers") or best.airline

    if quoted_first is None:
        # Nothing needed re-pricing, which on a repeat search is the normal case: the
        # correction is cached, so the headline is already one we fetched ourselves. Still
        # report that, or the card would look unconfirmed purely because it was cheap to serve.
        return {"headline_checked": settled, "headline_checks": 0, "headline_dropped": dropped}
    final = matrix.best(request, config.CHILD_FACTOR)
    if final is None:
        return {"headline_checked": False, "headline_dropped": dropped}
    actual = final.party_total(request, config.CHILD_FACTOR)
    return {
        "headline_checked": settled or final.checked or final.verified,
        "headline_drift": round((actual - quoted_first) / quoted_first * 100, 1)
                          if quoted_first else 0.0,
        "headline_was": round(quoted_first, 2),
        "headline_checks": checks,
        "headline_dropped": dropped,
    }


def _prune_to_nights(request: SearchRequest, matrix: DestinationMatrix) -> None:
    """In range mode keep only the trip lengths that were actually asked for.

    Verified cells accumulate across searches and are overlaid by date, so without this a
    "3-4 nights" board picks up stray 9- and 14-night cells from earlier work.
    """
    if not request.is_range:
        return
    wanted = set(request.nights_span())
    for key in [k for k, cell in matrix.cells.items() if cell.nights not in wanted]:
        del matrix.cells[key]


def _apply_verified(
    request: SearchRequest,
    matrix: DestinationMatrix,
    depart_dates: list[date] | None = None,
    return_dates: list[date] | None = None,
) -> None:
    """Overlay previously verified live totals onto this window's cells.

    The window bounds are required: verified rows accumulate across every search ever run
    for this origin, so without them a board for next April would inherit prices verified
    for this October, inflating the cell count past the grid size and hijacking the
    headline price.
    """
    bounds = None
    if depart_dates and return_dates:
        bounds = (depart_dates[0].isoformat(), depart_dates[-1].isoformat(),
                  return_dates[0].isoformat(), return_dates[-1].isoformat())

    verified = cache.get_all_verified(request.origin, request.adults, request.children, request.currency)
    for (destination, depart, ret), record in verified.items():
        if destination != matrix.destination:
            continue
        if bounds and not (bounds[0] <= depart <= bounds[1] and bounds[2] <= ret <= bounds[3]):
            continue
        cell = matrix.cells.get((depart, ret))
        if cell is None:
            # A verified cell with no cached estimate behind it still belongs on the board.
            cell = Cell(
                depart_date=depart,
                return_date=ret,
                price=record["total"] / max(request.passengers, 1),
                currency=request.currency,
                airline=record.get("airline"),
                transfers=record.get("stops_out"),
                return_transfers=record.get("stops_back"),
                link=record.get("link"),
            )
            matrix.cells[(depart, ret)] = cell
        cell.verified = True
        cell.verified_total = record["total"]
        cell.verified_at = record.get("fetched_at")
        if record.get("link"):
            cell.link = record["link"]


def build(
    request: SearchRequest,
    provider: Any = None,
    on_event: Callable[[dict[str, Any]], None] | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield board events: `meta`, then one `destination` per grid, then `done`."""
    # Status messages from the provider (rate-limit waits) are queued here and drained
    # into the event stream, so a pause is visible rather than looking like a hang.
    provider = provider or make_board_provider()
    depart_dates, return_dates = date_axes(request)

    def emit(event: dict[str, Any]) -> dict[str, Any]:
        if on_event:
            on_event(event)
        return event

    # Provider status (rate-limit waits) goes straight out so a pause is visible while it
    # is happening, not after the blocking call returns. The API layer sets this to push
    # onto the live stream; otherwise fall back to the generator's own emit.
    if hasattr(provider, "on_status") and provider.on_status is None:
        provider.on_status = lambda m: emit({"type": "provider_status", "message": m})

    yield emit(
        {
            "type": "meta",
            "origin": request.origin.upper(),
            "origin_city": airports.describe(request.origin)["city"],
            "depart_dates": [d.isoformat() for d in depart_dates],
            "return_dates": [d.isoformat() for d in return_dates],
            "adults": request.adults,
            "children": request.children,
            "currency": request.currency,
            "child_factor": config.CHILD_FACTOR,
            "nonstop_only": request.nonstop_only,
            "window_days": request.window_days,
            "window_step": config.WINDOW_STEP,
            "max_window_days": config.MAX_WINDOW_DAYS,
            "date_mode": request.date_mode,
            "nights_span": request.nights_span() if request.is_range else None,
        }
    )

    try:
        candidates = provider.discover(request, depart_dates, return_dates)
    except ProviderError as exc:
        # Kiwi rate-limits bursts and the block lasts minutes. Rather than show an empty
        # board, fall back to the cached source, which is always available.
        fallback = _fallback_provider(provider)
        if fallback is None:
            yield emit({"type": "error", "message": str(exc)})
            return
        yield emit({
            "type": "provider_fallback",
            "message": f"{exc} Falling back to cached estimates for this search.",
        })
        provider = fallback
        try:
            candidates = provider.discover(request, depart_dates, return_dates)
        except ProviderError as exc2:
            yield emit({"type": "error", "message": str(exc2)})
            return

    # Restrict the search itself, not just the view. Filtering here means the destination
    # budget is spent inside the filter: "IT" searches the cheapest Italian cities, rather
    # than finding the cheapest cities anywhere and then hiding the non-Italian ones.
    if request.destination_filter:
        needle = request.destination_filter.strip().lower()
        kept = []
        for code, price in candidates:
            info = _describe(provider, code)
            if destination_matches(needle, code, info.get("city") or "", info.get("country") or ""):
                kept.append((code, price))
        yield emit({
            "type": "filter_applied",
            "filter": request.destination_filter,
            "matched": len(kept),
            "considered": len(candidates),
        })
        candidates = kept

    # Cached coverage is thin, so many candidates come back with an empty grid. Try more
    # than asked for and stop once enough have actually filled.
    budget = max(request.max_destinations, int(request.max_destinations * config.CANDIDATE_MULTIPLIER))
    candidates = candidates[:budget]

    yield emit(
        {
            "type": "candidates",
            "count": len(candidates),
            "target": request.max_destinations,
            "codes": [code for code, _ in candidates],
        }
    )

    if not candidates:
        yield emit(
            {
                "type": "done",
                "destinations": 0,
                "note": (
                    f'Nothing reachable from {request.origin.upper()} matches '
                    f'"{request.destination_filter}". Try a country code (IT), a country '
                    "name (Italy), a city, or clear the box."
                    if request.destination_filter else
                    "Nothing came back for this origin and window. Try a different origin, "
                    "drop the nonstop filter, or move the dates."
                ),
            }
        )
        return

    filled = 0
    empty = 0
    for index, (destination, _seed_price) in enumerate(candidates):
        if filled >= request.max_destinations:
            break
        # Reuse a recent fetch rather than re-querying. Repeat searches are the main way
        # the live provider's rate limit gets tripped, and prices barely move within hours.
        cached = None if request.has_search_filters else cache.get_matrix(
            request.origin, destination, request.currency, depart_dates, return_dates,
            max_age_hours=config.KIWI_CACHE_HOURS, source=getattr(provider, "name", None),
            party=request.party_key,
        )
        # Reuse only a grid that is nearly COMPLETE for this window, judged as a fraction
        # of the valid cells. A flat cell-count threshold silently served half-filled grids:
        # a cache written under an older, narrower fetch strategy (or for a smaller window)
        # easily clears "20 cells" while missing whole diagonals, and would then never be
        # refetched.
        _, valid_cells = cached.coverage(depart_dates, return_dates) if cached else (0, 0)
        complete_enough = (
            cached is not None
            and len(cached.cells) >= config.CACHE_REUSE_MIN_CELLS
            and valid_cells
            and len(cached.cells) / valid_cells >= config.CACHE_REUSE_MIN_FRACTION
        )
        if complete_enough:
            _apply_verified(request, cached, depart_dates, return_dates)
            _prune_to_nights(request, cached)
            info = airports.describe(destination)
            cached.city, cached.country = info["city"], info["country"]
            cached.country_name = airports.country_name(info["country"])
            filled += 1
            checked = _check_headline(request, cached, provider)
            if checked.get("headline_checks") or checked.get("headline_dropped"):
                cache.put_cells(request.origin, destination, request.currency,
                                cached.cells.values(), party=request.party_key)
            payload = cached.to_json(request, depart_dates, return_dates,
                                     config.CHILD_FACTOR, config.STALE_AFTER_HOURS)
            payload.update(checked)
            payload.update({"type": "destination", "index": index,
                            "total_candidates": len(candidates), "from_cache": True})
            yield emit(payload)
            continue

        try:
            matrix = provider.fill_matrix(request, destination, depart_dates, return_dates)
        except ProviderError as exc:
            yield emit({"type": "destination_error", "destination": destination, "message": str(exc)})
            continue
        except Exception:                       # a single bad destination must not kill the board
            yield emit(
                {
                    "type": "destination_error",
                    "destination": destination,
                    "message": traceback.format_exc(limit=1).strip().splitlines()[-1],
                }
            )
            continue

        if not request.has_search_filters:
            cache.put_cells(request.origin, destination, request.currency, matrix.cells.values(),
                        party=request.party_key)
        _apply_verified(request, matrix, depart_dates, return_dates)
        _prune_to_nights(request, matrix)

        info = airports.describe(destination)
        matrix.city, matrix.country = info["city"], info["country"]
        matrix.country_name = airports.country_name(info["country"])

        if not matrix.cells:
            empty += 1
            yield emit({"type": "destination_empty", "destination": destination, "city": info["city"]})
            continue

        filled += 1
        checked = _check_headline(request, matrix, provider)
        payload = matrix.to_json(request, depart_dates, return_dates, config.CHILD_FACTOR, config.STALE_AFTER_HOURS)
        payload.update(checked)
        payload.update({"type": "destination", "index": index, "total_candidates": len(candidates)})
        yield emit(payload)

    yield emit(
        {
            "type": "done",
            "destinations": filled,
            "empty": empty,
            "strategy": provider.strategy,
            "note": _coverage_note(request, filled, provider),
        }
    )


def _coverage_note(request: SearchRequest, filled: int, provider: Any = None) -> str:
    """Advice about the window, which depends on WHICH source filled the board.

    The horizon problem belongs to the *cached* source only. Travelpayouts is a cache of
    other people's searches, so coverage collapses with distance: measured ~43% at two
    weeks out, ~24% at six weeks, ~13% at two months, ~2% at five months.

    Kiwi runs a real search, so it is bounded by how far airlines have loaded schedules,
    not by search popularity. Measured on TLV-ATH: identical coverage (153/197 cells,
    ~70 destinations) at 30, 208 and 330 days out; still partial at 355; empty at 375.
    So a full year ahead works fine and must not be warned about.
    """
    days_out = (parse_date(request.depart_date) - date.today()).days
    live = getattr(provider, "name", None) == "kiwi"

    if not filled:
        if days_out > 360:
            return (f"Departure is {days_out} days out. Airlines only load schedules about "
                    "11-12 months ahead, so there is nothing to price yet. Measured: data "
                    "exists to ~355 days and stops by ~375.")
        return ("Nothing came back for this origin and window. Try a different origin, drop "
                "the nonstop filter, or move the dates.")

    if live:
        if days_out > 330:
            return (f"Departure is {days_out} days out, near the edge of published schedules "
                    "(~355 days), so some routes will be thin.")
        return "Click any cell for the live price with your real passenger mix."

    # Cached source only.
    if days_out > 120:
        return (f"Departure is {days_out} days out and this board came from the cached source, "
                "which only has fares other people recently searched. Live prices are "
                "available at any horizon - click a cell, or use Fill live.")
    if days_out > 60:
        return (f"Departure is {days_out} days out, so the cached source is thin and many cells "
                "will be blank. Click any cell for its live price.")
    return "Click any cell for the live price with your real passenger mix."


def sort_key(destination: dict[str, Any]) -> float:
    """Rank a destination card by the price actually shown on it.

    A verified live total supersedes the estimate, so sorting on `estimate` alone would
    keep a destination near the top after verification proved it expensive.
    """
    best = destination.get("best") or {}
    for field in ("total", "estimate"):
        if best.get(field) is not None:
            return float(best[field])
    return float("inf")


def build_board(request: SearchRequest, provider: TravelpayoutsProvider | None = None) -> dict[str, Any]:
    """Collect the whole board eagerly. Used by the CLI and by the snapshot endpoint."""
    events = list(build(request, provider=provider))
    meta = next((e for e in events if e["type"] == "meta"), {})
    destinations = [e for e in events if e["type"] == "destination"]
    destinations.sort(key=sort_key)
    errors = [e for e in events if e["type"] in ("error", "destination_error")]
    done = next((e for e in events if e["type"] == "done"), {})
    return {"meta": meta, "destinations": destinations, "errors": errors, "done": done}
