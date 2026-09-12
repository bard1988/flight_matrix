"""Board assembly: discover destinations, fill each grid, emit progressively.

Runs as a generator so the API layer can stream one destination card at a time instead of
making the user stare at a spinner until all 20 are done.
"""
from __future__ import annotations

import traceback
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import wait as wait_futures
from datetime import date, timedelta
from typing import Any, Callable, Iterator

import airports
import cache
import config
from models import Cell, DestinationMatrix, SearchRequest, parse_date
from providers.base import ProviderError
from providers import verifier as _verifier_provider
from providers.kiwi import KiwiProvider
from providers.travelpayouts import TravelpayoutsProvider


def make_board_provider():
    """Kiwi by default: it returns real party totals rather than single-adult estimates."""
    if config.BOARD_PROVIDER == "travelpayouts":
        return TravelpayoutsProvider()
    return KiwiProvider()


_airline_singletons: dict[str, Any] = {}


def _airline(name: str) -> Any:
    """Lazily build one direct-carrier provider, shared across searches."""
    if name not in _airline_singletons:
        if name == "wizz":
            from providers.wizz import WizzProvider
            _airline_singletons[name] = WizzProvider()
        elif name == "ryanair":
            from providers.ryanair import RyanairProvider
            _airline_singletons[name] = RyanairProvider()
        else:
            _airline_singletons[name] = None
    return _airline_singletons[name]


def _airlines() -> list[Any]:
    """Direct-carrier sources, layered onto discovery and used to fill a grid the
    aggregators leave empty on a route the carrier flies. Each exposes routes(origin),
    serves(origin, dest) and fill_matrix(); Ryanair adds discover()."""
    names = []
    if config.WIZZ_ENABLED:
        names.append("wizz")
    if config.RYANAIR_ENABLED:
        names.append("ryanair")
    return [a for a in (_airline(n) for n in names) if a is not None]


def _base_provider(live: Any):
    """The source that paints the board first.

    Returns `live` unchanged unless ESTIMATE_FIRST is on and there is a cheap source to
    lead with, in which case the caller's expensive provider is held back for the upgrade
    pass. Falls through to `live` when there is no token, because an estimate-first board
    with no estimates source is just a slower Kiwi board.
    """
    if not config.ESTIMATE_FIRST or not config.TRAVELPAYOUTS_TOKEN:
        return live
    if getattr(live, "name", None) != "kiwi":
        return live          # already the cheap source, or a demo/test double
    return TravelpayoutsProvider()


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


def _seed_candidates(
    request: SearchRequest,
    have: set[str],
    depart_dates: list[date],
    return_dates: list[date],
    codes: list[str] | None = None,
) -> tuple[list[tuple[str, float]], int]:
    """Discovery top-up for a region filter the board provider under-served (idea.md #15A).

    Take the best hubs in the selected countries (OurAirports, `airports.shortlist`), drop
    the ones discovery already found, and probe each with one Google Flights lookup on a
    representative date pair near the middle of the window. Google prices the routes the
    board's cache-shaped discovery never surfaces (TLV -> Nairobi / Zanzibar / Cape Town),
    and returns a real party total. Keep the ones that price.

    Returns `([(code, party_total), ...] cheapest first, airports_probed)`.
    """
    if config.SEED_SHORTLIST <= 0 and codes is None:
        return [], 0
    origin = request.origin.upper()
    dead = cache.unpriceable_destinations(
        origin, request.adults, request.children, request.currency)
    # An explicit `codes` list (the typeahead's picked airports) is probed as given -- the
    # user asked for these by name, so they are not subject to the shortlist cap or the
    # "unpriceable" skip. Otherwise fall back to the region's best hubs, best-first
    # (`airports.shortlist` already orders large before medium).
    source = codes if codes is not None else airports.shortlist(
        request.country_codes, config.SEED_SHORTLIST)
    shortlist = [
        code for code in source
        if code.upper() != origin and (codes is not None or (
            code.upper() not in have and code.upper() not in dead))
    ]
    if not shortlist:
        return [], 0

    # One representative pair near the middle of the window: mid departure, and a return
    # that honours the requested trip length -- an arbitrary "+7 return rows" pick landed a
    # 14-night search on a 20-night pair, so a route only sold at the asked length probed
    # empty and got dropped.
    #
    # The trip length itself is the nights *closest to a week* within the span, not the
    # span's raw median: a "Flexible" search (idea.md's own 3-21 preset) medians out to
    # ~12 nights, and 12 is a materially less commonly sold length than 7 for a real
    # scheduled route. Measured directly against production: TLV -> Nairobi priced fine at
    # 7 nights (4,267) and came back "no itineraries" at 12, on the same departure date --
    # a real, bookable hub excluded from the whole region for no reason but which length
    # the median happened to land on. 7 is still clamped into [lo, hi] so a route only sold
    # at the asked length (the case the median was originally added for) still gets it.
    span = request.nights_span()
    nights = min(span, key=lambda n: abs(n - 7))
    depart = depart_dates[len(depart_dates) // 2]
    target = depart + timedelta(days=nights)
    ret = min(return_dates, key=lambda d: abs((d - target).days))
    if ret <= depart:
        ret = return_dates[-1]
    verifier = _verifier_provider()

    def _probe(code: str) -> tuple[str, float] | None:
        # A single route failing the probe (not in Google's data, a throttle, a blip) must
        # never take the board down with it - just skip that one. But `verify()` raises the
        # same ProviderError for "genuinely no fare" and "the scrape itself failed" (a
        # network blip, a malformed page, one bad Google response) -- measured on a thin
        # region (TLV -> Africa), 36 of 38 hubs came back empty on the first try, which is a
        # steeper coverage gap than the rest of the region's own real air links suggest. One
        # retry costs nothing extra for a route that never had a fare (would still fail) and
        # recovers the ones that were a transient blip, not a real gap.
        for attempt in range(2):
            try:
                result = verifier.verify(origin, code, depart.isoformat(), ret.isoformat(),
                                         request.adults, request.children, request.currency,
                                         request.nonstop_only)
                total = result.get("total")
                return (code.upper(), round(float(total), 2)) if total else None
            except Exception:                   # noqa: BLE001
                if attempt == 1:
                    return None

    # A plain pool.map() blocks for every last one of these, retry included -- on a big,
    # thin region (Africa's 60-hub shortlist, mostly misses at a far-future date) that
    # measured 68 SECONDS before the board could show anything at all. Wait only up to the
    # time budget; whichever probes have not answered by then are abandoned (their thread
    # runs to completion regardless, its result just is not waited for), so the search
    # always moves on with whatever answered in time instead of the single slowest one.
    pool = ThreadPoolExecutor(max_workers=config.FILL_WORKERS)
    futures = [pool.submit(_probe, code) for code in shortlist]
    done, _pending = wait_futures(futures, timeout=config.SEED_TIME_BUDGET)
    pool.shutdown(wait=False)
    results = [f.result() for f in done]
    # `done` is an unordered set (whichever finished first), not shortlist order -- fine,
    # because the caller re-sorts by hub rank then price regardless of what order this
    # returns them in.
    found = [r for r in results if r]
    return found, len(done)   # how many actually answered, not the shortlist size the budget may have cut short


def _hub_rank(code: str) -> int:
    """0 for a large international hub, 1 for a medium airport, 2 for anything else -- used
    to lead a country-filtered board with its major airports rather than its cheapest."""
    return {"large": 0, "medium": 1}.get(airports.describe(code).get("type"), 2)


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

    city_name = (city or "").lower()
    country_name = airports.country_name(country).lower()

    # A short needle is a CODE the user typed, not a fragment of a name, so it may only
    # match where a word begins. The exact-match guard above was not enough on its own:
    # the plain substring fall-through below still put "IT" inside L-it-huania, Un-it-ed
    # Kingdom and Spl-it, so a search for Italy returned Vilnius, London and Split.
    if len(needle) <= 3:
        return any(word.startswith(needle)
                   for word in (city_name + " " + country_name).split())

    return needle in city_name or needle in country_name


def date_axes(request: SearchRequest) -> tuple[list[date], list[date]]:
    """The two date fields bound a period; the axes fall out of it and the nights range."""
    return request.range_axes()


def fill_one(
    request: SearchRequest,
    destination: str,
    provider: Any = None,
) -> dict[str, Any]:
    """Fill (or re-fill, at a wider window) a single destination and return its payload.

    Used by the scroll-to-extend path (`/api/extend`): the nights band or the date window
    grows for whatever is on screen -- one Single card, or every destination in a Multi
    grid -- and each is re-fetched over the larger window, one call per destination.

    Routed through `_base_provider`, same as `build()`'s first pass, and for the same
    reason: called straight against Kiwi this was both much slower than a fresh search (a
    fresh search only *looks* fast because its first paint is the cheap source, with Kiwi
    upgrading destinations afterwards in the background -- this path had no such upgrade
    pass, just the slow source, every time) and, called for several destinations back to
    back, more exposed to Kiwi's rate limiting: a throttled mid-grid response comes back
    with only the columns that finished before the 403, which on a several-destination
    Multi grid read as "only part of the board filled". Getting a real total for a cell
    still goes through the separate per-cell Google verification, not this call.
    """
    live = provider or make_board_provider()
    provider = _base_provider(live)
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
                             config.CHILD_FACTOR, config.STALE_AFTER_HOURS,
                             config.VERIFY_STALE_HOURS)
    payload["type"] = "destination"
    return payload


def _check_headline(request: SearchRequest, matrix: DestinationMatrix) -> dict[str, Any]:
    """Re-price a card's cheapest cell with a real search until the headline is bookable.

    A calendar-sourced price is a precomputed index and individual routes go stale.
    Measured on TLV-CTA (Kiwi's calendar specifically): quoted 773-853 where a full search
    for the same dates returned 1,893-2,003, i.e. +135% to +166%. The link was correct, so
    clicking through showed flights at more than double the quoted price and read as "the
    flight does not exist".

    Checking only once is not enough. Correcting the cheapest cell upward promotes the
    next-cheapest cell to headline, and on a stale route that one is stale by the same
    margin - the first version of this shipped a corrected 1,893 and then displayed 790 from
    an unchecked neighbour. So loop until the cheapest cell is one we priced ourselves, up
    to CHECK_HEADLINE_MAX searches.

    Always goes through the Google verifier (the same one behind /api/verify and the
    open-destination cross-check), never `provider.itinerary_details` (Kiwi-only): this ran
    as `provider.itinerary_details` for years, but ESTIMATE_FIRST's initial pass fills from
    Travelpayouts, which has no such method, so `hasattr` silently no-opped this on every
    search and the very case the docstring above describes shipped unguarded. Using the
    verifier instead of the fill provider also means the correction never depends on which
    one happened to fill the grid, and doesn't add to Kiwi's rate-limit exposure.

    Unlike the old Kiwi path, a miss here is not deleted: Google not covering a route it
    genuinely IS on sale for is common (a whole separate part of the UI exists to say so),
    so treating "Google found nothing" as "this trip cannot be booked" would drop cells that
    are actually fine.
    """
    if not config.CHECK_HEADLINE:
        return {}
    verifier = _verifier_provider()

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
            real = verifier.verify(
                request.origin, matrix.destination, best.depart_date, best.return_date,
                request.adults, request.children, request.currency, request.nonstop_only)
        except ProviderError:
            break                     # rate limit, transport, or genuinely no fare found
        if real.get("total") is None:
            break
        checks += 1
        best.price = float(real["total"])
        best.is_total = True
        best.checked = True
        if real.get("stops_out") is not None:
            best.transfers = real["stops_out"]
        best.airline = real.get("airline") or best.airline

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
    """Keep only the trip lengths that were actually asked for.

    Verified cells accumulate across searches and are overlaid by date, so without this a
    "3-4 nights" board picks up stray 9- and 14-night cells from earlier work.
    """
    wanted = set(request.nights_span())
    for key in [k for k, cell in matrix.cells.items() if cell.nights not in wanted]:
        del matrix.cells[key]


def _apply_verified(
    request: SearchRequest,
    matrix: DestinationMatrix,
    depart_dates: list[date] | None = None,
    return_dates: list[date] | None = None,
    verified: dict[tuple[str, str, str], dict[str, Any]] | None = None,
) -> None:
    """Overlay previously verified live totals onto this window's cells.

    The window bounds are required: verified rows accumulate across every search ever run
    for this origin, so without them a board for next April would inherit prices verified
    for this October, inflating the cell count past the grid size and hijacking the
    headline price.

    `verified` is the whole origin's verified set. It does not vary by destination, so a
    board build reads it ONCE and passes it in; looking it up per destination re-ran the
    same query 20 times per board for an identical result (measured: 15 ms a time).
    """
    bounds = None
    if depart_dates and return_dates:
        bounds = (depart_dates[0].isoformat(), depart_dates[-1].isoformat(),
                  return_dates[0].isoformat(), return_dates[-1].isoformat())

    if verified is None:
        verified = cache.get_all_verified(
            request.origin, request.adults, request.children, request.currency)
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
                # No link. Cell.link is the BOOKING deeplink, and the panel labels it with
                # the fare's own source; the record's link points at Google Flights, which
                # reaches the frontend separately from /api/verify.
            )
            matrix.cells[(depart, ret)] = cell
        cell.verified = True
        cell.verified_total = record["total"]
        cell.verified_at = record.get("fetched_at")
        # Staleness for a verified cell tracks the verification, not the estimate behind
        # it: the number on screen is `verified_total`, so `found_at` is when THAT was
        # checked. A verification older than VERIFY_FRESH_MINUTES then shows the stale
        # marker and the background cross-check re-runs it.
        cell.found_at = record.get("fetched_at")
        # record["link"] is deliberately NOT copied onto cell.link. It used to be, so a
        # verified Travelpayouts cell offered "Book on Aviasales" pointing at Google
        # Flights: the booking deeplink was destroyed and the Google link served twice,
        # once under the wrong name.


def cells_event(request: SearchRequest, destination: str, cells: list[Cell]) -> dict[str, Any]:
    """One streamed calendar column, shaped like the cells inside a destination payload.

    Kept here rather than in the API layer so a cell is serialised by the same code and
    the same child-factor and staleness rules whether it arrives live or in the settled
    board. The frontend merges these into the card by date pair.
    """
    return {
        "type": "cells",
        "destination": destination.upper(),
        "cells": [c.to_json(request, config.CHILD_FACTOR, config.STALE_AFTER_HOURS,
                            config.VERIFY_STALE_HOURS)
                  for c in cells],
    }


def _preview_payload(
    request: SearchRequest,
    provider: Any,
    destination: str,
    seed_price: float,
    index: int,
    total: int,
) -> dict[str, Any]:
    """A destination card carrying only the headline price discovery already returned.

    Discovery prices the real passenger mix, so `preview_price` is a party total for a trip
    that exists - it is simply not yet attributable to a date PAIR, because the discovery
    query returns a departure date and a price and no return date. Rather than infer the
    return (the mistake that put unbookable prices on the board once already, see
    `_return_column`), the preview carries no cells and no `best`, and the UI labels it as
    still finding dates. The grid fill replaces this card wholesale a moment later.
    """
    info = _describe(provider, destination)
    country = info.get("country") or ""
    return {
        "type": "destination",
        "preview": True,
        "origin": request.origin.upper(),
        "destination": destination.upper(),
        "city": info.get("city") or destination.upper(),
        "country": country,
        "country_name": airports.country_name(country),
        "best": None,
        "preview_price": round(float(seed_price), 2),
        "currency": request.currency,
        "coverage": {"populated": 0, "valid": 0},
        "cells": [],
        "index": index,
        "total_candidates": total,
    }


def build(
    request: SearchRequest,
    provider: Any = None,
    on_event: Callable[[dict[str, Any]], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield board events: `meta`, then one `destination` per grid, then `done`.

    `should_stop` is polled between destinations; when it returns True the build ends
    early with a `done` event carrying whatever filled so far (`stopped: True`).
    """
    stopped = False
    # Status messages from the provider (rate-limit waits) are queued here and drained
    # into the event stream, so a pause is visible rather than looking like a hang.
    #
    # `live` is the good-but-expensive source the caller handed us, already wired for
    # status and live-cell streaming. `provider` is what actually paints the board. Under
    # ESTIMATE_FIRST those are different: a cheap source fills every card fast and `live`
    # comes back afterwards to upgrade the grids (see the upgrade pass at the end).
    live = provider or make_board_provider()
    provider = _base_provider(live)
    upgrade_with = live if provider is not live else None
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

    # Live grid fill is NOT wired here. `emit` routes through `on_event`, and the API layer
    # consumes this generator without passing one (passing it would double-deliver every
    # yielded event). So, exactly like provider_status, the caller sets `provider.on_cells`
    # itself and uses `cells_event` below to build the payload. The CLI and the snapshot
    # endpoint set nothing and never stream, which is what they want.

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
            "nights_span": request.nights_span(),
        }
    )

    if should_stop and should_stop():
        yield emit({"type": "done", "destinations": 0, "empty": 0, "stopped": True,
                    "strategy": getattr(provider, "strategy", "unknown"),
                    "note": "Stopped before any destination was priced."})
        return

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

    # Direct-carrier sources (Wizz, Ryanair), layered onto discovery for the routes each
    # flies from this origin. The aggregators share one GDS+NDC+LCC pool that thins out for
    # small routes booked far ahead (a TLV -> Iasi trip 7 months out came back empty from
    # all of them while Wizz was selling it), and from a Ryanair base it can be most of the
    # board. Ryanair's discover() gives real round-trip prices for its cheapest dozen;
    # everything else is priced at the median so it neither leads nor is cut before its
    # grid fills and re-ranks it.
    airlines = _airlines()
    for air in airlines:
        try:
            routes = list(air.routes(request.origin))
        except Exception:                       # noqa: BLE001 -- a carrier outage must not stop the board
            routes = []
        if not routes:
            continue
        priced: dict[str, float] = {}
        if hasattr(air, "discover"):
            try:
                priced = {c.upper(): p for c, p in air.discover(request, depart_dates, return_dates)}
            except Exception:                   # noqa: BLE001
                priced = {}
        have = {code.upper() for code, _ in candidates}
        prices = sorted(p for _, p in candidates if p and p < 10 ** 8)
        placeholder = prices[len(prices) // 2] if prices else 1.0
        added = [(code, priced.get(code.upper(), placeholder)) for code in routes
                 if code.upper() not in have and code.upper() != request.origin.upper()]
        if added:
            candidates = candidates + added
            yield emit({"type": "airline_routes", "airline": air.name, "added": len(added)})

    # Region tree: restrict to the selected countries, at discovery so the budget is spent
    # inside the selection (like destination_filter). Both filters compose.
    if request.country_codes:
        allowed = {c.upper() for c in request.country_codes}
        kept = [(code, price) for code, price in candidates
                if (_describe(provider, code).get("country") or "").upper() in allowed]
        yield emit({
            "type": "region_filtered",
            "countries": len(allowed),
            "matched": len(kept),
            "considered": len(candidates),
        })
        candidates = kept

        # The board provider's "where can I go" is short/medium-haul heavy: a TLV -> Africa
        # search finds ~1 city because Kiwi's board just does not carry Nairobi / Zanzibar /
        # Cape Town for TLV. If the region filter left us short, probe a curated shortlist
        # of that region's real hubs for a live fare and fold in the ones that fly.
        if len(candidates) < request.max_destinations and config.SEED_SHORTLIST > 0:
            have = {code.upper() for code, _ in candidates}
            yield emit({"type": "region_seeding"})
            seeded, probed = _seed_candidates(request, have, depart_dates, return_dates)
            if probed:
                # Rank the region's board by airport importance first (Bangkok before
                # Buri Ram), fare second -- a country search should lead with that
                # country's real hubs. The client list re-sorts by fare regardless.
                merged = {c.upper(): (c, p) for c, p in candidates}
                for c, p in seeded:
                    merged.setdefault(c.upper(), (c, p))
                candidates = sorted(merged.values(), key=lambda cp: (_hub_rank(cp[0]), cp[1]))
                yield emit({
                    "type": "region_seeded",
                    "probed": probed,
                    "added": len(seeded),
                    "matched": len(candidates),
                })

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

    # Typeahead picks: the exact airports the user chose. With a country filter too, these
    # are added to the country matches; on their own, the board IS just these. Any the
    # board provider did not surface are probed live so a picked airport always shows.
    if request.destination_codes:
        picked = {c.upper() for c in request.destination_codes}
        if request.country_codes:
            keep_codes = {c.upper() for c, _ in candidates} | picked
            candidates = [(c, p) for c, p in candidates if c.upper() in keep_codes]
        else:
            candidates = [(c, p) for c, p in candidates if c.upper() in picked]
        have = {c.upper() for c, _ in candidates}
        missing = [c for c in picked if c not in have]
        if missing:
            yield emit({"type": "region_seeding"})
            seeded, probed = _seed_candidates(request, have, depart_dates, return_dates, codes=missing)
            seeded_codes = {c for c, _ in seeded}
            # A picked airport the live probe could not price is still added -- the user
            # asked for it by name. It sorts last (unknown seed price) and the normal board
            # fill tries the board source; a truly unreachable route just gets an empty grid.
            forced = [(c, 10 ** 9) for c in missing if c not in seeded_codes]
            candidates = sorted(candidates + seeded + forced, key=lambda kv: kv[1])
            yield emit({"type": "region_seeded", "probed": probed,
                        "added": len(seeded) + len(forced), "matched": len(candidates)})

    # Cached coverage is thin, so many candidates come back with an empty grid. Try more
    # than asked for and stop once enough have actually filled.
    budget = max(request.max_destinations, int(request.max_destinations * config.CANDIDATE_MULTIPLIER))
    if request.destination_codes:
        picked = {c.upper() for c in request.destination_codes}
        head = [cp for cp in candidates if cp[0].upper() in picked]
        rest = [cp for cp in candidates if cp[0].upper() not in picked]
        candidates = head + rest[:max(0, budget - len(head))]
    else:
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
                    "Nothing reachable from here is in the regions you picked. Widen the "
                    "region selection or clear it."
                    if request.country_codes else
                    "Nothing came back for this origin and window. Try a different origin, "
                    "drop the nonstop filter, or move the dates."
                ),
            }
        )
        return

    # Headline-only cards for everything we are about to price, so the ranked list is on
    # screen after one call instead of after the whole board. Only as many as will actually
    # be filled: `candidates` is over-fetched by CANDIDATE_MULTIPLIER, and previewing a
    # destination the loop never reaches would leave a card stuck at "finding dates".
    if config.PREVIEW_FIRST:
        for index, (destination, seed_price) in enumerate(candidates[:request.max_destinations]):
            yield emit(_preview_payload(request, provider, destination, seed_price,
                                        index, len(candidates)))

    # Read once for the whole board rather than once per destination: the verified set is
    # keyed by origin and passenger mix, not by destination.
    verified = cache.get_all_verified(
        request.origin, request.adults, request.children, request.currency)

    filled = 0
    empty = 0
    airline_fills = 0   # grids filled direct from a carrier because the aggregator had none
    failovers = 0        # destinations that fell back to the cached source mid-board
    real_totals = 0      # destinations filled with genuine party totals (not estimates)
    filled_matrices: list[tuple[str, DestinationMatrix]] = []   # for the headline pass below
    for index, (destination, _seed_price) in enumerate(candidates):
        if filled >= request.max_destinations:
            break
        if should_stop and should_stop():
            stopped = True
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
        # `nights` is required. Without it coverage counts the whole depart <= return
        # triangle, but only the trip lengths in the nights range are askable, so a
        # COMPLETE grid scored 115/435 = 0.26 and never cleared CACHE_REUSE_MIN_FRACTION.
        # The effect was that no Kiwi grid was ever reused: every repeat search refetched
        # the whole board, which is precisely what the cache exists to prevent (and the
        # main way the rate limit gets tripped). `coverage` warns about this in its own
        # docstring; `to_json` already passes it.
        _, valid_cells = (
            cached.coverage(depart_dates, return_dates, nights=request.nights_span())
            if cached else (0, 0)
        )
        complete_enough = (
            cached is not None
            and len(cached.cells) >= config.CACHE_REUSE_MIN_CELLS
            and valid_cells
            and len(cached.cells) / valid_cells >= config.CACHE_REUSE_MIN_FRACTION
        )
        if complete_enough:
            _apply_verified(request, cached, depart_dates, return_dates, verified)
            _prune_to_nights(request, cached)
            info = airports.describe(destination)
            cached.city, cached.country = info["city"], info["country"]
            cached.country_name = airports.country_name(info["country"])
            filled += 1
            if getattr(provider, "name", "") == "kiwi":
                real_totals += 1
            filled_matrices.append((destination, cached))
            payload = cached.to_json(request, depart_dates, return_dates,
                                     config.CHILD_FACTOR, config.STALE_AFTER_HOURS,
                                     config.VERIFY_STALE_HOURS)
            payload.update({"type": "destination", "index": index,
                            "total_candidates": len(candidates), "from_cache": True})
            yield emit(payload)
            continue

        try:
            matrix = provider.fill_matrix(request, destination, depart_dates, return_dates)
        except ProviderError:
            matrix = None
        except Exception:                       # a single bad destination must not kill the board
            yield emit(
                {
                    "type": "destination_error",
                    "destination": destination,
                    "message": traceback.format_exc(limit=1).strip().splitlines()[-1],
                }
            )
            continue

        # Kiwi threw, or throttled part way through this grid (fill_matrix swallows the
        # 403 and just returns fewer cells, setting `rate_limited`). Either way, hand the
        # rest of the board to the cached source rather than grind through every remaining
        # destination at Kiwi's pace. Destinations already filled from Kiwi keep their real
        # party totals; the new ones are estimates whose cheapest cells the live
        # cross-check still corrects.
        if getattr(provider, "name", "") == "kiwi" and (
            matrix is None or getattr(provider, "rate_limited", False)
        ):
            fb = _fallback_provider(provider)
            if fb is None:
                if matrix is None:
                    yield emit({"type": "destination_error", "destination": destination,
                                "message": "Kiwi unavailable and no cached fallback configured."})
                    continue
            else:
                provider = fb
                if not failovers:
                    yield emit({
                        "type": "provider_fallback",
                        "message": ("Kiwi is rate-limiting - the rest of the board uses "
                                    "cached estimates; each card's cheapest cells are "
                                    "still cross-checked live."),
                    })
                failovers += 1
                try:
                    matrix = provider.fill_matrix(request, destination, depart_dates, return_dates)
                except Exception as exc2:
                    yield emit({"type": "destination_error", "destination": destination,
                                "message": str(exc2)})
                    continue

        if matrix is not None:
            # Cache the full aggregator grid, then narrow it to the asked trip lengths.
            # Order matters: the carrier fallback below has to see the POST-prune grid, or a
            # route the aggregator carries only at other lengths silently skips it.
            if not request.has_search_filters:
                cache.put_cells(request.origin, destination, request.currency,
                                matrix.cells.values(), party=request.party_key)
            _apply_verified(request, matrix, depart_dates, return_dates, verified)
            _prune_to_nights(request, matrix)

        # Nothing from the aggregator at the asked trip length. If a direct carrier flies
        # this route, fill the grid from its own calendar instead (carrier cells are
        # already cut to the nights range).
        if (matrix is None or not matrix.cells) and airline_fills < config.AIRLINE_FILL_CAP:
            for air in airlines:
                if not air.serves(request.origin, destination):
                    continue
                try:
                    am = air.fill_matrix(request, destination, depart_dates, return_dates)
                except ProviderError as exc:
                    yield emit({"type": "provider_status", "message": f"{air.name}: {exc}"})
                    continue
                airline_fills += 1
                if am is not None and am.cells:
                    matrix = am
                    _apply_verified(request, matrix, depart_dates, return_dates, verified)
                    yield emit({"type": "airline_fill", "airline": air.name,
                                "destination": destination, "cells": len(am.cells)})
                    break

        if matrix is None:
            yield emit({"type": "destination_error", "destination": destination,
                        "message": "no data for this destination"})
            continue

        info = airports.describe(destination)
        matrix.city, matrix.country = info["city"], info["country"]
        matrix.country_name = airports.country_name(info["country"])

        if not matrix.cells:
            empty += 1
            # A destination the user named explicitly (typeahead pick) that comes back with
            # nothing needs to say so -- otherwise a one-destination search just vanishes.
            picked = destination.upper() in {c.upper() for c in request.destination_codes}
            yield emit({"type": "destination_empty", "destination": destination,
                        "city": info["city"], "picked": picked})
            continue

        filled += 1
        if getattr(provider, "name", "") == "kiwi":
            real_totals += 1
        filled_matrices.append((destination, matrix))
        payload = matrix.to_json(request, depart_dates, return_dates, config.CHILD_FACTOR,
                                 config.STALE_AFTER_HOURS, config.VERIFY_STALE_HOURS)
        payload.update({"type": "destination", "index": index, "total_candidates": len(candidates)})
        yield emit(payload)

    # ------------------------------------------------------------- headline check pass
    #
    # The board's leading price is the one a user actually acts on, so it gets its own
    # check -- separate from, and before, the slower Kiwi upgrade pass below. Runs after
    # every destination is already on screen, so it never delays a destination's first
    # appearance the way checking inline (the old behaviour) would: for max_destinations
    # cards that is one extra sequential Google lookup apiece, which measured as the
    # whole board taking noticeably longer to finish -- exactly the latency ESTIMATE_FIRST
    # exists to avoid. A correction streams back as an updated 'destination' event,
    # marked headline_update so the client applies it without bumping the progress count.
    if filled_matrices and not stopped:
        for destination, matrix in filled_matrices:
            if should_stop and should_stop():
                stopped = True
                break
            checked = _check_headline(request, matrix)
            if not checked.get("headline_checks"):
                continue
            if not request.has_search_filters:
                cache.put_cells(request.origin, destination, request.currency,
                                matrix.cells.values(), party=request.party_key)
            payload = matrix.to_json(request, depart_dates, return_dates, config.CHILD_FACTOR,
                                     config.STALE_AFTER_HOURS, config.VERIFY_STALE_HOURS)
            payload.update(checked)
            payload.update({"type": "destination", "headline_update": True,
                            "total_candidates": len(candidates)})
            yield emit(payload)

    # ---------------------------------------------------------------- upgrade pass
    #
    # Every card now carries an estimate. Come back with the expensive source and replace
    # those grids with real party totals, cheapest destination first, streaming each
    # calendar column as it lands so the upgrade is visible rather than a second wait.
    #
    # This is the whole point of leading with estimates: the board is already usable, so
    # the moment Kiwi pushes back we stop and keep what we have. The old order spent the
    # rate limit BEFORE there was anything on screen, which is how a 403 turned into a
    # board made of estimates rather than a board made of estimates plus some real prices.
    upgraded = 0
    if upgrade_with is not None and filled and not stopped:
        yield emit({
            "type": "provider_status",
            "message": f"{filled} destinations priced from cached estimates. "
                       "Upgrading to live Kiwi prices, cheapest first.",
        })
        for destination in [d for d, _ in candidates][:request.max_destinations]:
            if should_stop and should_stop():
                stopped = True
                break
            try:
                fresh = upgrade_with.fill_matrix(request, destination, depart_dates, return_dates)
            except ProviderError:
                yield emit({
                    "type": "provider_status",
                    "message": "Kiwi is unavailable, so the board keeps its cached "
                               "estimates. Click any cell for a live price.",
                })
                break
            if getattr(upgrade_with, "rate_limited", False):
                yield emit({
                    "type": "provider_status",
                    "message": f"Kiwi started rate-limiting after {upgraded} upgrade(s). "
                               "The rest of the board keeps its estimates.",
                })
                break
            if not fresh.cells:
                continue
            _prune_to_nights(request, fresh)
            if not request.has_search_filters:
                cache.put_cells(request.origin, destination, request.currency,
                                fresh.cells.values(), party=request.party_key)
            upgraded += 1
            # The cells already streamed to the client through the provider's on_cells
            # hook as each column landed; nothing more to emit per destination here.

    if stopped:
        done_note = f"Stopped - showing the {filled} destination(s) filled so far."
    elif upgraded:
        done_note = (
            f"{upgraded} of {filled} destinations upgraded to live Kiwi prices; the rest "
            "are cached estimates. Click any cell for a live price."
            if upgraded < filled else
            "Click any cell for the live price with your real passenger mix."
        )
    elif failovers:
        estimated = max(0, filled - real_totals)
        done_note = (
            f"Kiwi rate-limited part way through: {real_totals} destination(s) have real "
            f"party totals, {estimated} use cached estimates. Click a cell, or use Fill "
            "live, to price the estimates for real."
        )
    else:
        done_note = _coverage_note(request, filled, provider)

    yield emit(
        {
            "type": "done",
            "destinations": filled,
            "empty": empty,
            "stopped": stopped,
            "failovers": failovers,
            "strategy": provider.strategy,
            "note": done_note,
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
    # A preview card has no cells yet, but discovery already priced it, so rank it on that
    # rather than dumping every unfilled destination at the bottom of the list.
    if destination.get("preview_price") is not None:
        return float(destination["preview_price"])
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
