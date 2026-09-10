"""Tiny server-side currency conversion, for the one source that needs it.

Kiwi and Travelpayouts price in the currency asked for. Wizz's timetable returns the
route's home currency (EUR for most TLV routes), and the frontend assumes every cell it
receives is already in the board currency -- so a Wizz cell has to be converted here
before it is emitted.

Daily rates from a keyless endpoint, cached to data/fx.json, with a frozen fallback table
so a fetch failure never blocks a board. Rates are units per 1 EUR.
"""
from __future__ import annotations

import json
import threading
import time
from typing import Any

import httpx

import config

_CACHE = config.DATA_DIR / "fx.json"
_TTL_SECONDS = 18 * 3600
_ENDPOINT = "https://open.er-api.com/v6/latest/EUR"

# Frozen mid-market rates (units per 1 EUR), good enough that a stale table still gives a
# fare within a few percent. Refreshed opportunistically from _ENDPOINT.
_FALLBACK: dict[str, float] = {
    "EUR": 1.0, "USD": 1.08, "GBP": 0.85, "ILS": 4.0,
}

_lock = threading.Lock()
_rates: dict[str, float] | None = None


def _load() -> dict[str, float]:
    global _rates
    if _rates is not None:
        return _rates
    with _lock:
        if _rates is not None:
            return _rates
        cached = _read_cache()
        if cached is not None:
            _rates = cached
            return _rates
        _rates = _fetch() or dict(_FALLBACK)
        return _rates


def _read_cache() -> dict[str, float] | None:
    try:
        blob = json.loads(_CACHE.read_text("utf-8"))
        if time.time() - blob.get("fetched", 0) < _TTL_SECONDS and blob.get("rates"):
            return {k.upper(): float(v) for k, v in blob["rates"].items()}
    except (OSError, ValueError, TypeError):
        pass
    return None


def _fetch() -> dict[str, float] | None:
    try:
        r = httpx.get(_ENDPOINT, timeout=10.0, verify=config.CA_BUNDLE)
        r.raise_for_status()
        data: dict[str, Any] = r.json()
        rates = {k.upper(): float(v) for k, v in (data.get("rates") or {}).items()}
        if "EUR" not in rates or "USD" not in rates:
            return None
        try:
            config.DATA_DIR.mkdir(parents=True, exist_ok=True)
            _CACHE.write_text(json.dumps({"fetched": time.time(), "rates": rates}), "utf-8")
        except OSError:
            pass
        return rates
    except (httpx.HTTPError, ValueError, TypeError):
        return None


def convert(amount: float, src: str, dst: str) -> float:
    """`amount` in `src` currency, returned in `dst`. Falls back to a frozen table."""
    src, dst = src.upper(), dst.upper()
    if src == dst:
        return amount
    rates = _load()
    rs, rd = rates.get(src), rates.get(dst)
    if not rs or not rd:
        rs, rd = _FALLBACK.get(src), _FALLBACK.get(dst)
    if not rs or not rd:
        return amount           # unknown currency: better the raw number than zero
    return amount * rd / rs
