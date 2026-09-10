"""Wizz Air's own booking calendar, wired in for the routes Wizz flies.

The aggregators (Kiwi, Travelpayouts, Google Flights) all resell one GDS+NDC+LCC pool,
and it thins out for small routes booked far ahead: a TLV -> Iasi trip seven months out
returned nothing from any of them while Wizz's own site was selling it for EUR 90. This
provider closes that gap.

- `asset/map` gives Wizz's route graph, so its ~29 TLV destinations feed discovery.
- `search/timetable` returns ~20 dated lowest fares per leg in one POST, and the two legs
  are priced independently -- so a whole destination grid costs two calls.

Caveats, handled here:
- The API version is pinned in a path string Wizz relocates. Scraped from the homepage
  and cached (data/wizz_meta.json); a stale value just triggers one re-scrape.
- The timetable price is the per-person lowest ("Basic") fare in the route's home
  currency. It is converted to the board currency (fx.py) and left as is_total=False so
  the party scaling every non-total source gets is applied.
- Repeat calls inside a few seconds return {"handlerError":"InvalidProtocol"}; calls are
  paced ~4s apart.
"""
from __future__ import annotations

import json
import re
import threading
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx

import config
import fx
from models import Cell, DestinationMatrix, SearchRequest
from providers.base import ProviderError

_HOME = "https://wizzair.com/"
_LAST_KNOWN_VERSION = "29.15.1"
_META_CACHE = config.DATA_DIR / "wizz_meta.json"
_ROUTES_CACHE = config.DATA_DIR / "wizz_routes.json"
_META_TTL = 12 * 3600
_ROUTES_TTL = 7 * 24 * 3600
_CALL_SPACING = 4.0

_UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Origin": "https://wizzair.com",
    "Referer": "https://wizzair.com/",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class WizzProvider:
    name = "wizz"
    strategy = "wizz-timetable"

    def __init__(self, timeout: float = 25.0) -> None:
        self._client = httpx.Client(timeout=timeout, headers=_UA, verify=config.CA_BUNDLE,
                                    follow_redirects=True)
        self._lock = threading.Lock()
        self._next_call = 0.0
        self._version: str | None = None
        self._map: dict[str, set[str]] | None = None
        # {IATA: {"city", "country"}} for _describe-style lookups by the board.
        self.cities: dict[str, dict[str, str]] = {}

    # ------------------------------------------------------------------ transport

    def _pace(self) -> None:
        with self._lock:
            wait = self._next_call - time.monotonic()
            self._next_call = max(time.monotonic(), self._next_call) + _CALL_SPACING
        if wait > 0:
            time.sleep(wait)

    def _api(self) -> str:
        if self._version is None:
            self._version = self._resolve_version()
        return f"https://be.wizzair.com/{self._version}/Api"

    def _resolve_version(self) -> str:
        try:
            blob = json.loads(_META_CACHE.read_text("utf-8"))
            if time.time() - blob.get("fetched", 0) < _META_TTL and blob.get("version"):
                return blob["version"]
        except (OSError, ValueError):
            pass
        version = _LAST_KNOWN_VERSION
        try:
            html = self._client.get(_HOME).text
            m = re.search(r"be\.wizzair\.com/(\d+\.\d+\.\d+)/Api", html)
            if m:
                version = m.group(1)
        except httpx.HTTPError:
            pass
        try:
            config.DATA_DIR.mkdir(parents=True, exist_ok=True)
            _META_CACHE.write_text(json.dumps({"fetched": time.time(), "version": version}), "utf-8")
        except OSError:
            pass
        return version

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        self._pace()
        try:
            r = self._client.post(f"{self._api()}/{path}", content=json.dumps(body))
        except httpx.HTTPError as exc:
            raise ProviderError(f"Wizz {path}: {exc}") from exc
        if r.status_code == 400 and "InvalidProtocol" in r.text:
            raise ProviderError("Wizz rate-limited this call (InvalidProtocol).")
        if r.status_code != 200:
            raise ProviderError(f"Wizz {path}: HTTP {r.status_code} {r.text[:120]}")
        try:
            return r.json()
        except ValueError as exc:
            raise ProviderError(f"Wizz {path}: bad JSON") from exc

    # ------------------------------------------------------------------ route map

    def _load_map(self) -> dict[str, set[str]]:
        if self._map is not None:
            return self._map
        cached = self._read_routes_cache()
        if cached is not None:
            self._map = cached
            return self._map
        self._map = self._fetch_map()
        return self._map

    def _read_routes_cache(self) -> dict[str, set[str]] | None:
        try:
            blob = json.loads(_ROUTES_CACHE.read_text("utf-8"))
        except (OSError, ValueError):
            return None
        if time.time() - blob.get("fetched", 0) >= _ROUTES_TTL:
            return None
        self.cities = blob.get("cities", {})
        return {o: set(ds) for o, ds in (blob.get("routes") or {}).items()}

    def _fetch_map(self) -> dict[str, set[str]]:
        self._pace()
        try:
            data = self._client.get(f"{self._api()}/asset/map",
                                    params={"languageCode": "en-gb"}).json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError(f"Wizz asset/map: {exc}") from exc
        routes: dict[str, set[str]] = {}
        cities: dict[str, dict[str, str]] = {}
        for city in data.get("cities", []):
            iata = (city.get("iata") or "").upper()
            if not iata or city.get("isFakeStation"):
                continue
            cities[iata] = {
                "city": (city.get("shortName") or iata),
                "country": (city.get("countryCode") or "").upper(),
                "name": city.get("shortName") or iata,
            }
            dests = {
                (c.get("iata") or "").upper()
                for c in city.get("connections", [])
                if c.get("isDirectFlight") and c.get("iata")
            }
            if dests:
                routes[iata] = dests
        self.cities = cities
        try:
            config.DATA_DIR.mkdir(parents=True, exist_ok=True)
            _ROUTES_CACHE.write_text(json.dumps({
                "fetched": time.time(),
                "routes": {o: sorted(ds) for o, ds in routes.items()},
                "cities": cities,
            }), "utf-8")
        except OSError:
            pass
        return routes

    def routes(self, origin: str) -> list[str]:
        """Destination IATAs Wizz flies non-stop from `origin`. Empty if the map fails."""
        try:
            return sorted(self._load_map().get(origin.upper(), set()))
        except ProviderError:
            return []

    def serves(self, origin: str, destination: str) -> bool:
        return destination.upper() in set(self.routes(origin))

    # ------------------------------------------------------------------ fill

    @staticmethod
    def _priced(flights: list[dict[str, Any]]) -> dict[str, tuple[float, str]]:
        out: dict[str, tuple[float, str]] = {}
        for f in flights:
            price = f.get("price") or {}
            amount = price.get("amount")
            if f.get("priceType") == "price" and amount:
                day = str(f.get("departureDate") or "")[:10]
                if day:
                    out[day] = (float(amount), price.get("currencyCode") or "EUR")
        return out

    def _timetable(self, origin: str, dest: str, first: date, last: date, ret_first: date,
                   ret_last: date) -> tuple[dict[str, tuple[float, str]], dict[str, tuple[float, str]]]:
        """Both legs in one POST: ({dep -> (amt, ccy)}, {ret -> (amt, ccy)}) of priced days.

        Wizz returns outbound and return prices independently in a single response, and
        rejects calls made a few seconds apart -- so one call per destination, not two.
        """
        body = {
            "flightList": [
                {"departureStation": origin.upper(), "arrivalStation": dest.upper(),
                 "from": first.isoformat(), "to": last.isoformat()},
                {"departureStation": dest.upper(), "arrivalStation": origin.upper(),
                 "from": ret_first.isoformat(), "to": ret_last.isoformat()},
            ],
            "priceType": "regular",
            "adultCount": 1, "childCount": 0, "infantCount": 0,
        }
        data = self._post("search/timetable", body)
        return self._priced(data.get("outboundFlights", [])), self._priced(data.get("returnFlights", []))

    def fill_matrix(
        self,
        request: SearchRequest,
        destination: str,
        depart_dates: list[date],
        return_dates: list[date],
    ) -> DestinationMatrix:
        origin = request.origin.upper()
        dest = destination.upper()
        matrix = DestinationMatrix(origin=origin, destination=dest)
        if not self.serves(origin, dest):
            return matrix

        out, back = self._timetable(origin, dest, depart_dates[0], depart_dates[-1],
                                    return_dates[0], return_dates[-1])
        if not out or not back:
            return matrix

        span = set(request.nights_span())
        now = _utcnow()
        found = now.isoformat()
        expires = (now + timedelta(hours=18)).isoformat()
        cur = request.currency.upper()

        for dep in depart_dates:
            di = dep.isoformat()
            if di not in out:
                continue
            for ret in return_dates:
                ri = ret.isoformat()
                if ri not in back or ret <= dep or (ret - dep).days not in span:
                    continue
                (out_amt, out_ccy), (back_amt, back_ccy) = out[di], back[ri]
                pp = fx.convert(out_amt, out_ccy, cur) + fx.convert(back_amt, back_ccy, cur)
                matrix.add(Cell(
                    depart_date=di,
                    return_date=ri,
                    price=round(pp, 2),
                    currency=cur,
                    airline="Wizz Air",
                    transfers=0,
                    return_transfers=0,
                    found_at=found,
                    expires_at=expires,
                    source="wizz",
                    is_total=False,
                    link=self.deep_link(origin, dest, di, ri, request.adults, request.children),
                ))
        return matrix

    # ------------------------------------------------------------------ booking link

    @staticmethod
    def deep_link(origin: str, dest: str, depart: str, ret: str,
                  adults: int, children: int) -> str:
        return (
            "https://wizzair.com/en-gb/booking/select-flight/"
            f"{origin.upper()}/{dest.upper()}/{depart}/{ret}/"
            f"{max(adults, 1)}/{max(children, 0)}/0"
        )

    def close(self) -> None:
        self._client.close()
