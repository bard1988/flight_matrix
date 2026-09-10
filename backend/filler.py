"""Bulk-fill a destination's whole grid with live Google Flights prices.

Why this exists: the cached Travelpayouts board is thin (43% coverage at two weeks out,
2% at five months) and its estimates run ~30% optimistic. Google Flights is keyless and
unlimited, and measured at concurrency 4 it returns a cell in ~1s with no failures, so a
full 197-cell grid takes about a minute. That is strictly better data than any additional
cached provider could give: 100% coverage AND true prices for the real passenger mix.

Deliberately per-destination and user-triggered rather than automatic for the whole board,
so we never fire thousands of requests nobody asked for.
"""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from typing import Any, Callable, Iterator

import cache
import config
from models import SearchRequest
from providers.base import ProviderError
from providers import verifier as _verifier_provider


def pending_cells(
    request: SearchRequest,
    destination: str,
    depart_dates: list[date],
    return_dates: list[date],
    skip_verified: bool = True,
) -> list[tuple[str, str]]:
    """Every valid (departure, return) pair not already verified for this passenger mix."""
    done = set()
    if skip_verified:
        done = {
            (d, r)
            for (dest, d, r) in cache.get_all_verified(
                request.origin, request.adults, request.children, request.currency
            )
            if dest == destination.upper()
        }
    pairs = []
    for depart in depart_dates:
        for ret in return_dates:
            if ret < depart:
                continue
            pair = (depart.isoformat(), ret.isoformat())
            if pair not in done:
                pairs.append(pair)
    return pairs


def verify_cells(
    request: SearchRequest,
    targets: list[tuple[str, str, str]],
    workers: int | None = None,
    should_stop: Callable[[], bool] | None = None,
    label: str = "auto",
) -> Iterator[dict[str, Any]]:
    """Live-price an explicit list of (destination, depart, return) cells.

    Used to upgrade a Kiwi board to Google Flights prices in the background. The caller
    chooses the order, and sends the cheapest cells first: those are the ones a booking
    decision turns on, and the ones where a headline fare is most likely to not survive
    contact with five passengers.
    """
    workers = workers or config.FILL_WORKERS
    already = cache.get_all_verified(request.origin, request.adults, request.children, request.currency)
    # Routes Google has never once managed to price: stop spending the budget on them.
    dead = cache.unpriceable_destinations(
        request.origin, request.adults, request.children, request.currency
    )
    pending = [
        t for t in targets
        if (t[0].upper(), t[1], t[2]) not in already and t[0].upper() not in dead
    ]

    yield {"type": "fill_start", "total_cells": len(pending), "workers": workers,
           "label": label, "skipped_routes": sorted(dead)}
    if not pending:
        yield {"type": "fill_done", "filled": 0, "failed": 0, "label": label,
               "note": "Every one of those cells was already verified."}
        return

    provider = _verifier_provider()
    lock = threading.Lock()
    filled = failed = 0

    def one(target: tuple[str, str, str]) -> dict[str, Any]:
        destination, depart, ret = target
        base = {
            "origin": request.origin.upper(), "destination": destination.upper(),
            "depart_date": depart, "return_date": ret,
            "adults": request.adults, "children": request.children,
            "currency": request.currency,
        }
        try:
            result = provider.verify(
                origin=request.origin, destination=destination,
                depart_date=depart, return_date=ret,
                adults=request.adults, children=request.children,
                currency=request.currency, nonstop_only=request.nonstop_only,
            )
        except ProviderError as exc:
            with lock:
                cache.put_verified({**base, "total": None, "airline": None, "stops_out": None,
                                    "stops_back": None, "duration": None, "link": None,
                                    "error": str(exc)})
            return {"type": "fill_cell", "ok": False, **base, "error": str(exc)}

        with lock:
            cache.put_verified({
                **base, "total": result["total"], "airline": result.get("airline"),
                "stops_out": result.get("stops_out"), "stops_back": result.get("stops_back"),
                "duration": result.get("duration"), "link": result.get("link"), "error": None,
            })
        return {"type": "fill_cell", "ok": True, **base, "total": result["total"],
                "airline": result.get("airline"), "stops": result.get("stops_out"),
                "duration": result.get("duration")}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(one, t): t for t in pending}
        for future in as_completed(futures):
            if should_stop and should_stop():
                for f in futures:
                    f.cancel()
                break
            event = future.result()
            if event["ok"]:
                filled += 1
            else:
                failed += 1
            event["progress"] = filled + failed
            event["total_cells"] = len(pending)
            event["label"] = label
            yield event

    yield {"type": "fill_done", "filled": filled, "failed": failed, "label": label,
           "note": f"{filled} cells priced live" + (f", {failed} unavailable" if failed else "")}


def fill(
    request: SearchRequest,
    destination: str,
    depart_dates: list[date],
    return_dates: list[date],
    workers: int | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield one event per cell as it lands, then a summary.

    Results are written to the verified cache as they arrive, so a cancelled or crashed
    fill still keeps everything it managed to fetch.
    """
    workers = workers or config.FILL_WORKERS
    pairs = pending_cells(request, destination, depart_dates, return_dates)
    total = len(pairs)
    # NOTE: the progress denominator is `total_cells`, never `total`. `total` on a
    # fill_cell event is the itinerary PRICE, and overloading the name silently painted
    # the cell count into every cell on the board.
    yield {"type": "fill_start", "destination": destination.upper(),
           "total_cells": total, "workers": workers}
    if not total:
        yield {"type": "fill_done", "destination": destination.upper(), "filled": 0, "failed": 0,
               "note": "Every cell for this destination is already verified."}
        return

    provider = _verifier_provider()
    lock = threading.Lock()
    filled = failed = 0

    def one(pair: tuple[str, str]) -> dict[str, Any]:
        depart, ret = pair
        base = {
            "origin": request.origin.upper(),
            "destination": destination.upper(),
            "depart_date": depart,
            "return_date": ret,
            "adults": request.adults,
            "children": request.children,
            "currency": request.currency,
        }
        try:
            result = provider.verify(
                origin=request.origin, destination=destination,
                depart_date=depart, return_date=ret,
                adults=request.adults, children=request.children,
                currency=request.currency, nonstop_only=request.nonstop_only,
            )
        except ProviderError as exc:
            record = {**base, "total": None, "airline": None, "stops_out": None,
                      "stops_back": None, "duration": None, "link": None, "error": str(exc)}
            with lock:
                cache.put_verified(record)
            return {"type": "fill_cell", "ok": False, **base, "error": str(exc)}

        record = {
            **base,
            "total": result["total"], "airline": result.get("airline"),
            "stops_out": result.get("stops_out"), "stops_back": result.get("stops_back"),
            "duration": result.get("duration"), "link": result.get("link"), "error": None,
        }
        with lock:
            cache.put_verified(record)
        return {
            "type": "fill_cell", "ok": True, **base,
            "total": result["total"], "airline": result.get("airline"),
            "stops": result.get("stops_out"), "duration": result.get("duration"),
        }

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(one, pair): pair for pair in pairs}
        for future in as_completed(futures):
            if should_stop and should_stop():
                for pending in futures:
                    pending.cancel()
                break
            event = future.result()
            if event["ok"]:
                filled += 1
            else:
                failed += 1
            event["progress"] = filled + failed
            event["total_cells"] = total
            yield event

    yield {
        "type": "fill_done",
        "destination": destination.upper(),
        "filled": filled,
        "failed": failed,
        "note": (f"{filled} cells priced live for {request.adults} adults"
                 + (f" + {request.children} children" if request.children else "")
                 + (f", {failed} unavailable" if failed else "")),
    }
