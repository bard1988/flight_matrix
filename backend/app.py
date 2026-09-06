"""SkyMatrix FastAPI layer. Serves the static board and streams destinations as they fill."""
from __future__ import annotations

import asyncio
import json
import os
import queue
import threading
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
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
from providers.travelpayouts import TravelpayoutsProvider

app = FastAPI(title="SkyMatrix", docs_url="/api/docs")


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
    window_days: int = Field(default=config.WINDOW_DAYS, ge=1, le=config.MAX_WINDOW_DAYS)
    destination_filter: str = Field(default="", max_length=60)
    date_mode: str = Field(default="anchors", pattern="^(anchors|range)$")
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
            window_days=self.window_days,
            destination_filter=self.destination_filter,
            date_mode=self.date_mode,
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
        "window_days": config.WINDOW_DAYS,
        "child_factor": config.CHILD_FACTOR,
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
    try:
        for event in board.build(request, provider=provider):
            collected.append(event)
            channel.put(event)
    except Exception as exc:                    # never leave the client hanging
        channel.put({"type": "error", "message": str(exc)})
    finally:
        destinations = [e for e in collected if e.get("type") == "destination"]
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
    _streams[search_id] = queue.Queue()
    threading.Thread(target=_run_search, args=(search_id, request), daemon=True).start()
    return {"search_id": search_id}


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
            return {**cached, "cached": True}

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
                body.adults, body.children,
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
    """Re-fetch the listed destinations over a wider date window."""

    origin: str
    depart_date: str
    return_date: str
    destinations: list[str] = Field(default_factory=list, max_length=40)
    window_days: int = Field(default=14, ge=1, le=config.MAX_WINDOW_DAYS)
    adults: int = Field(default=2, ge=1, le=9)
    children: int = Field(default=0, ge=0, le=8)
    currency: str = config.DEFAULT_CURRENCY
    nonstop_only: bool = False

    def to_request(self) -> SearchRequest:
        return SearchRequest(
            origin=self.origin.upper(), depart_date=self.depart_date,
            return_date=self.return_date, adults=self.adults, children=self.children,
            currency=self.currency.lower(), nonstop_only=self.nonstop_only,
            window_days=self.window_days,
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
                "window_days": request.window_days,
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
    return {"extend_id": extend_id, "window_days": request.window_days}


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


@app.get("/")
def index() -> FileResponse:
    return FileResponse(config.FRONTEND_DIR / "index.html")


app.mount("/static", StaticFiles(directory=config.FRONTEND_DIR), name="static")
