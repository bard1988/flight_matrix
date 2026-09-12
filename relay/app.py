"""Google Flights relay: a private, minimal service that does one thing -- run a live
Google Flights lookup from THIS box's own IP and hand back the result.

Why this exists: the main app's Google Flights concurrency is deliberately capped low
(`config.FILL_WORKERS`) because a burst from one IP risks Google's bot detection, and a
block costs far more than the speed gained. Running a second (or third...) instance of
this relay on a separate box, each behind the same conservative per-IP concurrency,
raises the *total* throughput without raising how bursty any single IP looks. See
idea.md's Lever 2 -- the same shape of idea already considered for Kiwi, applied here to
Google, using boxes we already have instead of a paid proxy.

Security model: this has no auth of its own. The network boundary IS the boundary -- the
VCN security list only lets the main app's own IP reach this port, and nothing else on the
internet can. Don't expose this port more widely without adding real auth first.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from providers.base import ProviderError
from providers.google_flights import GoogleFlightsProvider

app = FastAPI(title="FlightMatrix Google Flights relay", docs_url=None, redoc_url=None)
_provider = GoogleFlightsProvider()


class VerifyBody(BaseModel):
    origin: str
    destination: str
    depart_date: str
    return_date: str
    adults: int = 2
    children: int = 0
    currency: str = "ils"
    nonstop_only: bool = False


@app.get("/health")
def health() -> dict:
    return {"ok": True, "role": "google-relay"}


@app.post("/verify")
def verify(body: VerifyBody) -> dict:
    """Same shape as the main app's GoogleFlightsProvider.verify() -- a relay client on
    the main side can treat this exactly like a local call."""
    try:
        return _provider.verify(
            origin=body.origin, destination=body.destination,
            depart_date=body.depart_date, return_date=body.return_date,
            adults=body.adults, children=body.children,
            currency=body.currency, nonstop_only=body.nonstop_only,
        )
    except ProviderError as exc:
        # A 200 with an error field would let a careless caller silently treat "no fare
        # found" as success; a real HTTP error status is harder to miss.
        raise HTTPException(status_code=502, detail=str(exc)) from exc
