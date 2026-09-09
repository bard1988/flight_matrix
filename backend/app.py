"""FlightMatrix FastAPI layer. Serves the static board and streams destinations as they fill."""
from __future__ import annotations

import asyncio
import json
import os
import queue
import threading
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, PlainTextResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import airports
import board
import cache
import config
import filler
from models import SearchRequest
from providers.base import ProviderError
from providers.google_flights import GoogleFlightsProvider, google_flights_url
from providers.kiwi import proxy_status as kiwi_proxy_status
from providers.travelpayouts import TravelpayoutsProvider

app = FastAPI(title="FlightMatrix", docs_url="/api/docs")


def _make_provider():
    """Demo mode swaps in synthetic data so the board can be developed without a token."""
    if os.environ.get("FM_DEMO") == "1":
        from providers.demo import DemoProvider

        return DemoProvider()
    return board.make_board_provider()

_verifier = GoogleFlightsProvider()
_streams: dict[str, queue.Queue] = {}
_cancelled: set[str] = set()
_SENTINEL = object()


class SearchBody(BaseModel):
    origin: str = Field(default=config.DEFAULT_ORIGIN, min_length=3, max_length=3)
    depart_date: str
    return_date: str
    adults: int = Field(default=config.DEFAULT_ADULTS, ge=1, le=9)
    children: int = Field(default=config.DEFAULT_CHILDREN, ge=0, le=8)
    currency: str = config.DEFAULT_CURRENCY
    max_destinations: int = Field(default=config.DEFAULT_MAX_DESTINATIONS, ge=1, le=60)
    nonstop_only: bool = False
    max_price: float | None = None
    destination_filter: str = Field(default="", max_length=60)
    country_codes: list[str] = Field(default_factory=list, max_length=260)
    nights_min: int | None = Field(default=None, ge=0, le=60)
    nights_max: int | None = Field(default=None, ge=0, le=60)
    # Time-of-day windows as local hours. Search parameters, not display filters.
    depart_hour_from: int | None = Field(default=None, ge=0, le=23)
    depart_hour_to: int | None = Field(default=None, ge=0, le=23)
    return_hour_from: int | None = Field(default=None, ge=0, le=23)
    return_hour_to: int | None = Field(default=None, ge=0, le=23)

    def _pair(self, lo: int | None, hi: int | None) -> tuple[int, int] | None:
        if lo is None and hi is None:
            return None
        return (0 if lo is None else lo, 23 if hi is None else hi)

    def to_request(self) -> SearchRequest:
        return SearchRequest(
            origin=self.origin.upper(),
            depart_date=self.depart_date,
            return_date=self.return_date,
            adults=self.adults,
            children=self.children,
            currency=self.currency.lower(),
            max_destinations=self.max_destinations,
            nonstop_only=self.nonstop_only,
            max_price=self.max_price,
            destination_filter=self.destination_filter,
            country_codes=[c.strip().upper() for c in self.country_codes if c and c.strip()],
            nights_min=self.nights_min,
            nights_max=self.nights_max,
            depart_hours=self._pair(self.depart_hour_from, self.depart_hour_to),
            return_hours=self._pair(self.return_hour_from, self.return_hour_to),
        )


class VerifyBody(BaseModel):
    origin: str
    destination: str
    depart_date: str
    return_date: str
    adults: int = Field(default=2, ge=1, le=9)
    children: int = Field(default=0, ge=0, le=8)
    currency: str = config.DEFAULT_CURRENCY
    nonstop_only: bool = False
    force: bool = False


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "token_configured": bool(config.TRAVELPAYOUTS_TOKEN) or os.environ.get("FM_DEMO") == "1",
        "demo": os.environ.get("FM_DEMO") == "1",
        "child_factor": config.CHILD_FACTOR,
        "kiwi_proxy": kiwi_proxy_status(),
        "defaults": {
            "origin": config.DEFAULT_ORIGIN,
            "currency": config.DEFAULT_CURRENCY,
            "adults": config.DEFAULT_ADULTS,
            "children": config.DEFAULT_CHILDREN,
            "max_destinations": config.DEFAULT_MAX_DESTINATIONS,
        },
    }


def _run_search(search_id: str, request: SearchRequest) -> None:
    """Background worker. Pushes each board event onto the stream queue."""
    channel = _streams[search_id]
    collected: list[dict[str, Any]] = []
    provider = _make_provider()
    # Push rate-limit waits to the client as they happen, so a pause reads as "waiting"
    # rather than "hung".
    if hasattr(provider, "on_status"):
        provider.on_status = lambda m: channel.put({"type": "provider_status", "message": m})
    # Paint each calendar column as it lands rather than only when the whole grid is done.
    # Wired here, not in board.build, because that generator's `emit` needs an `on_event`
    # and passing one would double-deliver every yielded event (see the note there).
    if hasattr(provider, "on_cells"):
        provider.on_cells = lambda dest, cells: channel.put(
            board.cells_event(request, dest, cells))
    try:
        for event in board.build(
            request, provider=provider, should_stop=lambda: search_id in _cancelled
        ):
            # `cells` is a live paint of one calendar column and is superseded by the
            # destination event that follows it. Streaming it is the point; keeping it is
            # not, so it stays out of the snapshot buffer rather than holding a few
            # hundred throwaway payloads in memory for the length of the search.
            if event.get("type") != "cells":
                collected.append(event)
            channel.put(event)
    except Exception as exc:                    # never leave the client hanging
        channel.put({"type": "error", "message": str(exc)})
    finally:
        _cancelled.discard(search_id)
        # Each destination is emitted twice - once as a headline-only preview, then again
        # with its filled grid - and the stream upgrades the card in place. The saved
        # snapshot is a single final board, so keep only the last event per destination or
        # a reopened link would show every city twice, once with an empty grid.
        latest: dict[str, dict[str, Any]] = {}
        for event in collected:
            if event.get("type") == "destination":
                latest[event["destination"]] = event
        destinations = list(latest.values())
        destinations.sort(key=board.sort_key)
        snapshot = {
            "meta": next((e for e in collected if e.get("type") == "meta"), {}),
            "destinations": destinations,
            "errors": [e for e in collected if e.get("type") in ("error", "destination_error")],
            "done": next((e for e in collected if e.get("type") == "done"), {}),
        }
        cache.finish_search(search_id, snapshot)
        channel.put(_SENTINEL)


@app.post("/api/search")
def start_search(body: SearchBody) -> dict[str, str]:
    request = body.to_request()
    search_id = uuid.uuid4().hex[:12]
    cache.create_search(search_id, body.model_dump())
    _cancelled.discard(search_id)
    _streams[search_id] = queue.Queue()
    threading.Thread(target=_run_search, args=(search_id, request), daemon=True).start()
    return {"search_id": search_id}


@app.post("/api/search/{search_id}/cancel")
def cancel_search(search_id: str) -> dict[str, bool]:
    """Stop a running search. It ends at the next destination boundary and emits a
    `done` event with whatever filled so far."""
    _cancelled.add(search_id)
    return {"cancelled": True}


@app.get("/api/search/{search_id}/stream")
async def stream_search(search_id: str) -> StreamingResponse:
    channel = _streams.get(search_id)
    if channel is None:
        raise HTTPException(status_code=404, detail="Unknown or expired search id.")

    async def events():
        loop = asyncio.get_running_loop()
        while True:
            item = await loop.run_in_executor(None, channel.get)
            if item is _SENTINEL:
                yield "event: end\ndata: {}\n\n"
                _streams.pop(search_id, None)
                return
            yield f"data: {json.dumps(item)}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/search/{search_id}")
def search_snapshot(search_id: str) -> dict[str, Any]:
    record = cache.get_search(search_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Unknown search id.")
    return record


@app.post("/api/verify")
def verify(body: VerifyBody) -> dict[str, Any]:
    """One live Google Flights query for a single cell, with the real passenger mix."""
    if not body.force:
        cached = cache.get_verified(
            body.origin, body.destination, body.depart_date, body.return_date,
            body.adults, body.children, body.currency,
        )
        if cached and cached.get("total") is not None:
            # Rebuild the link instead of serving the stored one. It is a pure function of
            # route, dates, party and currency, so caching it buys nothing and goes stale
            # for real: records written before the URL format changed kept handing out the
            # old free-text search, which is the form that opens an empty Flights page.
            return {
                **cached,
                "link": google_flights_url(
                    body.origin, body.destination, body.depart_date, body.return_date,
                    body.adults, body.children, body.currency, body.nonstop_only,
                ),
                "cached": True,
            }

    base = {
        "origin": body.origin.upper(),
        "destination": body.destination.upper(),
        "depart_date": body.depart_date,
        "return_date": body.return_date,
        "adults": body.adults,
        "children": body.children,
        "currency": body.currency,
    }
    try:
        result = _verifier.verify(
            origin=body.origin,
            destination=body.destination,
            depart_date=body.depart_date,
            return_date=body.return_date,
            adults=body.adults,
            children=body.children,
            currency=body.currency,
            nonstop_only=body.nonstop_only,
        )
    except ProviderError as exc:
        record = {
            **base, "total": None, "airline": None, "stops_out": None, "stops_back": None,
            "duration": None,
            "link": google_flights_url(
                body.origin, body.destination, body.depart_date, body.return_date,
                body.adults, body.children, body.currency, body.nonstop_only,
            ),
            "error": str(exc),
        }
        cache.put_verified(record)
        return {**record, "cached": False}

    record = {
        **base,
        "total": result["total"],
        "airline": result.get("airline"),
        "stops_out": result.get("stops_out"),
        "stops_back": result.get("stops_back"),
        "duration": result.get("duration"),
        "departs": result.get("departs"),
        "arrives": result.get("arrives"),
        "segments": result.get("segments"),
        "link": result.get("link"),
        "error": None,
    }
    cache.put_verified(record)
    return {**record, "price_level": result.get("price_level"), "cached": False}


class ExtendBody(BaseModel):
    """Re-price the listed destinations over a WIDER TRAVEL PERIOD.

    depart_date and return_date are the widened period bounds, not anchors and not the
    midpoints of the existing grid. The axes are derived from them together with the nights
    range, exactly as a fresh search would derive them, so the result is the same grid the
    user would get by editing the two date fields and pressing Search.

    nights_min and nights_max are carried for a reason: without them nights_span() falls
    back to its 5-9 default, and the widened board comes back built for a trip length the
    user never asked for. That, plus sending midpoints as the bounds, is what made the old
    widen control shrink a 19x19 board to 6x6.

    The point of this endpoint over a plain re-search is that it skips destination
    discovery: the same destinations are re-priced over the new period rather than the
    cheapest ones being chosen again, so widening does not silently change which cities are
    on the board.
    """

    origin: str
    depart_date: str
    return_date: str
    destinations: list[str] = Field(default_factory=list, max_length=40)
    nights_min: int | None = Field(default=None, ge=0, le=60)
    nights_max: int | None = Field(default=None, ge=0, le=60)
    adults: int = Field(default=2, ge=1, le=9)
    children: int = Field(default=0, ge=0, le=8)
    currency: str = config.DEFAULT_CURRENCY
    nonstop_only: bool = False

    def to_request(self) -> SearchRequest:
        return SearchRequest(
            origin=self.origin.upper(), depart_date=self.depart_date,
            return_date=self.return_date, adults=self.adults, children=self.children,
            currency=self.currency.lower(), nonstop_only=self.nonstop_only,
            nights_min=self.nights_min, nights_max=self.nights_max,
        )


@app.post("/api/extend")
def start_extend(body: ExtendBody) -> dict[str, Any]:
    request = body.to_request()
    extend_id = uuid.uuid4().hex[:12]
    channel: queue.Queue = queue.Queue()
    _streams[extend_id] = channel
    _cancelled.discard(extend_id)
    depart_dates, return_dates = board.date_axes(request)

    def worker() -> None:
        try:
            provider = _make_provider()
            channel.put({
                "type": "axes",
                "depart_dates": [d.isoformat() for d in depart_dates],
                "return_dates": [d.isoformat() for d in return_dates],
                "pending": len(body.destinations),
            })
            for code in body.destinations:
                if extend_id in _cancelled:
                    break
                try:
                    payload = board.fill_one(request, code, provider=provider)
                    payload["type"] = "destination"
                    channel.put(payload)
                except Exception as exc:
                    channel.put({"type": "destination_error", "destination": code,
                                 "message": str(exc)[:200]})
        except Exception as exc:
            channel.put({"type": "error", "message": str(exc)})
        finally:
            _cancelled.discard(extend_id)
            channel.put(_SENTINEL)

    threading.Thread(target=worker, daemon=True).start()
    return {"extend_id": extend_id}


@app.get("/api/extend/{extend_id}/stream")
async def stream_extend(extend_id: str) -> StreamingResponse:
    return await stream_fill(extend_id)


class FillBody(BaseModel):
    origin: str
    destination: str
    depart_date: str
    return_date: str
    adults: int = Field(default=2, ge=1, le=9)
    children: int = Field(default=0, ge=0, le=8)
    currency: str = config.DEFAULT_CURRENCY
    nonstop_only: bool = False

    def to_request(self) -> SearchRequest:
        return SearchRequest(
            origin=self.origin.upper(), depart_date=self.depart_date,
            return_date=self.return_date, adults=self.adults, children=self.children,
            currency=self.currency.lower(), nonstop_only=self.nonstop_only,
        )


@app.post("/api/fill")
def start_fill(body: FillBody) -> dict[str, Any]:
    """Bulk-fill one destination's whole grid with live prices."""
    request = body.to_request()
    depart_dates, return_dates = board.date_axes(request)
    fill_id = uuid.uuid4().hex[:12]
    channel: queue.Queue = queue.Queue()
    _streams[fill_id] = channel
    _cancelled.discard(fill_id)

    def worker() -> None:
        try:
            for event in filler.fill(
                request, body.destination, depart_dates, return_dates,
                should_stop=lambda: fill_id in _cancelled,
            ):
                channel.put(event)
        except Exception as exc:
            channel.put({"type": "error", "message": str(exc)})
        finally:
            _cancelled.discard(fill_id)
            channel.put(_SENTINEL)

    threading.Thread(target=worker, daemon=True).start()
    pending = filler.pending_cells(request, body.destination, depart_dates, return_dates)
    return {"fill_id": fill_id, "pending": len(pending)}


class AutoVerifyBody(BaseModel):
    """Upgrade specific Kiwi cells to live Google Flights prices, cheapest first."""

    origin: str
    adults: int = Field(default=2, ge=1, le=9)
    children: int = Field(default=0, ge=0, le=8)
    currency: str = config.DEFAULT_CURRENCY
    nonstop_only: bool = False
    cells: list[dict[str, str]] = Field(default_factory=list, max_length=400)


@app.post("/api/autoverify")
def start_autoverify(body: AutoVerifyBody) -> dict[str, Any]:
    request = SearchRequest(
        origin=body.origin.upper(), depart_date="2000-01-01", return_date="2000-01-01",
        adults=body.adults, children=body.children, currency=body.currency.lower(),
        nonstop_only=body.nonstop_only,
    )
    targets = [
        (c["destination"], c["depart_date"], c["return_date"])
        for c in body.cells
        if c.get("destination") and c.get("depart_date") and c.get("return_date")
    ]
    job_id = uuid.uuid4().hex[:12]
    channel: queue.Queue = queue.Queue()
    _streams[job_id] = channel
    _cancelled.discard(job_id)

    def worker() -> None:
        try:
            for event in filler.verify_cells(
                request, targets, should_stop=lambda: job_id in _cancelled, label="auto",
            ):
                channel.put(event)
        except Exception as exc:
            channel.put({"type": "error", "message": str(exc)})
        finally:
            _cancelled.discard(job_id)
            channel.put(_SENTINEL)

    threading.Thread(target=worker, daemon=True).start()
    return {"fill_id": job_id, "pending": len(targets)}


@app.post("/api/fill/{fill_id}/cancel")
def cancel_fill(fill_id: str) -> dict[str, bool]:
    _cancelled.add(fill_id)
    return {"cancelled": True}


@app.get("/api/fill/{fill_id}/stream")
async def stream_fill(fill_id: str) -> StreamingResponse:
    channel = _streams.get(fill_id)
    if channel is None:
        raise HTTPException(status_code=404, detail="Unknown or finished fill id.")

    async def events():
        loop = asyncio.get_running_loop()
        while True:
            item = await loop.run_in_executor(None, channel.get)
            if item is _SENTINEL:
                yield "event: end\ndata: {}\n\n"
                _streams.pop(fill_id, None)
                return
            yield f"data: {json.dumps(item)}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/details")
def cell_details(body: VerifyBody) -> dict[str, Any]:
    """Flight times for one cell, from the board's own source.

    Separate from /api/verify because the two answer different questions and have different
    reach: this gives real departure/arrival times for both legs at any horizon, while the
    Google cross-check gives an independent price but has no data much beyond a year out.
    """
    request = SearchRequest(
        origin=body.origin.upper(), depart_date=body.depart_date, return_date=body.return_date,
        adults=body.adults, children=body.children, currency=body.currency.lower(),
        nonstop_only=body.nonstop_only,
    )
    provider = board.make_board_provider()
    if not hasattr(provider, "itinerary_details"):
        return {"error": "The current board source does not expose flight times."}
    try:
        details = provider.itinerary_details(
            request, body.destination, body.depart_date, body.return_date)
    except ProviderError as exc:
        return {"error": str(exc)}
    return {
        "destination": body.destination.upper(),
        "depart_date": body.depart_date,
        "return_date": body.return_date,
        "currency": body.currency,
        **details,
    }


@app.get("/api/airport/{code}")
def airport(code: str) -> dict[str, str]:
    return {"code": code.upper(), **airports.describe(code)}


@app.get("/api/regions")
def regions() -> dict[str, Any]:
    """The region tree for the destination filter: continent -> subregion -> countries."""
    return {"tree": airports.taxonomy()}


@app.middleware("http")
async def no_store_static(request, call_next):
    """Never let the browser cache the frontend.

    This is a local dev tool that gets edited in place; a stale cached stylesheet looks
    exactly like a bug in the app.
    """
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static"):
        response.headers["Cache-Control"] = "no-store, must-revalidate"
    return response


@app.get("/robots.txt", response_class=PlainTextResponse)
def robots(request: Request) -> str:
    """The board is one indexable page; the JSON API is not content and stays out.

    Both files derive the origin from the request rather than a configured hostname, so
    they stay correct behind whatever DNS name or reverse proxy the instance ends up on.
    """
    base = str(request.base_url).rstrip("/")
    return (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /api/\n"
        f"Sitemap: {base}/sitemap.xml\n"
    )


@app.get("/sitemap.xml")
def sitemap(request: Request) -> Response:
    base = str(request.base_url).rstrip("/")
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"  <url><loc>{base}/</loc></url>\n"
        "</urlset>\n"
    )
    return Response(content=xml, media_type="application/xml")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(config.FRONTEND_DIR / "index.html")


app.mount("/static", StaticFiles(directory=config.FRONTEND_DIR), name="static")
