"""Ryanair's fare-finder, wired in for origins Ryanair actually flies from.

Ryanair serves no Israeli airport, so from TLV it contributes nothing. But the origin box
now takes any airport, and for a search out of Kraków, Stansted, Bergamo, Dublin or any of
Ryanair's ~230 bases it is the single best source there is: one keyless call returns the
cheapest round trip from that origin to *every* Ryanair destination over a date range,
filtered by trip length -- a whole discovery pass in one request. `cheapestPerDay` then
fills an opened grid, one call per leg-month.

Fares are per-person (an LCC prices per seat), so cells are left is_total=False for the
usual party scaling and converted from EUR via fx.py. The API is stable, documented, and
needs no cookies -- none of the version-scraping the Wizz provider carries.
"""
from __future__ import annotations

import threading
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx

import config
import fx
from models import Cell, DestinationMatrix, SearchRequest
from providers.base import ProviderError

_FARE_API = "https://services-api.ryanair.com/farfnd/v4"
_SITE_API = "https://www.ryanair.com/api"
_BOOK = "https://www.ryanair.com/gb/en/trip/flights/select"
_ROUTES_TTL = 24 * 3600         # the origin->destinations graph barely moves
_RTF_LIMIT = 16                 # roundTripFares rejects anything larger ("InvalidLimit")
_CALL_SPACING = 0.4

_UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-GB,en;q=0.9",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _months_spanned(first: date, last: date) -> list[date]:
    out, cur = [], first.replace(day=1)
    while cur <= last:
        out.append(cur)
        cur = (cur + timedelta(days=32)).replace(day=1)
    return out


class RyanairProvider:
    name = "ryanair"
    strategy = "ryanair-farfnd"

    def __init__(self, timeout: float = 20.0) -> None:
        self._timeout = timeout
        self._lock = threading.Lock()
        self._next_call = 0.0
        # {origin: {dest: {"city","country"}}}, cached per origin with a timestamp
        self._routes: dict[str, tuple[float, dict[str, dict[str, str]]]] = {}
        self.cities: dict[str, dict[str, str]] = {}

    # ------------------------------------------------------------------ transport

    def _pace(self) -> None:
        with self._lock:
            wait = self._next_call - time.monotonic()
            self._next_call = max(time.monotonic(), self._next_call) + _CALL_SPACING
        if wait > 0:
            time.sleep(wait)

    def _get(self, base: str, path: str, params: dict[str, Any]) -> Any:
        self._pace()
        try:
            with httpx.Client(timeout=self._timeout, headers=_UA, verify=config.CA_BUNDLE,
                              follow_redirects=True) as c:
                r = c.get(f"{base}/{path}", params=params)
        except httpx.HTTPError as exc:
            raise ProviderError(f"Ryanair {path}: {exc}") from exc
        if r.status_code != 200:
            raise ProviderError(f"Ryanair {path}: HTTP {r.status_code} {r.text[:120]}")
        try:
            return r.json()
        except ValueError as exc:
            raise ProviderError(f"Ryanair {path}: bad JSON") from exc

    # ------------------------------------------------------------------ route map

    def routes(self, origin: str) -> dict[str, dict[str, str]]:
        """{dest_iata: {city, country}} Ryanair flies non-stop from this origin. Cached 24h.

        `searchWidget/routes` is the whole origin graph -- the Ryanair equivalent of Wizz's
        `asset/map`. Empty (not an error) when the origin is off Ryanair's network.
        """
        origin = origin.upper()
        cached = self._routes.get(origin)
        if cached and time.time() - cached[0] < _ROUTES_TTL:
            return cached[1]
        try:
            rows = self._get(_SITE_API, f"views/locate/searchWidget/routes/en/airport/{origin}", {})
        except ProviderError:
            return {}
        found: dict[str, dict[str, str]] = {}
        for row in rows if isinstance(rows, list) else []:
            a = row.get("arrivalAirport") or {}
            code = (a.get("code") or "").upper()
            if not code:
                continue
            found[code] = {
                "city": (a.get("city") or {}).get("name") or a.get("name") or code,
                "country": (a.get("country") or {}).get("code", "").upper(),
                "name": a.get("name") or code,
            }
        self._routes[origin] = (time.time(), found)
        self.cities.update(found)
        return found

    def serves(self, origin: str, dest: str) -> bool:
        return dest.upper() in self.routes(origin)

    # ------------------------------------------------------------------ discovery

    def discover(self, request: SearchRequest, dd: list[date], rd: list[date]
                 ) -> list[tuple[str, float]]:
        """The cheapest Ryanair destinations from this origin, with real round-trip party
        prices. `roundTripFares` is a short "inspire me" list (~12-16 places), not the whole
        map -- the map feeds `serves()`; this feeds the ranked candidate list."""
        span = request.nights_span()
        try:
            data = self._get(_FARE_API, "roundTripFares", {
                "departureAirportIataCode": request.origin.upper(),
                "outboundDepartureDateFrom": dd[0].isoformat(),
                "outboundDepartureDateTo": dd[-1].isoformat(),
                "inboundDepartureDateFrom": rd[0].isoformat(),
                "inboundDepartureDateTo": rd[-1].isoformat(),
                "durationFrom": span[0], "durationTo": span[-1],
                "currency": "EUR", "limit": _RTF_LIMIT,
            })
        except ProviderError:
            return []
        cur = request.currency.upper()
        best: dict[str, float] = {}
        for f in data.get("fares") or []:
            a = ((f.get("outbound") or {}).get("arrivalAirport") or {}).get("iataCode")
            pv = (f.get("summary") or {}).get("price") or {}
            if not a or pv.get("value") is None:
                continue
            party = fx.convert(float(pv["value"]), pv.get("currencyCode") or "EUR", cur) \
                * max(request.passengers, 1)
            best[a.upper()] = min(best.get(a.upper(), party), round(party, 2))
        self.routes(request.origin)          # warm the map / cities for these codes
        return sorted(best.items(), key=lambda kv: kv[1])

    # ------------------------------------------------------------------ fill

    def _per_day(self, origin: str, dest: str, months: list[date], currency: str
                 ) -> dict[str, tuple[float, str]]:
        out: dict[str, tuple[float, str]] = {}
        for m in months:
            try:
                data = self._get(_FARE_API,
                                 f"oneWayFares/{origin.upper()}/{dest.upper()}/cheapestPerDay",
                                 {"outboundMonthOfDate": m.isoformat(), "currency": "EUR"})
            except ProviderError:
                continue
            for x in (data.get("outbound") or {}).get("fares", []):
                p = x.get("price") or {}
                if x.get("day") and p.get("value") is not None and not x.get("soldOut") and not x.get("unavailable"):
                    out[x["day"]] = (float(p["value"]), p.get("currencyCode") or "EUR")
        return out

    def fill_matrix(self, request: SearchRequest, destination: str,
                    depart_dates: list[date], return_dates: list[date]) -> DestinationMatrix:
        origin, dest = request.origin.upper(), destination.upper()
        matrix = DestinationMatrix(origin=origin, destination=dest)

        out = self._per_day(origin, dest, _months_spanned(depart_dates[0], depart_dates[-1]), "EUR")
        back = self._per_day(dest, origin, _months_spanned(return_dates[0], return_dates[-1]), "EUR")
        if not out or not back:
            return matrix

        span = set(request.nights_span())
        first_dep, last_dep = depart_dates[0], depart_dates[-1]
        first_ret, last_ret = return_dates[0], return_dates[-1]
        now = _utcnow()
        found, expires = now.isoformat(), (now + timedelta(hours=12)).isoformat()
        cur = request.currency.upper()

        for di, (oa, oc) in sorted(out.items()):
            dep = date.fromisoformat(di)
            if not first_dep <= dep <= last_dep:
                continue
            for ri, (ba, bc) in sorted(back.items()):
                ret = date.fromisoformat(ri)
                if not first_ret <= ret <= last_ret or (ret - dep).days not in span:
                    continue
                pp = fx.convert(oa, oc, cur) + fx.convert(ba, bc, cur)
                matrix.add(Cell(
                    depart_date=di, return_date=ri,
                    price=round(pp, 2), currency=cur,
                    airline="Ryanair", transfers=0, return_transfers=0,
                    found_at=found, expires_at=expires,
                    source="ryanair", is_total=False,
                    link=self.deep_link(origin, dest, di, ri, request.adults, request.children),
                ))
        return matrix

    @staticmethod
    def deep_link(origin: str, dest: str, dep: str, ret: str, adults: int, children: int) -> str:
        return (f"{_BOOK}?adults={max(adults,1)}&teens=0&children={max(children,0)}&infants=0"
                f"&dateOut={dep}&dateIn={ret}&isConnectedFlight=false&isReturn=true"
                f"&originIata={origin.upper()}&destinationIata={dest.upper()}")

    def close(self) -> None:
        pass
